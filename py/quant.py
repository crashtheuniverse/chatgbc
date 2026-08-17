"""Integer twin of reference.py - the exact arithmetic the SM83 code performs.

Design choices, all driven by what the SM83 can do cheaply:

* **Symmetric int8, range [-127, 127].** No zero point, so a product is a plain
  signed multiply with no correction term.
* **Power-of-two scales only.** Every value is `int * 2**exp`. Rescaling is
  therefore a shift, never a divide, and never a multiply by a float.
* **Static, calibrated exponents.** Each tensor site has one exponent baked in at
  export time, measured offline over real prompts. The ROM never searches for a
  max or computes a dynamic shift; it shifts by a constant and saturates. This is
  the single biggest simplification in the whole design.
* **int24 accumulators.** Worst case is 172 * 127 * 127 = 2.77M, inside signed
  24-bit (+/-8.39M), so the ROM can accumulate exactly and never overflow.
* **Table-driven nonlinearities.** rsqrt, exp and sigmoid become ROM lookups.

Everything here is plain integer arithmetic on numpy int32/int64. Nothing in
this file may use a float once weights are quantized.
"""

from dataclasses import dataclass, field

import numpy as np

import reference as ref

QMAX = 127
# Products are halved before accumulating, which keeps the running sum inside
# signed 16-bit and lets the kernel drop the third accumulator byte entirely.
# The cost is one bit per product, rounded at export time: over 172 terms that
# is ~4 of accumulator error against a requantization LSB of ~32. Two bits, not
# one: one bit fits real activations (peak 20,767 of 32,767) but not an adversarial
# uniform-random vector, and the extra bit costs nothing measurable.
ACC_SHIFT = 2
ACC_MAX = (1 << 15) - 1          # signed int16, the accumulator the ROM provides
SIG_SHIFT = 4                    # sigmoid table input is Q4.4, i.e. +/-8.0
SIG_BITS = 8                     # sigmoid table output is Q0.8
EXP_BITS = 12                    # softmax exp table output is Q0.12
# 14, not 15, so every table entry stays inside signed 16-bit: the SM83 helper
# multiplies signed operands, and a value above 32767 would read as negative.
RSQRT_BITS = 14
RECIP_BITS = 14                  # same constraint for the softmax reciprocal


# --- shared helpers ---------------------------------------------------------

def shr_round(x, s):
    """Arithmetic right shift with round-half-up. One `add` then shifts in ASM."""
    if s <= 0:
        return np.asarray(x, dtype=np.int64) << -s
    x = np.asarray(x, dtype=np.int64)
    return (x + (1 << (s - 1))) >> s


def rescale(value, from_exp, to_exp):
    """Reinterpret an integer from one power-of-two scale to another.

    Every scale change in the model goes through here. Writing the shift out by
    hand at each site is how sign errors creep in: a value carrying `from_exp`
    means `value * 2**from_exp`, so landing on `to_exp` is a shift right by
    `to_exp - from_exp`, and never the other way round.
    """
    return shr_round(value, to_exp - from_exp)


def sat8(x):
    return np.clip(x, -QMAX, QMAX).astype(np.int8)


def quantize(x, exp):
    """Float -> int8 at a known power-of-two scale."""
    return sat8(np.round(np.asarray(x, dtype=np.float64) / 2.0**exp))


def exp_for(maxabs):
    """Smallest exponent e with maxabs / 2**e <= 127."""
    if maxabs <= 0:
        return 0
    e = 0
    while maxabs / 2.0**e > QMAX:
        e += 1
    while maxabs / 2.0 ** (e - 1) <= QMAX:
        e -= 1
    return e


# --- lookup tables (exported to ROM verbatim) -------------------------------

