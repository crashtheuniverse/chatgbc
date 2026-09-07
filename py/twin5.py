"""The bit-exact integer twin of the v0.5 assembly. Semantics decided HERE.

Every arithmetic rule the SM83 will follow is written in this file first, in
the exact widths, rounding and order the kernels will use - then the assembly
is judged against it byte for byte. Same contract that carried v0.3.

What carries over from the v0.4 twin, imported rather than re-derived:
4-bit Lloyd-Max codebooks with per-output-row exponents, quarter-scaled
product tables (ACC_SHIFT), int16 accumulator discipline, power-of-two site
exponents, shift-only requantization, the int8 tied classifier.

What is new, and its exact integer form:

**The gate.** zl (int8 at site e_zl) indexes a 256-entry sigmoid table built
for that exponent, giving zg in Q0.8 (0..255). With h and ht int8 at the
shared state site e_h:

    s     = zg * ht + (256 - zg) * h          # convex: |s| <= 256*127, s16-safe
    h_new = sat8(shr_round(s, 8))

The assembly computes the same integer as
    s = M(zg-128, ht) - M(zg-128, h) + ((ht + h) << 7)
because its multiplier is the signed quarter-square table; the two forms are
algebraically identical over the integers, so the twin keeps the readable one.

**ReLU squared.** a (int8 at e_h1) -> u (int8 at e_hb):

    u = sat8(shr_round(max(a,0)^2, e_hb - 2*e_h1))

max(a,0)^2 <= 16129, one quarter-square lookup on the cartridge; the shift
count is a per-layer export constant and may be negative (a left shift).

**State.** h starts at zero and persists across tokens: it IS the
conversation. 64 bytes per layer, int8, at one calibrated site per layer.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import quant as Q                     # noqa: E402  the v0.4 integer machinery
from model5 import Model5, State5, forward5, rms, Tokenizer, EOS  # noqa: E402

ACC_SHIFT = Q.ACC_SHIFT
MATS = ("wz", "wh", "wo", "w1", "w2")

# The ternary block kernel: blocks of three inputs, every block sum EXACT and
# every accumulator exact. The first version halved each block sum to keep
# a 352-input row inside int16, with round-half-up - and round-half-up on a
# halved sum is a bias of +0.5 on every odd block, ~11 units a row, enough
# to turn a model that speaks in fp32 into "little little little" through
# three layers of skewed gates. Instead: a 64-input row is at most 8,128,
# exact; w2's 352 inputs run as two halves of 59 blocks (at most 22,479
# each), each requantized and added into the stream in turn. A checkpoint
# whose rows are {-a, 0, +a} with a a power of two - what the trainer's
# ternary quantizer with POW2_SCALE emits - is detected per tensor and
# takes this path.
TERNARY_BLOCK = 3
TERNARY_ACC_SHIFT = 0
W2_SPLIT_BLOCKS = 59                       # inputs 0..176 | 177..351

# The one-bit block kernel: blocks of FOUR inputs, coefficients in {-1, +1},
# every block sum exact - the 16-entry table src/matvec4b.asm builds. Four
# tiles every width the model uses, so there is no padding (a one-bit row has
# no zero to pad with). A checkpoint whose rows are {-a, +a} with a a power of
# two - the trainer's binary quantizer with POW2_SCALE - takes this path; it
# is checked before the ternary test, which would also accept such rows.
BINARY_BLOCK = 4
BINARY_CLS_BLOCK = 8                       # the classifier's WRAM-table kernel
TERNARY_CLS_BLOCK = 5                      # the ternary classifier's planes: 3^5 = 243 sums
W2_SPLIT_BLOCKS_BIN = 44                   # inputs 0..175 | 176..351


def binary_rows(arr):
    """(b, rowexp) if every row of every layer is exactly {-a, +a} with a a
    power of two and no zero anywhere, else None. b is int8 in {-1, +1}."""
    b = np.where(arr > 0, 1, -1).astype(np.int8)
    rowexp = np.zeros(arr.shape[:-1], dtype=np.int32)
    for idx in np.ndindex(arr.shape[:-1]):
        row = arr[idx]
        mags = np.unique(np.abs(row))
        if len(mags) != 1 or mags[0] <= 0:
            return None
        e = np.log2(mags[0])
        if e != np.round(e):
            return None
        rowexp[idx] = int(np.round(e))
    return b, rowexp


def ternary_rows(arr):
    """(t, rowexp) if every row of every layer is {-a, 0, +a} with a a power
    of two, else None. t is int8 in {-1, 0, 1}; a_r = 2 ** rowexp_r."""
    t = np.zeros(arr.shape, dtype=np.int8)
    rowexp = np.zeros(arr.shape[:-1], dtype=np.int64)
    for idx in np.ndindex(arr.shape[:-1]):
        row = arr[idx]
        nz = row[row != 0]
        if nz.size == 0:
            continue
        a = np.abs(nz).max()
        e = np.log2(a)
        if abs(e - round(e)) > 1e-9 or not np.all(np.isclose(np.abs(nz), a)):
            return None
        rowexp[idx] = int(round(e))
        t[idx] = np.sign(row).astype(np.int8)
    return t, rowexp


def shr_round_any(x, s):
    """Q.shr_round for s >= 0; a plain left shift for s < 0."""
    if s >= 0:
        return Q.shr_round(x, s)
    return np.asarray(x) << (-s)


def sigmoid_table(e_zl):
    """zg = round(256 * sigmoid(zl * 2^e_zl)), clamped to 0..255, indexed by
    zl + 128. Built per calibrated exponent, so the table IS the exponent."""
    t = np.zeros(256, dtype=np.int64)
    for i in range(256):
        v = (i - 128) * 2.0 ** e_zl
        t[i] = min(255, round(256.0 / (1.0 + np.exp(-v))))
    return t


@dataclass
class Quant5:
    cfg: object
    sites: dict
    wexp: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)      # int codebook values / int8
    rowexp: dict = field(default_factory=dict)
    codebooks: dict = field(default_factory=dict)
    indices: dict = field(default_factory=dict)
    sig_tables: list = field(default_factory=list)   # per layer

    def site(self, name, l=None):
        return self.sites[name] if l is None else self.sites[name][l]


def calibrate5(m, tok, prompts, extra=0.0):
    """Site exponents from the fp32 model's own activations over conversation
    prompts - the same discipline as v0.4's calibrate, written against the
    minGRU forward. Returns {site: exp or [exp per layer]}."""
    L = m.cfg.layers
    mx = {k: np.zeros(L) for k in
          ("xb_att", "zl", "h", "att_out", "xb_ffn", "h1", "hb")}
    mx["x"] = 0.0
    mx["xb_final"] = 0.0
    for text in prompts:
        st = State5(m.cfg)
        ids = tok.encode(text)
        t = ids[0]
        for pos in range(len(ids)):
            x = m.tok_emb[t].copy()
            mx["x"] = max(mx["x"], np.abs(x).max())
            for l in range(L):
                xn = rms(x, m.rms_att[l])
                mx["xb_att"][l] = max(mx["xb_att"][l], np.abs(xn).max())
                zlog = m.wz[l] @ xn
                mx["zl"][l] = max(mx["zl"][l], np.abs(zlog).max())
                z = 1.0 / (1.0 + np.exp(-zlog))
                ht = m.wh[l] @ xn
                st.h[l] = (1.0 - z) * st.h[l] + z * ht
                mx["h"][l] = max(mx["h"][l], np.abs(st.h[l]).max(),
                                 np.abs(ht).max())
                ao = m.wo[l] @ st.h[l]
                mx["att_out"][l] = max(mx["att_out"][l], np.abs(ao).max())
                x = x + ao
                mx["x"] = max(mx["x"], np.abs(x).max())
                xf = rms(x, m.rms_ffn[l])
                mx["xb_ffn"][l] = max(mx["xb_ffn"][l], np.abs(xf).max())
                if getattr(m, "experts", 0):
                    e = int(np.argmax(m.router[l] @ xf))
                    w1, w2 = m.w1[l][e], m.w2[l][e]
                else:
                    w1, w2 = m.w1[l], m.w2[l]
                a = w1 @ xf
                mx["h1"][l] = max(mx["h1"][l], np.abs(a).max())
                u = np.maximum(a, 0.0) ** 2
                mx["hb"][l] = max(mx["hb"][l], np.abs(u).max())
                x = x + w2 @ u
                mx["x"] = max(mx["x"], np.abs(x).max())
            xb = rms(x, m.rms_final)
            mx["xb_final"] = max(mx["xb_final"], np.abs(xb).max())
            t = ids[pos + 1] if pos + 1 < len(ids) else int(
                (m.tok_emb @ xb).argmax())
    sites = {}
    for k, v in mx.items():
        if np.ndim(v) == 0:
            sites[k] = Q.exp_for(float(v) * (1 + extra))
        else:
            sites[k] = [Q.exp_for(float(x) * (1 + extra)) for x in v]
    return sites


def quantize5(m, sites):
    q = Quant5(cfg=m.cfg, sites=sites)
    # classifier / embedding: uniform int8, single exponent, tied - as v0.4.
    # A ternary embedding with ONE scale for the whole tensor takes the block
    # kernel for the classifier: argmax over block sums needs no per-row
    # rescale when every row shares the scale.
    q.binary_cls = False
    binr = binary_rows(m.tok_emb[None, :, :])
    if binr is not None and np.all(binr[1] == binr[1].flat[0]):
        q.wexp["tok_emb"] = int(binr[1].flat[0])
        q.weights["tok_emb"] = binr[0][0].astype(np.int64)
        q.rowexp["tok_emb"] = np.zeros(m.cfg.vocab, dtype=np.int8)
        q.binary_cls = True
    tern = None if q.binary_cls else ternary_rows(m.tok_emb[None, :, :])
    q.ternary_cls = False
    if tern is not None:
        t, rowexp = tern
        live = np.any(t[0] != 0, axis=-1)
        if np.any(live) and np.all(rowexp[0][live] == rowexp[0][live][0]):
            q.wexp["tok_emb"] = int(rowexp[0][live][0])
            q.weights["tok_emb"] = t[0].astype(np.int64)
            q.rowexp["tok_emb"] = np.zeros(m.cfg.vocab, dtype=np.int8)
            q.ternary_cls = True
    if not q.ternary_cls and not q.binary_cls:
        e = Q.exp_for(float(np.abs(m.tok_emb).max()))
        q.wexp["tok_emb"] = e
        q.weights["tok_emb"] = Q.quantize(m.tok_emb, e)
        q.rowexp["tok_emb"] = np.zeros(m.cfg.vocab, dtype=np.int8)
    for name in ("rms_att", "rms_ffn"):
        arr = np.stack(getattr(m, name))
        eN = Q.exp_for(float(np.abs(arr).max()))
        q.wexp[name] = eN
        q.weights[name] = Q.quantize(arr, eN)
    ef = Q.exp_for(float(np.abs(m.rms_final).max()))
    q.wexp["rms_final"] = ef
    q.weights["rms_final"] = Q.quantize(m.rms_final, ef)

    q.ternary = {}
    q.binary = {}
    for name in MATS:
        arr = np.stack(getattr(m, name))
        binr = binary_rows(arr)
        if binr is not None:
            b, rowexp = binr
            e = int(rowexp.min())
            q.wexp[name] = e
            q.rowexp[name] = (rowexp - e).astype(np.int8)
            q.indices[name] = b
            q.codebooks[name] = np.array([-1, 1], dtype=np.int64)
            q.weights[name] = b.astype(np.int64)
            q.ternary[name] = False
            q.binary[name] = True
            continue
        q.binary[name] = False
        tern = ternary_rows(arr)
        if tern is not None:
            # Lossless: the weight IS t * 2^(wexp + rowexp). wexp is the
            # smallest row scale so every rowexp is non-negative, as the
            # 4-bit path's are.
            t, rowexp = tern
            live = np.any(t != 0, axis=-1)          # rows with any weight
            e = int(rowexp[live].min()) if np.any(live) else 0
            q.wexp[name] = e
            q.rowexp[name] = (rowexp - e).astype(np.int8)
            q.indices[name] = t
            q.codebooks[name] = np.array([-1, 0, 1], dtype=np.int64)
            q.weights[name] = t.astype(np.int64)
            q.ternary[name] = True
            continue
        q.ternary[name] = False
        e = Q.exp_for(float(np.abs(arr).max()))
        q.wexp[name] = e
        rex = np.stack([Q.row_exponents(arr[l], e) for l in range(arr.shape[0])])
        scaled = arr / 2.0 ** (e + rex[..., None].astype(np.float64))
        cb = Q.lloyd_max(scaled, 16, 0)
        idx = Q.quantize_to_codebook(scaled, cb, 0)
        q.codebooks[name], q.indices[name], q.rowexp[name] = cb, idx, rex
        q.weights[name] = cb[idx]
    q.sig_tables = [sigmoid_table(sites["zl"][l]) for l in range(m.cfg.layers)]

    # Experts: the router is ternary at one scale per layer (the trainer's
    # TERNARY_ONE, so the ROM's exact block sums reproduce its argmax), and
    # the expert tensors were quantized above with an experts axis in front -
    # ternary_rows and row_exponents both work per row whatever leads.
    q.experts = getattr(m, "experts", 0)
    if q.experts:
        rt = ternary_rows(np.stack(m.router))
        assert rt is not None, "router must be ternary (train.TERNARY_ONE)"
        t, rowexp = rt
        q.router_t = t.astype(np.int64)             # (L, E, dim); scale irrelevant
    return q


def mv(q, name, l, x, in_exp, out_exp, e=None):
    """One matvec plus its per-row requant, on whichever kernel the tensor
    takes: block sums for ternary, product tables otherwise. e selects an
    expert's slice of an experts-major tensor."""
    w = q.weights[name][l] if e is None else q.weights[name][l][e]
    rowexp = q.rowexp[name][l] if e is None else q.rowexp[name][l][e]
    if q.binary.get(name):
        acc = Q.matvec_blocks(w, x, BINARY_BLOCK, TERNARY_ACC_SHIFT)
        acc_shift = TERNARY_ACC_SHIFT
    elif q.ternary.get(name):
        acc = Q.matvec_blocks(w, x, TERNARY_BLOCK, TERNARY_ACC_SHIFT)
        acc_shift = TERNARY_ACC_SHIFT
    else:
        acc = Q.matvec(w, x)
        acc_shift = ACC_SHIFT
    return Q.requant_rows(acc, q.wexp[name] + in_exp + acc_shift, rowexp, out_exp)


