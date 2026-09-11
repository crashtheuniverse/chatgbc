"""PIP5 checkpoint -> ROM blobs + generated assembly, for the minGRU app.

Same mechanics that shipped v0.3, same discipline: everything the kernels
consume is precomputed here - product tables, requant shifts as signed bytes,
sigmoid gate tables baked per calibrated exponent - and py/twin5.py is the
authority this output must reproduce bit for bit on the cartridge.

What is gone against the v0.4 exporter: RoPE, the exp/recip softmax tables,
the score LUTs, every KV constant. What is new: per-layer gate tables
(sigmoid at the layer's zl exponent, Q0.8) and the ReLU^2 shift, one signed
byte per layer.
"""

import os
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
ROOT = APP
sys.path.insert(0, str(ROOT / "py"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
# The app's shipping pair. Every entry point (golden5, census5, the tests)
# imports export5 before anything touches reference.Tokenizer, so setting the
# default here makes the app self-consistent with no environment required;
# PIP5 / CHATGBC_TOKENIZER still override for experiments.
os.environ.setdefault("CHATGBC_TOKENIZER",
                      str(ROOT / "models" / "tok_ts1024.bin"))
import quant as Q                # noqa: E402
import twin5                     # noqa: E402
from model5 import Model5, Tokenizer, UNK, BOS, EOS   # noqa: E402

BLOBS = APP / "build" / "blobs"
WEIGHTS_ASM = APP / "src" / "weights.asm"
MODEL_INC = APP / "src" / "model.inc"

CKPT = Path(os.environ.get("PIP5", ROOT / "models" / "ts3L_v1024.bin"))

# The story generator. A chat build (Rei, the conversation partner) sets
# CHAT: the newline piece then ends a turn and the keyboard becomes a
# message box; here the model writes until the step count runs out.
CHAT = os.environ.get("CHATGBC_CHAT") == "1"
PROMPT = "> hello\n" if CHAT else "Once upon a time"
HLUT_BASE = 0x80
MATS = twin5.MATS                # wz wh wo w1 w2

_blobs = []


def blob(name, data, rom0=True, attach=None):
    """A blob becomes its own section - ROM0 or a bank of rgblink's choosing -
    unless `attach` names another blob, in which case it is placed inside
    THAT blob's section: the guarantee a per-row shift table needs to sit in
    the same bank as its matrix, which is the bank still mapped when the
    requant that reads it runs. ROM0 could not hold the shifts of a 96-wide
    model with 256-wide experts; the banks can, and the code did not move."""
    data = bytes(data)
    (BLOBS / f"{name}.bin").write_bytes(data)
    _blobs.append((name, len(data), rom0, attach))
    return name


def blob_split(name, data, rows):
    stride = len(data) // rows
    per_bank = (0x4000 // stride) * stride
    parts = [data[i:i + per_bank] for i in range(0, len(data), per_bank)]
    for i, part in enumerate(parts):
        blob(f"{name}_p{i}", part, rom0=False)
    return len(parts), per_bank // stride


def weight_blob(name, idx):
    offsets = idx.T.astype(np.int32) * 2 + HLUT_BASE
    assert offsets.max() < 0x100
    return blob(name, offsets.astype(np.uint8).tobytes(), rom0=False)


# The ternary block kernel's code space: the 27 coefficient triples in the
# order src/matvec3.asm walks them - the snake from (-1,-1,-1), one
# coefficient step at a time. py/tests/test_blockbench.py is the reference.
_BK3_STEPS = ([0, 0, 4, 2, 2, 4, 0, 0] + [8] + [2, 2, 6, 0, 0, 6, 2, 2] + [8]
              + [0, 0, 4, 2, 2, 4, 0, 0])
_STEP_DELTA = {0: (0, +1), 2: (0, -1), 4: (1, +1), 6: (1, -1),
               8: (2, +1), 10: (2, -1)}


def block_codes():
    coef, order = [-1, -1, -1], [(-1, -1, -1)]
    for step in _BK3_STEPS:
        i, d = _STEP_DELTA[step]
        coef[i] += d
        order.append(tuple(coef))
    assert len(set(order)) == 27
    return {trip: k for k, trip in enumerate(order)}


def block_weight_blob(name, t):
    """Ternary (out, in) in {-1, 0, 1} -> input-major block codes: for each
    block of three inputs, one byte per output, already an HRAM offset. A
    partial last block is padded with zero coefficients."""
    codes = block_codes()
    out, n_in = t.shape
    pad = (-n_in) % 3
    tp = np.concatenate([t, np.zeros((out, pad), dtype=t.dtype)], axis=1)
    blocks = tp.reshape(out, -1, 3)
    data = bytearray()
    for b in range(blocks.shape[1]):
        for o in range(out):
            data.append(codes[tuple(int(v) for v in blocks[o, b])] * 2 + HLUT_BASE)
    assert len(data) <= 0x4000, f"{name}: {len(data)} bytes exceeds a bank"
    return blob(name, bytes(data), rom0=False)


def gray_position(pattern):
    """The table position p whose gray code p ^ (p >> 1) is `pattern`."""
    p = 0
    while pattern:
        p ^= pattern
        pattern >>= 1
    return p


def binary_weight_blob(name, b, block=twin5.BINARY_BLOCK, hram=True):
    """One-bit (out, in) in {-1, +1} -> input-major block codes: for each
    block of `block` inputs, one byte per output - the Gray position of the
    row's sign pattern (bit i set = +1 on input i), as an HRAM offset for the
    16-entry kernel or the bare position for the 256-entry one. No padding:
    every width is a multiple of the block."""
    out, n_in = b.shape
    assert n_in % block == 0, f"{name}: {n_in} inputs is not a multiple of {block}"
    blocks = (b > 0).reshape(out, n_in // block, block)
    data = bytearray()
    for k in range(blocks.shape[1]):
        for o in range(out):
            pattern = 0
            for i in range(block):
                if blocks[o, k, i]:
                    pattern |= 1 << i
            # The HRAM kernel walks its table in Gray order; the WRAM planes
            # are built by doubling in natural order, so their code is the
            # pattern itself.
            data.append(gray_position(pattern) * 2 + HLUT_BASE if hram else pattern)
    assert len(data) <= 0x4000, f"{name}: {len(data)} bytes exceeds a bank"
    return blob(name, bytes(data), rom0=False)


CLS4_ROW = 16               # bytes a token's row takes in the output-major stream


def ternary_row_blob(name, t):
    """Ternary (out, in) in {-1, 0, 1} -> OUTPUT-major codes for the block-4
    tables of src/cls4.asm: per output one row of CLS4_ROW bytes, byte k the
    low address byte of block k's int16 entry, 2 * sum((c_i + 1) * 3^i) over
    the block's four inputs, 0..160. A partial last block is padded with zero
    coefficients (digit 1), so the input past the vector never reaches a sum
    whatever it holds.

    Odd rows carry their blocks in REVERSE order. The scan walks the sixteen
    table pages upward on an even token and downward on the odd one that
    follows, so the page register is already right when the next row starts
    and never needs resetting - two cycles an output, for a byte order that
    only this function and that scan know about."""
    out, n_in = t.shape
    pad = (-n_in) % 4
    tp = np.concatenate([t, np.zeros((out, pad), dtype=t.dtype)], axis=1)
    blocks = tp.reshape(out, -1, 4).astype(np.int64) + 1          # digits 0..2
    assert blocks.shape[1] == CLS4_ROW, (
        f"{name}: {blocks.shape[1]} blocks of four; the scan's token arithmetic "
        f"and its one WRAM bank of tables assume exactly {CLS4_ROW}")
    codes = (blocks * np.array([1, 3, 9, 27])).sum(axis=2) * 2      # (out, 16)
    assert codes.min() >= 0 and codes.max() <= 160
    codes[1::2] = codes[1::2, ::-1]
    assert out % 2 == 0, f"{name}: the scan takes tokens two at a time"
    data = codes.astype(np.uint8).tobytes()
    assert len(data) == out * CLS4_ROW <= 0x4000, f"{name}: {len(data)} bytes exceeds a bank"
    return blob(name, data, rom0=False)


def sbytes(values):
    return bytes(int(v) & 0xFF for v in values)


def product_lut(codebook):
    out = bytearray()
    for x in range(-128, 128):
        for w in codebook:
            out += int(Q.shr_round(x * int(w), Q.ACC_SHIFT)).to_bytes(
                2, "little", signed=True)
    assert len(out) == 256 * 16 * 2
    return bytes(out)


def nibble_luts():
    hi, lo = bytearray(), bytearray()
    for x in range(-128, 128):
        for u in range(16):
            hi += int(x * u * 4).to_bytes(2, "little", signed=True)
            lo += int(Q.shr_round(x * (u - 128), Q.ACC_SHIFT)).to_bytes(
                2, "little", signed=True)
    return bytes(hi), bytes(lo)


CAL_TEXT = ROOT / "models" / "tinystories" / "ts_valid_v1.txt"
CAL_FALLBACK = ["Once upon a time, there was a little girl named Lily. She "
                "liked to play in the park with her dog.",
                "Tom and Sam were best friends. One day they found a big red "
                "ball under a tree.",
                "The sun was warm and the sky was blue. A small bird sat on a "
                "branch and sang."]


def cal_prompts(n=6):
    """Held-out stories: the exponents baked into the ROM must cover what the
    model will actually see, and the first stories of the V1 validation file
    are text it never trained on. Without the corpus, three openers."""
    if not CAL_TEXT.exists():
        return CAL_FALLBACK
    text = CAL_TEXT.read_text(encoding="utf-8")
    stories = [s for s in text.split("\n\n") if s.strip()]
    return [s[:600] for s in stories[:n]]


def main():
    BLOBS.mkdir(parents=True, exist_ok=True)
    m = Model5(CKPT)
    tok = Tokenizer()
    c = m.cfg
    print(f"calibrating {CKPT.name}...", flush=True)
    sites = twin5.calibrate5(m, tok, cal_prompts())
    q = twin5.quantize5(m, sites)

    S = lambda n, l=None: q.site(n, l)      # noqa: E731
    lines, consts = [], []

    def const(name, value):
        consts.append(f"DEF {name} EQU {value}")

    const("DIM", c.dim)
    const("HIDDEN", c.hidden)
    const("N_LAYERS", c.layers)
    const("VOCAB", c.vocab)
    const("CB_LEVELS", 16)
    const("HLUT_BASE", f"${HLUT_BASE:02X}")
    const("X_EXP", S("x"))
    const("RSQRT_BITS", Q.RSQRT_BITS)

    # --- lookup tables ---
    blob("tbl_rsqrt", Q.TABLES["rsqrt"].astype("<u2").tobytes())
    qsq = (np.arange(257, dtype=np.int64) ** 2) // 4
    blob("tbl_qsq", qsq.astype("<u2").tobytes())

    # Gate tables: sigmoid at each layer's zl exponent, Q0.8, indexed zl+128.
    # Resident in ROM0 - the gate step sits between two banked matvecs and
    # having its table always mapped keeps the kernel free of switches.
    for l in range(c.layers):
        blob(f"sig_l{l}", q.sig_tables[l].astype(np.uint8).tobytes())

    # ReLU^2: u = sat8(shr_round(relu(a)^2, e_hb - 2*e_h1)), per layer. The
    # register path shifts right only; a negative count would need the old
    # scratch path, and is a calibration problem to see here.
    r2 = [S("hb", l) - 2 * S("h1", l) for l in range(c.layers)]
    assert min(r2) >= 0, f"relu2 shift {min(r2)} < 0"
    blob("r2_shift", sbytes(r2))

    # --- token embedding ---
    # A part holds a power of two rows - as many as fit a bank - so EmbedToken
    # takes the part as token >> EMB_ROW_BITS and the row as the remainder.
    # 256 rows of 64 fill a bank exactly; 96-wide rows get 128 a part.
    emb_bits = 0
    while (2 << emb_bits) * c.dim <= 0x4000 and (2 << emb_bits) <= c.vocab:
        emb_bits += 1
    emb_per = 1 << emb_bits
    emb_rows = q.weights["tok_emb"].astype(np.int8)
    emb_parts = -(-c.vocab // emb_per)
    for i in range(emb_parts):
        blob(f"emb_rows_p{i}", emb_rows[i * emb_per:(i + 1) * emb_per].tobytes(), rom0=False)
    assert c.dim in (64, 96, 128), "EmbedToken multiplies the row by DIM with shifts for these widths"
    const("EMB_PARTS", emb_parts)
    const("EMB_PER_PART", emb_per)
    const("EMB_ROW_BITS", emb_bits)
    # The embedding has one exponent, so its shift is one constant - not a
    # 512-byte table of the same byte, which is what used to live in ROM0.
    const("EMB_SHIFT", S("x") - q.wexp["tok_emb"])

    # --- classifier ---
    assert int(np.abs(q.rowexp["tok_emb"]).max()) == 0
    const("CLS_TERNARY", int(q.ternary_cls))
    const("CLS_BINARY", int(getattr(q, "binary_cls", False)))
    if getattr(q, "binary_cls", False):
        # Blocks of eight against 256-entry planes in the sum bank: a part is
        # 512 outputs (what the sums' stretch and the code arithmetic assume),
        # a block's codes are 512 bytes, the whole vocabulary's planes need
        # 512 bytes above the sums - so 2048 pieces would not fit the bank.
        per = 512
        assert c.vocab % per == 0 and c.dim % 8 == 0 and c.vocab * 2 + 512 <= 4096
        nparts = c.vocab // per
        b_cls = q.weights["tok_emb"].astype(np.int8)
        for i in range(nparts):
            binary_weight_blob(f"cls_w_p{i}", b_cls[i * per:(i + 1) * per],
                               block=twin5.BINARY_CLS_BLOCK, hram=False)
        const("CLS_BLOCKS8", c.dim // twin5.BINARY_CLS_BLOCK)
        blob("lut_cls_hi", bytes(1), rom0=False)
        blob("lut_cls_lo", bytes(1), rom0=False)
    elif q.ternary_cls:
        # Output-major over sixteen block-of-four tables (src/cls4.asm): a
        # token is one 16-byte row of codes, a part is the 1024 rows that fill
        # a bank, and the tables are the 16 pages of one WRAM bank. The sums
        # are exact whatever the blocking (TERNARY_ACC_SHIFT = 0), so the
        # twin's logits are what the scan sums in its register pair; only
        # the argmax and the runner-up are ever kept.
        blocks4 = -(-c.dim // 4)
        assert blocks4 == CLS4_ROW and blocks4 * 256 <= 4096, (
            f"dim {c.dim}: {blocks4} blocks of four need {blocks4} table pages; "
            f"the scan is wired for {CLS4_ROW} (one WRAM bank)")
        per = 0x4000 // CLS4_ROW
        assert c.vocab % per == 0, (
            f"vocab {c.vocab}: Cls4_Scan ends a part where the bank ends, so "
            f"every part must hold exactly {per} tokens")
        nparts = c.vocab // per
        t_cls = q.weights["tok_emb"].astype(np.int8)
        for i in range(nparts):
            ternary_row_blob(f"cls_w_p{i}", t_cls[i * per:(i + 1) * per])
        const("CLS_BLOCKS4", blocks4)
        blob("lut_cls_hi", bytes(1), rom0=False)   # unused; the manifest names them
        blob("lut_cls_lo", bytes(1), rom0=False)
    else:
        # output-major register argmax, verbatim v0.4 semantics
        cls_u = q.weights["tok_emb"].astype(np.int32) + 128
        jbase = ((np.arange(c.dim, dtype=np.int32) * 64) & 0xFF)[None, :]
        cls_pair = np.empty((c.vocab, c.dim, 2), dtype=np.uint8)
        cls_pair[..., 0] = (jbase + (cls_u >> 4) * 2) & 0xFF
        cls_pair[..., 1] = (jbase + 32 + (cls_u & 15) * 2) & 0xFF
        nparts, per = blob_split("cls_w", cls_pair.tobytes(), c.vocab)
        _hi, _lo = nibble_luts()
        blob("lut_cls_hi", _hi, rom0=False)
        blob("lut_cls_lo", _lo, rom0=False)
    const("CLS_PARTS", nparts)
    const("CLS_OUTPUTS_PER_PART", per)

    # --- rmsnorm gains and shifts ---
    blob("rms_att", q.weights["rms_att"].astype(np.int8).tobytes())
    blob("rms_ffn", q.weights["rms_ffn"].astype(np.int8).tobytes())
    blob("rms_final", q.weights["rms_final"].astype(np.int8).tobytes())
    const("RMS_ROOTN", int(np.log2(c.dim)) // 2)
    blob("rmsatt_shift", sbytes(S("xb_att", l) - (-11 + q.wexp["rms_att"])
                                for l in range(c.layers)))
    blob("rmsffn_shift", sbytes(S("xb_ffn", l) - (-11 + q.wexp["rms_ffn"])
                                for l in range(c.layers)))
    const("RMSFINAL_SHIFT", S("xb_final") - (-11 + q.wexp["rms_final"]))

    # --- matrices: codebook product tables, weights, per-row requant shifts ---
    # wo lands directly on the stream's exponent, exactly as v0.4's did: the
    # residual add is raw int8 + int8 at one shared site, single-stage.
    out_site = {"wz": "zl", "wh": "h", "wo": "x", "w1": "h1", "w2": "x"}
    in_site = {"wz": "xb_att", "wh": "xb_att", "wo": "h",
               "w1": "xb_ffn", "w2": "hb"}

    # The FFN matrices ship as halves, unconditionally. At hidden 172 a whole
    # tensor fits one MBC5 bank and the split costs one extra matvec setup; at
    # hidden 352 (22,528 bytes) it does not fit, and a weight walk that crossed
    # $8000 would read VRAM as weights. One code path, valid at every size the
    # 8-bit counters allow: w1 splits by output rows (each half requants its
    # own rows), w2 by input rows (both halves accumulate into the same int16
    # accumulators, in the same order as one pass - bit-exact by construction).
    # The split point must be a multiple of four: Matvec_AddRow runs four
    # outputs per group, and a count with a remainder both drops the tail and
    # desyncs the weight stream for every later input (measured: 170 of 172
    # outputs wrong at a split of 86). Round the midpoint up to keep both
    # halves group-aligned; hidden % 4 == 0 keeps the second half aligned too.
    half = (c.hidden // 2 + 3) // 4 * 4
    assert c.hidden % 4 == 0 and c.hidden % 2 == 0
    assert half <= 255 and c.hidden - half <= 255 and c.dim <= 255
    assert half * c.dim <= 0x4000
    const("FFN_SPLIT", half)

    # All-or-nothing: the forward pass is assembled for one kernel. A ternary
    # checkpoint (every matrix in {-a, 0, +a}, a a power of two) takes the
    # block kernel; anything else the 4-bit product tables.
    ternary = all(q.ternary[n] for n in MATS)
    binary = all(q.binary[n] for n in MATS)
    assert ternary or not any(q.ternary[n] for n in MATS), "mixed kernels"
    assert binary or not any(q.binary[n] for n in MATS), "mixed kernels"
    const("TERNARY", int(ternary))
    const("BINARY", int(binary))
    # The block kernel in force: four inputs a block for one-bit rows (src/
    # matvec4b.asm), three for ternary (src/matvec3.asm). Both count wMvIn in
    # blocks and share the inner body.
    blk = twin5.BINARY_BLOCK if binary else twin5.TERNARY_BLOCK
    w2_split = twin5.W2_SPLIT_BLOCKS_BIN if binary else twin5.W2_SPLIT_BLOCKS
    if binary:
        assert c.dim % blk == 0 and c.hidden % blk == 0, "one-bit rows cannot pad"
    const("BLOCKS_DIM", -(-c.dim // blk))
    # The router and a ternary classifier keep the ternary kernel whatever
    # the rows run: their codes are blocks of three, so their counts are.
    const("ROUTER_BLOCKS", -(-c.dim // twin5.TERNARY_BLOCK))
    const("CLS_BLOCKS", -(-c.dim // twin5.TERNARY_BLOCK))
    const("BLOCKS_HIDDEN", -(-c.hidden // blk))
    const("W2_BLOCKS_A", w2_split)
    const("W2_BLOCKS_B", -(-c.hidden // blk) - w2_split)
    const("W2_SPLIT_IN", w2_split * blk)
    # Experts: `hidden` in the header is per expert. An expert's w1 (hidden
    # outputs) and w2 (hidden inputs, at most 176 * 127 in int16) each fit a
    # bank whole, so the MoE FFN is one router matvec, one select, two
    # unsplit matvecs. The router is ternary at one scale (trainer's
    # TERNARY_ONE) and only its argmax is used.
    experts = getattr(m, "experts", 0)
    const("EXPERTS", experts)
    if experts:
        assert ternary or binary, "experts are only wired for the block kernels"
        assert experts == 4, "forward.asm forms layer * 4 + expert with two adds"
        assert c.hidden * 127 <= 32767, "an expert's w2 must sum inside int16"
        const("HID_EXP", c.hidden)
        const("BLOCKS_HID_EXP", -(-c.hidden // blk))
    acc_shift = twin5.TERNARY_ACC_SHIFT if (ternary or binary) else Q.ACC_SHIFT

    def shift_bytes(name, l):
        to_exp = S("x") if out_site[name] == "x" else S(out_site[name], l)
        base = to_exp - q.wexp[name] - S(in_site[name], l) - acc_shift
        sh = base - q.rowexp[name][l]
        # Requant_All16 rounds by shifting s-1 then adding one then shifting
        # once more. For s >= 2 that cannot overflow; for s == 1 the kernel
        # special-cases the one accumulator (32767) whose +1 would wrap.
        # s == 0 stores the sum as it is, and s < 0 doubles it per step with
        # saturation - w2 rows ask for both now that the stream sits on the
        # trainer's grid. Deeper left shifts than a few would mean a
        # calibration mistake, so they still fail here.
        assert int(sh.min()) >= -4, f"{name} layer {l}: shift {int(sh.min())} < -4"
        return sh

    wblob = binary_weight_blob if binary else block_weight_blob if ternary else weight_blob
    if not (ternary or binary):
        for name in MATS:
            blob(f"lut_{name}", product_lut(q.codebooks[name]), rom0=False)
    banked = ternary or binary          # block kernels leave the matrix's bank mapped
    for name in ("wz", "wh", "wo"):
        for l in range(c.layers):
            wblob(f"{name}_l{l}", q.indices[name][l])
            blob(f"{name}_sh_l{l}", sbytes(shift_bytes(name, l)),
                 rom0=not banked, attach=f"{name}_l{l}" if banked else None)
    for l in range(c.layers):
        if experts:
            # Expert-major, one blob per (layer, expert); the manifest indexes
            # them as layer * EXPERTS + expert, which is what SetMatrix's
            # 8-bit index carries.
            block_weight_blob(f"router_l{l}", q.router_t[l].astype(np.int8))
            for e in range(experts):
                wblob(f"w1_l{l}_e{e}", q.indices["w1"][l][e])
                wblob(f"w2_l{l}_e{e}", q.indices["w2"][l][e])
                sh1 = shift_bytes("w1", l)[e]
                sh2 = shift_bytes("w2", l)[e]
                blob(f"w1_sh_l{l}_e{e}", sbytes(sh1), rom0=False, attach=f"w1_l{l}_e{e}")
                blob(f"w2_sh_l{l}_e{e}", sbytes(sh2), rom0=False, attach=f"w2_l{l}_e{e}")
            continue
        idx = q.indices["w1"][l]                  # (hidden out, dim in)
        wblob(f"w1a_l{l}", idx[:half])
        wblob(f"w1b_l{l}", idx[half:])
        sh = shift_bytes("w1", l)
        blob(f"w1a_sh_l{l}", sbytes(sh[:half]), rom0=not banked, attach=f"w1a_l{l}" if banked else None)
        blob(f"w1b_sh_l{l}", sbytes(sh[half:]), rom0=not banked, attach=f"w1b_l{l}" if banked else None)
        idx = q.indices["w2"][l]                  # (dim out, hidden in)
        if ternary or binary:
            # Two input halves, so every accumulator is an exact int16 sum -
            # no halving, no rounding bias. Each half is its own matvec,
            # requantized and added into the stream in turn.
            split = w2_split * blk
            wblob(f"w2a_l{l}", idx[:, :split])
            wblob(f"w2b_l{l}", idx[:, split:])
        else:
            weight_blob(f"w2a_l{l}", idx[:, :half])
            weight_blob(f"w2b_l{l}", idx[:, half:])
        blob(f"w2_sh_l{l}", sbytes(shift_bytes("w2", l)))

    # --- detokenizer ---
    import reference as ref
    pieces, offsets = bytearray(), []
    for i, piece in enumerate(tok.vocab):
        mm = ref._BYTE_PIECE.fullmatch(piece)
        if mm:
            piece = bytes([int(mm.group(1), 16)])
        elif i == BOS:
            piece = b"\n"
        offsets.append(len(pieces))
        pieces += bytes([len(piece)]) + piece
    # One banked blob: the offset table first (VOCAB words), the pieces
    # behind it, offsets already counted from the blob's start - so the
    # printer switches to the bank once and reads both. The offset table used
    # to live in ROM0, where 1024 tokens cost the 2 KB ROM0 did not have.
    blob("vocab_data",
         np.array([o + 2 * c.vocab for o in offsets], dtype="<u2").tobytes()
         + bytes(pieces), rom0=False)

    # --- encoder ---
    enc, enc_off = bytearray(), []
    for piece in tok.vocab:
        enc_off.append(len(enc))
        enc += bytes([len(piece)]) + piece
    order = np.argsort(-np.array(tok.scores, dtype=np.float64), kind="stable")
    rank = np.empty(len(tok.scores), dtype="<u2")
    rank[order] = np.arange(len(tok.scores), dtype=np.uint16)
    off_bytes = np.array(enc_off, dtype="<u2").tobytes()
    blob("enc_all", off_bytes + rank.tobytes() + bytes(enc), rom0=False)
    const("ENC_OFF_AT", 0)
    const("ENC_RANK_AT", len(off_bytes))
    const("ENC_VOCAB_AT", len(off_bytes) + len(rank.tobytes()))
    const("TOK_UNK", UNK)
    nl = tok.lookup.get(b"\n")
    if CHAT:
        assert nl is not None, "a chat tokenizer must have a newline piece"
    # A story's paragraph break is just another token; only a chat ends its
    # turn on one. -1 means "no id ends a turn" in src/generate.asm.
    const("TOK_NL", nl if CHAT else -1)
    const("CHAT_MODE", 1 if CHAT else 0)
    const("TOK_BOS", BOS)
    const("TOK_EOS", EOS)
    const("TOK_SPACE", tok.lookup[b" "])

    prompt_tokens = tok.encode(PROMPT)
    blob("prompt", np.array(prompt_tokens, dtype="<u2").tobytes())
    const("PROMPT_LEN", len(prompt_tokens))

    # --- bit-exact spot checks the ROM's selftest can assert ---
    x0 = Q.requant(q.weights["tok_emb"][prompt_tokens[0]].astype(np.int64),
                   q.wexp["tok_emb"], S("x"))
    tx = Q.rmsnorm(x0, q.weights["rms_ffn"][0], q.wexp["rms_ffn"], S("xb_ffn", 0))
    blob("test_x", tx.astype(np.int8).tobytes())
    want = twin5.mv(q, "w1", 0, tx, S("xb_ffn", 0), S("h1", 0),
                    e=0 if experts else None)          # expert 0, if experts
    blob("test_h1", want.astype(np.int8).tobytes())
    print(f"test matvec w1[0]: h1 range {want.min()}..{want.max()}")

    # Gate spot check: one full gate step on layer 0, from the twin.
    zl = np.clip(np.arange(-32, 32), -128, 127).astype(np.int64)
    zl = np.resize(zl, c.dim)
    hprev = np.resize(np.arange(-20, 44), c.dim).astype(np.int64)
    htild = np.resize(np.arange(30, -34, -1), c.dim).astype(np.int64)
    zg = q.sig_tables[0][zl + 128]
    hnew = Q.sat8(Q.shr_round(zg * htild + (256 - zg) * hprev, 8))
    blob("test_gate_zl", zl.astype(np.int8).tobytes())
    blob("test_gate_h", hprev.astype(np.int8).tobytes())
    blob("test_gate_ht", htild.astype(np.int8).tobytes())
    blob("test_gate_out", hnew.astype(np.int8).tobytes())

    # --- generated assembly ---
    lines.append("; Generated by py/export5.py - do not edit.")
    lines.append('INCLUDE "model.inc"')
    lines.append("")
    attached = {}
    for name, size, rom0, attach in _blobs:
        if attach:
            attached.setdefault(attach, []).append((name, size))
    for name, size, rom0, attach in _blobs:
        if attach:
            continue
        lines.append(f'SECTION "{name}", {"ROM0" if rom0 else "ROMX"}')
        lines.append(f'{name}:: INCBIN "build/blobs/{name}.bin"   ; {size} bytes')
        for aname, asize in attached.get(name, []):
            lines.append(f"{aname}:: INCBIN \"build/blobs/{aname}.bin\"   ; {asize} bytes, in the bank of {name}")
        lines.append("")

    lines.append('SECTION "Model manifest", ROM0')
    lines.append("emb_banks:: db " + ", ".join(
        f"BANK(emb_rows_p{i})" for i in range(emb_parts)))
    lines.append("emb_addrs:: dw " + ", ".join(
        f"emb_rows_p{i}" for i in range(emb_parts)))
    lines.append("cls_banks:: db " + ", ".join(
        f"BANK(cls_w_p{i})" for i in range(nparts)))
    lines.append("cls_addrs:: dw " + ", ".join(
        f"cls_w_p{i}" for i in range(nparts)))
    # w2a and w2b share w2's one shift table - both halves land in the same
    # output rows, requantized once after the second accumulating pass.
    for name in ("wz", "wh", "wo"):
        lines.append(f"{name}_banks:: db " + ", ".join(
            f"BANK({name}_l{l})" for l in range(c.layers)))
        lines.append(f"{name}_addrs:: dw " + ", ".join(
            f"{name}_l{l}" for l in range(c.layers)))
        lines.append(f"{name}_shifts:: dw " + ", ".join(
            f"{name}_sh_l{l}" for l in range(c.layers)))
        lines.append(f"{name}_shbanks:: db " + ", ".join(
            f"BANK({name}_sh_l{l})" for l in range(c.layers)))
    if experts:
        le = [(l, e) for l in range(c.layers) for e in range(experts)]
        lines.append("router_banks:: db " + ", ".join(
            f"BANK(router_l{l})" for l in range(c.layers)))
        lines.append("router_addrs:: dw " + ", ".join(
            f"router_l{l}" for l in range(c.layers)))
        for name in ("w1", "w2"):
            lines.append(f"{name}_banks:: db " + ", ".join(
                f"BANK({name}_l{l}_e{e})" for l, e in le))
            lines.append(f"{name}_addrs:: dw " + ", ".join(
                f"{name}_l{l}_e{e}" for l, e in le))
            lines.append(f"{name}_shifts:: dw " + ", ".join(
                f"{name}_sh_l{l}_e{e}" for l, e in le))
            lines.append(f"{name}_shbanks:: db " + ", ".join(
                f"BANK({name}_sh_l{l}_e{e})" for l, e in le))
    else:
        for name in ("w1a", "w1b", "w2a", "w2b"):
            lines.append(f"{name}_banks:: db " + ", ".join(
                f"BANK({name}_l{l})" for l in range(c.layers)))
            lines.append(f"{name}_addrs:: dw " + ", ".join(
                f"{name}_l{l}" for l in range(c.layers)))
        for name in ("w1a", "w1b", "w2"):
            lines.append(f"{name}_shifts:: dw " + ", ".join(
                f"{name}_sh_l{l}" for l in range(c.layers)))
            lines.append(f"{name}_shbanks:: db " + ", ".join(
                f"BANK({name}_sh_l{l})" for l in range(c.layers)))
    lines.append("sig_tables:: dw " + ", ".join(
        f"sig_l{l}" for l in range(c.layers)))
    lines.append("")

    WEIGHTS_ASM.write_text("\n".join(lines), encoding="utf-8")
    MODEL_INC.write_text(
        "; Generated by py/export5.py - do not edit.\n"
        "IF !DEF(MODEL_INC)\nDEF MODEL_INC EQU 1\n" + "\n".join(consts) + "\nENDC\n",
        encoding="utf-8")
    total = sum(b[1] for b in _blobs)
    r0 = sum(b[1] for b in _blobs if b[2] and not b[3])
    print(f"{len(_blobs)} blobs, {total:,} bytes ({total / 16384:.1f} banks); "
          f"ROM0 {r0:,} bytes")
    print(f"prompt tokens for {PROMPT!r}: {prompt_tokens}")


if __name__ == "__main__":
    main()