def build_tables():
    """The three nonlinearities, as the exact tables both sides will use."""
    # 1/sqrt(f) for f in [0.25, 1), indexed by the top 8 bits of a normalized
    # sum of squares. Only indices 64..255 are ever reached.
    rsqrt = np.zeros(256, dtype=np.uint16)
    for i in range(1, 256):
        rsqrt[i] = min(0xFFFF, round((1 << RSQRT_BITS) / np.sqrt((i + 0.5) / 256.0)))

    # sigmoid over Q4.4 input, i.e. x in [-8, 8), as Q0.8.
    sigmoid = np.zeros(256, dtype=np.uint8)
    for i in range(256):
        x = (i - 128) / 2.0**SIG_SHIFT
        sigmoid[i] = min(255, round((1 << SIG_BITS) / (1.0 + np.exp(-x))))

    # exp(-i/16) as Q0.12, for softmax after subtracting the row max.
    expt = np.zeros(256, dtype=np.uint16)
    for i in range(256):
        expt[i] = round((1 << EXP_BITS) * np.exp(-i / 16.0))

    # 1/f for f in [0.5, 1), indexed by the top 8 bits of a normalized total.
    # Softmax normalizes with this instead of dividing - the SM83 has no divide
    # instruction, and this is the same normalize-and-index trick as rsqrt.
    recip = np.zeros(256, dtype=np.uint16)
    for i in range(128, 256):
        recip[i] = min(0x7FFF, round((1 << RECIP_BITS) / ((i + 0.5) / 256.0)))

    return {"rsqrt": rsqrt, "sigmoid": sigmoid, "exp": expt, "recip": recip}


TABLES = build_tables()


# --- integer kernels; each maps 1:1 onto an assembly routine ----------------

def matvec(w, x, acc_check=True):
    """int8 matrix (out, in) times int8 vector -> exact int32 accumulators.

    The ROM walks this input-major: for each input j it builds a 256-entry table
    of x[j] * w for every possible weight byte, then sweeps the outputs adding
    table lookups into int24 accumulators.
    """
    prod = w.astype(np.int64) * x.astype(np.int64)[None, :]
    acc = shr_round(prod, ACC_SHIFT).sum(axis=1)
    if acc_check and np.abs(acc).max() > ACC_MAX:
        raise OverflowError(f"accumulator {np.abs(acc).max()} exceeds int16")
    return acc


def requant(acc, from_exp, to_exp):
    """int32 accumulator -> int8 at a calibrated constant shift, saturating."""
    return sat8(rescale(acc, from_exp, to_exp))


def requant_rows(acc, base_from, rowexp, to_exp):
    """As requant, but each output carries its own extra power-of-two scale."""
    out = np.empty(acc.shape, dtype=np.int64)
    for i in range(acc.shape[0]):
        out[i] = shr_round(acc[i], to_exp - (base_from + int(rowexp[i])))
    return sat8(out)