def route(q, l, xf):
    """The expert for this token: argmax over exact ternary block sums of the
    router, ties to the lowest index - what the ROM's compare does."""
    return int(np.argmax(Q.matvec_blocks(q.router_t[l], xf, TERNARY_BLOCK, 0)))


class QState5:
    def __init__(self, cfg):
        self.h = np.zeros((cfg.layers, cfg.dim), dtype=np.int64)


def forward_q5(q, st, token):
    """The integer step the cartridge performs. No position anywhere."""
    c = q.cfg
    ex = q.site("x")
    x = Q.requant(q.weights["tok_emb"][token].astype(np.int64),
                  q.wexp["tok_emb"], ex)
    for l in range(c.layers):
        exb = q.site("xb_att", l)
        xb = Q.rmsnorm(x, q.weights["rms_att"][l], q.wexp["rms_att"], exb)

        ezl, eh = q.site("zl", l), q.site("h", l)
        zl = mv(q, "wz", l, xb, exb, ezl)
        zg = q.sig_tables[l][zl.astype(np.int64) + 128]                     # u8, Q0.8
        ht = mv(q, "wh", l, xb, exb, eh)
        s = zg * ht.astype(np.int64) + (256 - zg) * st.h[l]                 # |s| <= 32512
        st.h[l] = Q.sat8(Q.shr_round(s, 8))

        ao = mv(q, "wo", l, st.h[l], eh, ex)
        x = Q.add_requant(x, ex, ao, ex, ex)

        exf = q.site("xb_ffn", l)
        xf = Q.rmsnorm(x, q.weights["rms_ffn"][l], q.wexp["rms_ffn"], exf)
        e1, ehb = q.site("h1", l), q.site("hb", l)
        if getattr(q, "experts", 0):
            # One expert of half the hidden: 176 outputs fit a bank whole and
            # 176 inputs fit int16 exactly, so neither matvec splits.
            ex_ = route(q, l, xf)
            a = mv(q, "w1", l, xf, exf, e1, e=ex_)
            u = Q.sat8(shr_round_any(
                np.maximum(a.astype(np.int64), 0) ** 2, ehb - 2 * e1))
            w2o = mv(q, "w2", l, u, ehb, ex, e=ex_)
            x = Q.add_requant(x, ex, w2o, ex, ex)
            continue
        a = mv(q, "w1", l, xf, exf, e1)
        u = Q.sat8(shr_round_any(
            np.maximum(a.astype(np.int64), 0) ** 2, ehb - 2 * e1))
        if q.ternary.get("w2") or q.binary.get("w2"):
            # Two input halves, each exact, each requantized and added: the
            # cartridge's order, so the two saturations happen where its do.
            blk = BINARY_BLOCK if q.binary.get("w2") else TERNARY_BLOCK
            split = (W2_SPLIT_BLOCKS_BIN if q.binary.get("w2") else W2_SPLIT_BLOCKS) * blk
            t = q.weights["w2"][l]
            for lo, hi in ((0, split), (split, c.hidden)):
                acc = Q.matvec_blocks(t[:, lo:hi], u[lo:hi], blk,
                                      TERNARY_ACC_SHIFT)
                part = Q.requant_rows(acc, q.wexp["w2"] + ehb + TERNARY_ACC_SHIFT,
                                      q.rowexp["w2"][l], ex)
                x = Q.add_requant(x, ex, part, ex, ex)
        else:
            w2o = mv(q, "w2", l, u, ehb, ex)
            x = Q.add_requant(x, ex, w2o, ex, ex)

    exbf = q.site("xb_final")
    xb = Q.rmsnorm(x, q.weights["rms_final"], q.wexp["rms_final"], exbf)
    if getattr(q, "binary_cls", False):
        return Q.matvec_blocks(q.weights["tok_emb"], xb, BINARY_CLS_BLOCK,
                               TERNARY_ACC_SHIFT)
    if getattr(q, "ternary_cls", False):
        # Exact sums, so the blocking is documentation: five, as the planes.
        return Q.matvec_blocks(q.weights["tok_emb"], xb, TERNARY_CLS_BLOCK,
                               TERNARY_ACC_SHIFT)
    return q.weights["tok_emb"].astype(np.int64) @ xb.astype(np.int64)


def generate_q5(q, tok, prompt, steps=48, state=None, pick=None):
    st = state or QState5(q.cfg)
    ids = tok.encode(prompt)
    t, out, prev, text = ids[0], [], None, []
    for pos in range(steps):
        logits = forward_q5(q, st, t)
        if pos + 1 < len(ids):
            nxt = ids[pos + 1]
        elif pick is not None:
            nxt = pick(logits, out)
        else:
            nxt = int(logits.argmax())
        if nxt == EOS:
            break
        out.append(nxt)
        text.append(tok.decode(nxt, prev))
        prev, t = nxt, nxt
    return out, "".join(text)