def rmsnorm(x, w_int, w_exp, out_exp):
    """x_hat = x / rms(x), then elementwise weight. The rms ratio is scale-free,
    so the input exponent cancels and never enters the arithmetic."""
    x = x.astype(np.int64)
    n = x.size
    ss = int((x * x).sum())
    if ss == 0:
        return np.zeros(n, dtype=np.int8)

    # Normalize ss to 2**e * f with f in [0.25, 1) and e even, so that
    # sqrt(2**e) is an exact shift.
    e = int(ss).bit_length()
    if e & 1:
        e += 1
    idx = ss >> (e - 8) if e >= 8 else ss << (8 - e)
    r = int(TABLES["rsqrt"][idx])          # ~ 2**15 / sqrt(f)

    # x_hat = x * sqrt(n) / sqrt(ss) held as Q11; sqrt(n) = 2**3 for dim 64.
    # With RSQRT_BITS 14 and root_n_shift 3 the constant part cancels, leaving a
    # shift of exactly e/2 - which is why the assembly needs no bias term here.
    root_n_shift = int(np.log2(n)) // 2
    xh = shr_round(x * r, RSQRT_BITS - 11 - root_n_shift + e // 2)

    # Fold in the elementwise weight and land back on int8.
    prod = xh * w_int.astype(np.int64)
    return sat8(rescale(prod, -11 + w_exp, out_exp))


def silu_mul(h1, h1_exp, h3, h3_exp, out_exp):
    """SwiGLU: silu(h1) * h3, with sigmoid from the Q4.4 table."""
    # Bring h1 to Q4.4 so it can index the sigmoid table, saturating at +/-8.
    idx = np.clip(shr_round(h1.astype(np.int64), -h1_exp - SIG_SHIFT), -128, 127) + 128
    sig = TABLES["sigmoid"][idx.astype(np.int32)].astype(np.int64)

    silu = h1.astype(np.int64) * sig       # exponent h1_exp - SIG_BITS
    prod = silu * h3.astype(np.int64)
    return sat8(rescale(prod, h1_exp - SIG_BITS + h3_exp, out_exp))


def softmax_weights(scores, score_exp):
    """Scores -> Q0.12 weights summing to ~4096, using the exp table.

    Table steps are 1/16 in real units, so the shift below converts a score
    difference into table index units.
    """
    s = scores.astype(np.int64)
    d = s.max() - s                        # >= 0, exponent score_exp
    idx = np.clip(shr_round(d, -score_exp - 4), 0, 255)
    e = TABLES["exp"][idx.astype(np.int32)].astype(np.int64)
    total = int(e.sum())
    if total == 0:
        e = np.ones_like(e)
        total = int(e.sum())

    # Normalize total to 2**bits * f with f in [0.5, 1), look up 1/f, and fold
    # the exponent into the shift. One table read per head instead of a divide.
    bits = total.bit_length()
    idx = total >> (bits - 8) if bits >= 8 else total << (8 - bits)
    r = int(TABLES["recip"][idx])
    return shr_round(e * r, RECIP_BITS + bits - EXP_BITS)


# --- quantized model --------------------------------------------------------

@dataclass
class Site:
    """A calibrated activation site: values are int8 * 2**exp."""
    exp: int = 0
    observed: float = 0.0


# Big matmuls get codebook quantization; the tiny elementwise rmsnorm gains stay
# int8 because they cost 320 bytes in total and sit outside every hot loop.
MATMULS = ("tok_emb", "wq", "wk", "wv", "wo", "w1", "w2", "w3")


@dataclass
class QuantModel:
    cfg: ref.Config
    weights: dict = field(default_factory=dict)   # int8 values actually multiplied
    wexp: dict = field(default_factory=dict)
    sites: dict = field(default_factory=dict)
    codebooks: dict = field(default_factory=dict)  # name -> int8[2**bits]
    indices: dict = field(default_factory=dict)    # name -> codebook index per weight
    rowexp: dict = field(default_factory=dict)     # name -> extra exponent per output row
    bits: dict = field(default_factory=dict)       # name -> weight width actually used
    weight_bits: int = 8

    def w(self, name, layer=None):
        return self.weights[name] if layer is None else self.weights[name][layer]

    def e(self, name):
        return self.wexp[name]

    def rex(self, name, layer=None):
        return self.rowexp[name] if layer is None else self.rowexp[name][layer]

    def site(self, name, layer):
        return self.sites[f"{name}.{layer}"].exp


def lloyd_max(values, levels, exp, iters=40):
    """Non-uniform int8 codebook for a weight tensor.

    The ROM builds its product table as `table[u] = x_j * codebook[u]`, so the
    16 representable weights can sit anywhere in int8 rather than on a uniform
    grid - a strictly better 4-bit quantizer for the same runtime cost.
    """
    v = np.asarray(values, dtype=np.float64).ravel() / 2.0**exp
    lo, hi = v.min(), v.max()
    cb = np.linspace(lo, hi, levels)
    for _ in range(iters):
        idx = np.abs(v[:, None] - cb[None, :]).argmin(axis=1)
        for k in range(levels):
            sel = v[idx == k]
            if sel.size:
                cb[k] = sel.mean()
        cb.sort()
    cb = np.clip(np.round(cb), -QMAX, QMAX)
    cb = np.unique(cb)
    while cb.size < levels:  # keep the codebook a fixed size
        cb = np.append(cb, cb[-1] + 1)
    return cb[:levels].astype(np.int8)


def uniform_codebook(levels):
    """cb[u] = (u - levels/2) * step, with step a power of two.

    This is what lets the ROM build its product table with shifts and adds
    alone: table[0] = -(x << 7), then step through by (x << 4). A Lloyd-Max
    codebook would need 16 real multiplies per input instead.
    """
    step = 256 // levels
    return np.array([(u - levels // 2) * step for u in range(levels)], dtype=np.int16) \
        .clip(-QMAX, QMAX).astype(np.int8)


def quantize_to_codebook(arr, codebook, exp):
    v = np.asarray(arr, dtype=np.float64) / 2.0**exp
    idx = np.abs(v[..., None] - codebook[None, :].astype(np.float64)).argmin(axis=-1)
    return idx.astype(np.uint8)


def row_exponents(mat, base_exp):
    """One power-of-two scale per output row.

    The product table is shared by every output, so a per-row scale cannot live
    in the table - but requantization already runs once per output, so folding a
    per-row shift in there is free. It buys back most of the accuracy that 4-bit
    weights give up, for one extra byte per output row.
    """
    rows = np.abs(mat.reshape(mat.shape[0], -1)).max(axis=1)
    return np.array([exp_for(r) - base_exp if r > 0 else 0 for r in rows], dtype=np.int8)


def quantize_model(model, sites, weight_bits=8, bits_override=None, uniform=False,
                   fixed_codebook=None):
    """`bits_override` sets per-tensor widths. The classifier is the natural
    exception: with 512 outputs it amortizes a 256-entry product table down to
    ~8 cycles/MAC, so 8-bit costs little there and it is what decides argmax."""
    q = QuantModel(cfg=model.cfg, sites=sites)
    q.weight_bits = weight_bits
    override = bits_override or {}
    for name in ("tok_emb", "rms_att", "wq", "wk", "wv", "wo",
                 "rms_ffn", "w1", "w2", "w3", "rms_final"):
        arr = getattr(model, name).astype(np.float64)
        if name == "wq":
            # Fold attention's 1/sqrt(head_size) into wq. RoPE is a rotation and
            # preserves scale, so pre-scaling q is exactly equivalent - and it
            # removes a multiply from the innermost attention loop for free.
            arr = arr / np.sqrt(model.cfg.head_size)
        e = exp_for(float(np.abs(arr).max()))
        q.wexp[name] = e
        bits = override.get(name, weight_bits)
        q.bits[name] = bits
        if bits >= 8 or name not in MATMULS:
            q.weights[name] = quantize(arr, e)
            q.rowexp[name] = np.zeros(arr.shape[:-1], dtype=np.int8)
            continue

        # Per-output-row scales, then one shared codebook over the normalized
        # weights. Layered tensors are (layers, out, in); tok_emb is (vocab, in).
        rex = np.stack([row_exponents(arr[l], e) for l in range(arr.shape[0])]) \
            if arr.ndim == 3 else row_exponents(arr, e)
        scaled = arr / 2.0 ** (e + rex[..., None].astype(np.float64))
        if fixed_codebook is not None:
            cb = fixed_codebook
        elif uniform:
            cb = uniform_codebook(1 << bits)
        else:
            cb = lloyd_max(scaled, 1 << bits, 0)
        idx = quantize_to_codebook(scaled, cb, 0)
        assert idx.max() < (1 << bits)
        q.codebooks[name], q.indices[name], q.rowexp[name] = cb, idx, rex
        q.weights[name] = cb[idx]   # int8 codebook values; the row scale is applied at requant

    for alias, src in (("wcls", "tok_emb"),):
        for d in (q.weights, q.wexp, q.rowexp, q.codebooks, q.indices, q.bits):
            if src in d:
                d[alias] = d[src]
    return q


def rope_table(seq_len, head_size):
    """(cos, sin) per (position, rotation pair) as Q0.15, exported to ROM."""
    pairs = head_size // 2
    tbl = np.zeros((seq_len, pairs, 2), dtype=np.int16)
    for pos in range(seq_len):
        for i in range(pairs):
            val = pos * (1.0 / (10000.0 ** ((2 * i) / head_size)))
            tbl[pos, i, 0] = int(np.round(np.cos(val) * 32767))
            tbl[pos, i, 1] = int(np.round(np.sin(val) * 32767))
    return tbl


def rope_q(vec, pos, tbl):
    """In-place RoPE on an int8 vector. A rotation preserves magnitude, so the
    site exponent is unchanged."""
    pairs = tbl.shape[1]
    out = vec.astype(np.int64).copy()
    for i in range(0, vec.size, 2):
        c, s = tbl[pos, (i // 2) % pairs]
        v0, v1 = out[i], out[i + 1]
        out[i] = shr_round(v0 * int(c) - v1 * int(s), 15)
        out[i + 1] = shr_round(v0 * int(s) + v1 * int(c), 15)
    return sat8(out)


def add_requant(a, ea, b, eb, eout):
    """Residual add of two int8 vectors at different exponents."""
    total = shr_round(a.astype(np.int64), eout - ea) + shr_round(b.astype(np.int64), eout - eb)
    return sat8(total)


class QState:
    def __init__(self, cfg, seq_len):
        self.seq_len = seq_len
        self.k = np.zeros((cfg.n_layers, seq_len, cfg.kv_dim), dtype=np.int8)
        self.v = np.zeros((cfg.n_layers, seq_len, cfg.kv_dim), dtype=np.int8)


def forward_q(q, state, token, pos, rtbl, window=None):
    """Integer-only decode step. Returns int32 logits; greedy decode just needs
    their argmax, so the ROM never has to store or rescale them."""
    c = q.cfg
    hs, kvm = c.head_size, c.kv_mul
    ex = q.site("x", 0)

    x = requant(q.w("tok_emb")[token].astype(np.int32),
                q.e("tok_emb") + int(q.rex("tok_emb")[token]), ex)

    for l in range(c.n_layers):
        exb = q.site("xb_att", l)
        xb = rmsnorm(x, q.w("rms_att", l), q.e("rms_att"), exb)

        eq_, ek_, ev_ = q.site("q", l), q.site("k", l), q.site("v", l)
        qv = requant_rows(matvec(q.w("wq", l), xb), q.e("wq") + exb + ACC_SHIFT, q.rex("wq", l), eq_)
        kv = requant_rows(matvec(q.w("wk", l), xb), q.e("wk") + exb + ACC_SHIFT, q.rex("wk", l), ek_)
        vv = requant_rows(matvec(q.w("wv", l), xb), q.e("wv") + exb + ACC_SHIFT, q.rex("wv", l), ev_)

        qv = rope_q(qv, pos, rtbl)
        kv = rope_q(kv, pos, rtbl)
        state.k[l, pos], state.v[l, pos] = kv, vv

        eout = q.site("att_out", l)
        xb2 = np.zeros(c.dim, dtype=np.int8)
        for h in range(c.n_heads):
            qh = qv[h * hs : (h + 1) * hs].astype(np.int32)
            base = (h // kvm) * hs
            # A sliding window drops the oldest positions instead of growing.
            lo = 0 if window is None else max(0, pos + 1 - window)
            keys = state.k[l, lo : pos + 1, base : base + hs].astype(np.int32)
            att = softmax_weights(keys @ qh, eq_ + ek_)
            vals = state.v[l, lo : pos + 1, base : base + hs].astype(np.int64)
            # sum(att) == 1<<EXP_BITS, so this stays inside int24.
            acc = (att[:, None] * vals).sum(axis=0)
            xb2[h * hs : (h + 1) * hs] = sat8(rescale(acc, ev_ - EXP_BITS, eout))

        wo = requant_rows(matvec(q.w("wo", l), xb2), q.e("wo") + eout + ACC_SHIFT, q.rex("wo", l), ex)
        x = add_requant(x, ex, wo, ex, ex)

        exf = q.site("xb_ffn", l)
        xb = rmsnorm(x, q.w("rms_ffn", l), q.e("rms_ffn"), exf)

        e1, e3, eh = q.site("h1", l), q.site("h3", l), q.site("hb", l)
        h1 = requant_rows(matvec(q.w("w1", l), xb), q.e("w1") + exf + ACC_SHIFT, q.rex("w1", l), e1)
        h3 = requant_rows(matvec(q.w("w3", l), xb), q.e("w3") + exf + ACC_SHIFT, q.rex("w3", l), e3)
        hb = silu_mul(h1, e1, h3, e3, eh)

        w2 = requant_rows(matvec(q.w("w2", l), hb), q.e("w2") + eh + ACC_SHIFT, q.rex("w2", l), ex)
        x = add_requant(x, ex, w2, ex, ex)

    xf = rmsnorm(x, q.w("rms_final"), q.e("rms_final"), q.site("xb_final", 0))
    acc = matvec(q.w("wcls"), xf, acc_check=False)

    # Each vocabulary row carries its own scale, so the raw accumulators are not
    # comparable. Shift them onto a common exponent before the argmax; the ROM
    # does exactly this while streaming, keeping only the running best.
    rex = q.rex("wcls").astype(np.int64)
    return np.array([int(a) << int(r) for a, r in zip(acc, rex - rex.min())], dtype=np.int64)


# --- calibration ------------------------------------------------------------

CAL_PROMPTS = [
    "",
    "Once upon a time",
    "Lily and Tom went to the park",
    "The little dog was very happy because",
    "One day, a girl named Sara found a red box",
    "Tim was sad. His mom said",
]


def calibrate(model, prompts=CAL_PROMPTS, steps=64, seq_len=64, headroom=1.15):
    """Record the true dynamic range at every activation site over real prompts,
    in float, then pick the smallest power-of-two scale that covers it.

    `headroom` pads the observed maxima, since the exponents are baked into the
    ROM and a prompt we never calibrated on must not saturate.
    """
    c = model.cfg
    hs, kvm = c.head_size, c.kv_mul
    obs = {}

    def note(name, layer, arr):
        key = f"{name}.{layer}"
        obs[key] = max(obs.get(key, 0.0), float(np.abs(arr).max()))

    tok = ref.Tokenizer()
    for prompt in prompts:
        state = ref.State(c, seq_len)
        toks = tok.encode(prompt)
        token = toks[0]

        for pos in range(min(steps, seq_len)):
            x = model.tok_emb[token].copy()
            for l in range(c.n_layers):
                xb = ref.rmsnorm(x, model.rms_att[l])
                note("xb_att", l, xb)
                qv = (model.wq[l] @ xb) / np.sqrt(hs)   # 1/sqrt(hs) folded into wq
                kv = model.wk[l] @ xb
                vv = model.wv[l] @ xb
                ref.rope(qv, pos, hs, c.dim)
                ref.rope(kv, pos, hs, c.kv_dim)
                note("q", l, qv)
                note("k", l, kv)
                note("v", l, vv)
                state.k[l, pos], state.v[l, pos] = kv, vv

                xb2 = np.zeros(c.dim, dtype=np.float32)
                for h in range(c.n_heads):
                    qh = qv[h * hs : (h + 1) * hs]
                    base = (h // kvm) * hs
                    att = ref.softmax(state.k[l, : pos + 1, base : base + hs] @ qh)
                    xb2[h * hs : (h + 1) * hs] = att @ state.v[l, : pos + 1, base : base + hs]
                note("att_out", l, xb2)

                x = x + model.wo[l] @ xb2
                note("x", 0, x)

                xbf = ref.rmsnorm(x, model.rms_ffn[l])
                note("xb_ffn", l, xbf)
                h1 = model.w1[l] @ xbf
                h3 = model.w3[l] @ xbf
                note("h1", l, h1)
                note("h3", l, h3)
                hb = h1 / (np.float32(1.0) + np.exp(-h1, dtype=np.float32)) * h3
                note("hb", l, hb)
                x = x + model.w2[l] @ hb
                note("x", 0, x)

            xf = ref.rmsnorm(x, model.rms_final)
            note("xb_final", 0, xf)
            logits = model.wcls @ xf
            nxt = toks[pos + 1] if pos + 1 < len(toks) else int(logits.argmax())
            if nxt == ref.EOS:
                break
            token = nxt

    return {k: Site(exp_for(v * headroom), v) for k, v in obs.items()}


def generate_q(q, tokenizer, prompt="", steps=64, seq_len=64, window=None):
    state = QState(q.cfg, seq_len)
    rtbl = rope_table(seq_len, q.cfg.head_size)
    toks = tokenizer.encode(prompt)
    token = toks[0]

    for pos in range(min(steps, seq_len)):
        logits = forward_q(q, state, token, pos, rtbl, window)
        nxt = toks[pos + 1] if pos + 1 < len(toks) else int(logits.argmax())
        if nxt == ref.EOS:
            break
        yield nxt, tokenizer.decode(nxt, token)
        token = nxt


if __name__ == "__main__":
    import sys

    model, tok = ref.Model(), ref.Tokenizer()
    print("calibrating...", flush=True)
    sites = calibrate(model)
    q = quantize_model(model, sites)

    print("\nweight exponents:")
    for k, v in q.wexp.items():
        print(f"  {k:<10} 2^{v}")
    print("\nactivation sites (observed max -> exponent):")
    for k in sorted(sites):
        print(f"  {k:<14} {sites[k].observed:8.3f}  2^{sites[k].exp}")

    prompt = sys.argv[1] if len(sys.argv) > 1 else "Once upon a time"
    print(f"\nprompt {prompt!r}\n")
    print("fp32 : ", end="")
    print("".join(t for _, t in ref.generate(model, tok, prompt, 64, 64)).replace("\n", "\\n"))
    print("int8 : ", end="")
    print("".join(t for _, t in generate_q(q, tok, prompt, 64, 64)).replace("\n", "\\n"))
