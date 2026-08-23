"""Export the quantized model into ROM-ready blobs plus generated assembly.

Emits one .bin per (tensor, layer) and a `src/weights.asm` that INCBINs them
into ROMX sections. Section placement is left to rgblink, and the manifest
tables use `BANK(label)` so the linker fills the bank numbers in - no bin
packing here.

Everything the ROM needs is precomputed into *shifts*, never exponents. A
requantization is `acc >> shift` with the per-output-row scale already folded
in, so the assembly never does exponent arithmetic at runtime.

Product table bias
------------------
The per-input table holds `x[j] * cb[u]`, which is signed, and adding a signed
16-bit value into an int24 accumulator needs a sign extension the SM83 has no
spare register for. Biasing every entry by MV_BIAS makes the table unsigned, so
the third accumulator byte is a plain `adc a, 0`. The sum picks up `n * MV_BIAS`,
removed once per matvec rather than once per MAC.
"""

from pathlib import Path

import numpy as np

import quant as Q
import reference as ref

ROOT = Path(__file__).resolve().parent.parent
BLOBS = ROOT / "build" / "blobs"
WEIGHTS_ASM = ROOT / "src" / "weights.asm"
MODEL_INC = ROOT / "src" / "model.inc"

BIAS = 1 << 14
HLUT_BASE = 0x80          # product table pinned here so weight bytes are HRAM offsets
WEIGHT_BITS = 4

# Tensors kept at 8 bits, with per-output-row scales, and run through the
# nibble-split kernel instead of the 4-bit table one.
#
# wk and wv are the only weights in the model whose error compounds along the
# sequence: everything else affects the token being computed, while these two
# write the KV cache and are re-read at every one of the next SEQ_LEN positions.
# They are also the smallest matrices in the layer - DIM x KV_DIM against
# DIM x DIM and DIM x HIDDEN - so the 37-cycle kernel costs 2.9% of a token and
# buys more quality than putting *every* matrix at 8 bits, which costs 31.9%.
# Measured: 1.706 -> 1.540 bits/token, against 1.487 for the whole model.
#
# ROM is roughly a wash: the weights double to two bytes each (+20 KB) and the
# two 8 KB per-matrix product tables go away, since the nibble tables depend
# only on the activation and are shared with the classifier.
WIDE = ("wk", "wv")
# Attention window. Everything is parameterized on this - the ring mask, the
# score and weight buffers, the KV bank offsets - so it is genuinely a knob.
#
# It was widened from 16 to 64 before the ring buffer existed, purely to get
# longer output. The ring provides that now, so the width is free to be chosen
# on merit again. Re-measured with each window calibrated at its own width and scored past
# saturation, against an fp32 reference that keeps full context:
#
#   window   top-1     KL     token cycles   saved
#        8   68.6%  0.6050      11,058,880   27.5%
#       16   71.5%  0.4969      12,455,936   18.3%
#       24   75.7%  0.4320      13,852,992    9.2%
#       32   76.9%  0.4368      15,250,048      -
#
# 24 is the knee: 1.2 points of top-1 against 32, with a KL that is actually
# better, so no measurable quality cost for 9% of the token. 16 is where the
# curve genuinely breaks - 5.4 points and a KL of 0.50, which shows in the text.
#
# 24 needs a real modulo rather than a mask to find the ring slot. That is five
# subtract loops a token, roughly 70 cycles, and it was briefly mistaken for a
# reason to avoid the width entirely.
#
# Why this is a first-class knob here and was not for the C implementation that
# shipped 16: attention is 37% of a token for us, and costs more per layer than
# all seven weight matrices combined. At 169 s/token it was a rounding error.
SEQ = 24
# Absolute positions for RoPE. The cache rings at SEQ, but RoPE needs the true
# position - an old key keeps the rotation it was written with, and q.k depends
# on the difference, so positions must keep counting. 256 fits a byte and needs
# only a 4 KB table; past that RoPE extrapolates badly anyway (trained to 512).
MAX_POS = 256

MATS = ("wq", "wk", "wv", "wo", "w1", "w2", "w3")

_blobs = []


def blob(name, data, rom0=True):
    """Record a named binary that weights.asm will INCBIN into its own section.

    Small tables go in ROM0 so they are always mapped; only the weight matrices
    are banked. That keeps bank switching entirely out of the kernels - they
    would otherwise have to juggle a bank per codebook and shift array.
    """
    data = bytes(data)
    (BLOBS / f"{name}.bin").write_bytes(data)
    _blobs.append((name, len(data), rom0))
    return name


def blob_split(name, data, rows):
    """Split a blob across banks on a row boundary.

    A ROMX section cannot exceed 16 KB, and both the embedding table and the
    classifier weights are 32 KB. Splitting the classifier by *input* is free:
    the matvec accumulates over inputs, so a bank boundary just ends one group
    and the accumulators carry straight over.
    """
    stride = len(data) // rows
    per_bank = (0x4000 // stride) * stride
    parts = [data[i : i + per_bank] for i in range(0, len(data), per_bank)]
    for i, part in enumerate(parts):
        blob(f"{name}_p{i}", part, rom0=False)
    return len(parts), per_bank // stride


def weight_blob(name, idx):
    """Codebook indices as ready-to-use HRAM table offsets, input-major.

    Input-major means input j's weights for every output are contiguous, which
    is what lets the kernel stream them with `ld a, [de]` / `inc de`. It also
    makes splitting a matvec across ROM banks trivial: a bank boundary just ends
    one group of inputs, and the accumulators carry over.
    """
    offsets = idx.T.astype(np.int32) * 2 + HLUT_BASE
    assert offsets.max() < 0x100
    return blob(name, offsets.astype(np.uint8).tobytes(), rom0=False)


def nibble_pair_blob(name, w):
    """An 8-bit weight matrix as ready-made HRAM offset pairs, input-major.

    Same layout the classifier uses: for input j, each output contributes a
    high-nibble offset then a low-nibble offset, and Matvec_AddRowCls adds both.
    `w` arrives as (out, in) and is transposed, so the kernel streams it with
    `ld a, [de]` / `inc de` exactly as the 4-bit one does.
    """
    u = w.T.astype(np.int32) + 128                       # (in, out), 0..255
    pair = np.empty(u.shape + (2,), dtype=np.uint8)
    pair[..., 0] = (u >> 4) * 2 + HLUT_BASE              # hi table
    pair[..., 1] = (u & 15) * 2 + HLUT_BASE + 32         # lo table, 32 bytes up
    return blob(name, pair.tobytes(), rom0=False)


def sbytes(values):
    return bytes(int(v) & 0xFF for v in values)


def product_lut(codebook):
    """Every product table the matvec could ever need, precomputed.

    The table for input j is `x[j] * cb[u] + BIAS` for the 16 codebook entries.
    Both operands are known at export time, so all 256 possible tables fit in
    8 KB of ROM and the kernel's per-input work collapses from sixteen shift-add
    multiplies (~3,200 cycles) to a 32-byte copy into HRAM (~200). ROM is the
    one resource this project has in abundance; cycles are the scarce one.

    Indexed by `(x + 128) * 32`, so a signed activation becomes an offset with
    one add. Entries stay unsigned: |x*cb| <= 16256 < BIAS.
    """
    out = bytearray()
    for x in range(-128, 128):
        for w in codebook:
            out += int(Q.shr_round(x * int(w), Q.ACC_SHIFT)).to_bytes(2, "little", signed=True)
    assert len(out) == 256 * 16 * 2
    return bytes(out)


def quantize(model, sites):
    """The one place that decides how this model is quantized.

    8 bits on the classifier is worth 6.6 points of teacher-forced top-1
    (74.6 -> 81.2) and it is the tensor that decides argmax. At 8 bits
    quantize_model uses plain uniform int8 with a single exponent, which is
    exactly what the nibble split below needs.

    py/golden.py calls this too - if the golden were quantized differently from
    the ROM, the bit-exactness test would be comparing two different models.
    """
    return Q.quantize_model(model, sites, weight_bits=WEIGHT_BITS,
                            bits_override={"tok_emb": 8, **{n: 8 for n in WIDE}},
                            rowscale_8bit=WIDE)


def nibble_luts():
    """The classifier's weights are 8-bit, which will not fit the 16-entry trick.

    A 256-entry product table is 512 bytes against 127 of HRAM, so the weight is
    split instead. Storing it unsigned as `u = w + 128`, with `hi = u >> 4` and
    `lo = u & 15`:

        x * w == x * (16*hi + lo - 128)
              == (x * hi * 16) + (x * (lo - 128))

    which is two lookups and one add, and is *exact* - the product is
    reconstructed in full before the accumulator's rounding shift, so the twin
    does not have to change to match it.

    Returns (hi, lo) tables, each 256 activations x 16 entries x 2 bytes.
    Both tables are pre-divided by four, like every other product table here, and
    the split survives it exactly: `x * hi * 16` is always a multiple of four, and
    adding a multiple of four before a rounding shift by two changes nothing. So
    the kernel never rounds - it adds two ready-made numbers, which is the same
    shape as the 4-bit loop, run twice.
    """
    hi = bytearray()
    lo = bytearray()
    for x in range(-128, 128):
        for u in range(16):
            hi += int(x * u * 4).to_bytes(2, "little", signed=True)
            lo += int(Q.shr_round(x * (u - 128), Q.ACC_SHIFT)).to_bytes(
                2, "little", signed=True)
    return bytes(hi), bytes(lo)


def main():
    BLOBS.mkdir(parents=True, exist_ok=True)
    model, tok = ref.Model(), ref.Tokenizer()
    c = model.cfg
    print("calibrating...", flush=True)
    sites = Q.calibrate(model, seq_len=SEQ)
    q = quantize(model, sites)

    S = lambda n, l=0: q.site(n, l)
    lines, consts = [], []

    def const(name, value):
        consts.append(f"DEF {name} EQU {value}")

    const("DIM", c.dim)
    const("HIDDEN", c.hidden_dim)
    const("N_LAYERS", c.n_layers)
    const("N_HEADS", c.n_heads)
    const("N_KV_HEADS", c.n_kv_heads)
    const("HEAD_SIZE", c.head_size)
    const("KV_DIM", c.kv_dim)
    const("KV_MUL", c.kv_mul)
    const("VOCAB", c.vocab_size)
    const("SEQ_LEN", SEQ)
    const("MAX_POS", MAX_POS)
    const("CB_LEVELS", 1 << WEIGHT_BITS)
    const("MV_BIAS", BIAS)
    const("HLUT_BASE", f"${HLUT_BASE:02X}")
    const("EXP_BITS", Q.EXP_BITS)
    const("SIG_BITS", Q.SIG_BITS)
    const("RSQRT_BITS", Q.RSQRT_BITS)
    const("RECIP_BITS", Q.RECIP_BITS)
    const("KV_BANK_BASE", 2)        # banks 2..6 hold layers 0..4; 1 holds the stack
    # One layer of KV is SEQ * KV_DIM of K then the same of V, which is exactly
    # 4096 bytes - a whole WRAM bank - so every offset inside is a constant.
    const("KV_K_BASE", "$D000")
    const("KV_V_BASE", f"${0xD000 + SEQ * c.kv_dim:04X}")
    const("X_EXP", S("x"))

    # --- lookup tables ---
    t = Q.TABLES
    blob("tbl_rsqrt", t["rsqrt"].astype("<u2").tobytes())
    blob("tbl_sigmoid", t["sigmoid"].astype(np.uint8).tobytes())
    # Softmax owns both of these and nothing else touches them, so they are
    # banked rather than resident. That is a kilobyte back in ROM0, which had
    # 78 bytes left.
    blob("tbl_exp", t["exp"].astype("<u2").tobytes(), rom0=False)
    blob("tbl_recip", t["recip"].astype("<u2").tobytes(), rom0=False)
    blob("tbl_rope", Q.rope_table(MAX_POS, c.head_size).astype("<i2").tobytes(), rom0=False)

    # Quarter squares, so attention can multiply without multiplying.
    #
    #   a*b == f(a+b) - f(a-b),  where f(x) = floor(x*x / 4)
    #
    # Exact for every integer pair, not an approximation: a+b and a-b always
    # share parity, so either both floors are exact or both drop the same 1/4.
    # f is even, so only |x| needs storing - 257 entries instead of 512, which
    # is what lets it sit in ROM0 alongside everything else.
    #
    # Attention's dot products are int8 by int8 with both operands only known at
    # runtime, so the product tables the matvec uses cannot help there. This can.
    qsq = (np.arange(257, dtype=np.int64) ** 2) // 4
    blob("tbl_qsq", qsq.astype("<u2").tobytes())

    # --- token embedding: output-major rows for the lookup ---
    emb = q.weights["tok_emb"]                       # int8 codebook values, (vocab, dim)
    nparts, per = blob_split("emb_rows", emb.astype(np.int8).tobytes(), c.vocab_size)
    const("EMB_PARTS", nparts)
    const("EMB_PER_PART", per)
    blob("emb_shift", sbytes(
        S("x") - q.e("tok_emb") - q.rowexp["tok_emb"]
    ))

    # --- classifier: input-major, plus the left shift that makes rows comparable ---
    # Two HRAM offsets per weight, ready to use: the kernel does no nibble
    # arithmetic at all, it just reads two bytes and adds two lookups. ROM is
    # the resource this project has spare.
    cls_u = (q.w("tok_emb").T.astype(np.int32) + 128)        # (dim, vocab), 0..255
    cls_pair = np.empty((c.dim, c.vocab_size, 2), dtype=np.uint8)
    cls_pair[..., 0] = (cls_u >> 4) * 2 + HLUT_BASE          # hi table
    cls_pair[..., 1] = (cls_u & 15) * 2 + HLUT_BASE + 32     # lo table, 32 bytes up
    nparts, per = blob_split("cls_w", cls_pair.tobytes(), c.dim)
    const("CLS_PARTS", nparts)
    const("CLS_INPUTS_PER_PART", per)
    rex = q.rowexp["tok_emb"].astype(np.int32)
    blob("cls_lshift", sbytes(rex - rex.min()))
    # The same split again, for attention's q.k - but unscaled. A score is an
    # exact integer dot product in the twin (`keys @ qh`, no rounding), so these
    # tables must reconstruct the exact product, where the classifier's are
    # pre-divided by four to match its accumulator.
    #
    # It works there for the same reason it works here: for one head, q is fixed
    # across every attended position. Iterate dimension on the outside and q[d]
    # is constant for the whole inner sweep - which is the matvec's shape, and
    # what a product table needs.
    # Both halves are biased by 2^15 so every entry is unsigned, which is what
    # lets the kernel accumulate with a plain `adc a, 0` into the third byte
    # instead of sign-extending each lookup. The bias is constant per MAC, so
    # eight dimensions add exactly 8 * 65536 = 0x080000 - removed afterwards by
    # subtracting 8 from the score's top byte, once per position.
    SBIAS = 1 << 15
    shi, slo = bytearray(), bytearray()
    for x in range(-128, 128):
        for u in range(16):
            shi += (x * u * 16 + SBIAS).to_bytes(2, "little")
            slo += (x * (u - 128) + SBIAS).to_bytes(2, "little")
    blob("lut_score_hi", bytes(shi), rom0=False)
    blob("lut_score_lo", bytes(slo), rom0=False)

    _hi, _lo = nibble_luts()
    blob("lut_cls_hi", _hi, rom0=False)
    blob("lut_cls_lo", _lo, rom0=False)

    # --- rmsnorm gains (kept int8; 320 bytes total and outside every hot loop) ---
    for name, shift_name in (("rms_att", "RMSATT"), ("rms_ffn", "RMSFFN")):
        blob(name, q.weights[name].astype(np.int8).tobytes())
    blob("rms_final", q.weights["rms_final"].astype(np.int8).tobytes())

    # rmsnorm lands on `-11 + w_exp`, so the closing shift is a per-layer constant.
    root_n_shift = int(np.log2(c.dim)) // 2
    const("RMS_ROOTN", root_n_shift)
    blob("rmsatt_shift", sbytes(S("xb_att", l) - (-11 + q.e("rms_att")) for l in range(c.n_layers)))
    blob("rmsffn_shift", sbytes(S("xb_ffn", l) - (-11 + q.e("rms_ffn")) for l in range(c.n_layers)))
    const("RMSFINAL_SHIFT", S("xb_final") - (-11 + q.e("rms_final")))

    # --- per-matrix codebooks and per-layer weights + requant shifts ---
    out_site = {"wq": "q", "wk": "k", "wv": "v", "wo": "x", "w1": "h1", "w2": "x", "w3": "h3"}
    in_site = {"wq": "xb_att", "wk": "xb_att", "wv": "xb_att", "wo": "att_out",
               "w1": "xb_ffn", "w2": "hb", "w3": "xb_ffn"}
    for name in MATS:
        if name not in WIDE:
            blob(f"lut_{name}", product_lut(q.codebooks[name]), rom0=False)
        for l in range(c.n_layers):
            if name in WIDE:
                nibble_pair_blob(f"{name}_l{l}", q.w(name, l))
            else:
                weight_blob(f"{name}_l{l}", q.indices[name][l])
            to_exp = S("x") if out_site[name] == "x" else S(out_site[name], l)
            base = to_exp - q.e(name) - S(in_site[name], l) - Q.ACC_SHIFT
            blob(f"{name}_sh_l{l}", sbytes(base - q.rowexp[name][l]))

    # --- per-layer shifts for the nonlinearities ---
    blob("att_shift", sbytes(-(S("q", l) + S("k", l)) - 4 for l in range(c.n_layers)))
    blob("attout_shift", sbytes(
        S("att_out", l) - (S("v", l) - Q.EXP_BITS) for l in range(c.n_layers)))
    blob("silu_idx_shift", sbytes(-S("h1", l) - Q.SIG_SHIFT for l in range(c.n_layers)))
    blob("silu_out_shift", sbytes(
        S("hb", l) - (S("h1", l) - Q.SIG_BITS + S("h3", l)) for l in range(c.n_layers)))

    # --- detokenizer: vocabulary pieces, with byte-fallback tokens resolved ---
    # BOS is a story separator in this corpus and the model emits it mid-run.
    # Its vocabulary piece is the literal text "<s>", which is what used to
    # appear on screen. A blank line is what it actually means.
    pieces, offsets = bytearray(), []
    for i, piece in enumerate(tok.vocab):
        m = ref._BYTE_PIECE.fullmatch(piece)
        if m:
            piece = bytes([int(m.group(1), 16)])
        elif i == ref.BOS:
            piece = b"\n"
        offsets.append(len(pieces))
        pieces += bytes([len(piece)]) + piece
    assert len(pieces) < 1 << 16
    blob("vocab_data", bytes(pieces), rom0=False)
    blob("vocab_off", np.array(offsets, dtype="<u2").tobytes())

    # --- a matvec+requant case the ROM can be checked against bit-exactly ---
    # A real post-RMSNorm activation, not uniform noise: the kernel should be
    # checked on the distribution it actually sees.
    tok0 = tok.encode("Once upon a time")[0]
    x0 = Q.requant(q.w("tok_emb")[tok0].astype(np.int32),
                   q.e("tok_emb") + int(q.rex("tok_emb")[tok0]), S("x"))
    tx = Q.rmsnorm(x0, q.w("rms_ffn", 0), q.e("rms_ffn"), S("xb_ffn", 0))
    blob("test_x", tx.tobytes())
    acc = Q.matvec(q.weights["w1"][0], tx)
    want = Q.requant_rows(acc, q.e("w1") + S("xb_ffn", 0) + Q.ACC_SHIFT, q.rowexp["w1"][0], S("h1", 0))
    blob("test_h1", want.astype(np.int8).tobytes())
    print(f"test matvec w1[0]: {c.hidden_dim}x{c.dim}, h1 range {want.min()}..{want.max()}")

    # --- encoder: raw vocab strings plus merge scores ---
    # The detokenizer blob above resolved byte-fallback tokens to raw bytes.
    # Encoding needs the vocabulary as trained: merges concatenate the literal
    # pieces, and "<0x0A>"-style entries must stay literal so they never merge.
    enc, enc_off = bytearray(), []
    for piece in tok.vocab:
        enc_off.append(len(enc))
        enc += bytes([len(piece)]) + piece
    # Scores only need to preserve order, so rank them: highest score = rank 0.
    order = np.argsort(-np.array(tok.scores, dtype=np.float64), kind="stable")
    rank = np.empty(len(tok.scores), dtype="<u2")
    rank[order] = np.arange(len(tok.scores), dtype=np.uint16)

    # One blob, because the encoder touches all three together: keeping them in
    # a single section guarantees they share a bank, so the whole encode needs
    # exactly one bank switch instead of one per lookup.
    off_bytes = np.array(enc_off, dtype="<u2").tobytes()
    rank_bytes = rank.tobytes()
    blob("enc_all", off_bytes + rank_bytes + bytes(enc), rom0=False)
    const("ENC_OFF_AT", 0)
    const("ENC_RANK_AT", len(off_bytes))
    const("ENC_VOCAB_AT", len(off_bytes) + len(rank_bytes))
    const("TOK_BOS", ref.BOS)
    const("TOK_EOS", ref.EOS)
    const("TOK_SPACE", tok.lookup[b" "])

    prompt_tokens = tok.encode("Once upon a time")
    blob("prompt", np.array(prompt_tokens, dtype="<u2").tobytes())
    const("PROMPT_LEN", len(prompt_tokens))

    # --- generated assembly ---
    lines.append("; Generated by py/export.py - do not edit.")
    lines.append('INCLUDE "model.inc"')
    lines.append("")
    for name, size, rom0 in _blobs:
        lines.append(f'SECTION "{name}", {"ROM0" if rom0 else "ROMX"}')
        lines.append(f"{name}:: INCBIN \"build/blobs/{name}.bin\"   ; {size} bytes")
        lines.append("")

    # Manifest: bank + address per (tensor, layer), resolved by the linker.
    lines.append('SECTION "Model manifest", ROM0')
    # The classifier spans however many banks its weights need. Two bytes per
    # weight put it at four; emitting the table means forward.asm loops instead
    # of naming each part, and stays right if the shape changes again.
    lines.append("cls_banks:: db " + ", ".join(f"BANK(cls_w_p{i})" for i in range(nparts)))
    lines.append("cls_addrs:: dw " + ", ".join(f"cls_w_p{i}" for i in range(nparts)))
    for name in MATS:
        lines.append(f"{name}_banks:: db " + ", ".join(f"BANK({name}_l{l})" for l in range(c.n_layers)))
        lines.append(f"{name}_addrs:: dw " + ", ".join(f"{name}_l{l}" for l in range(c.n_layers)))
        lines.append(f"{name}_shifts:: dw " + ", ".join(f"{name}_sh_l{l}" for l in range(c.n_layers)))
        lines.append(f"{name}_shbanks:: db " + ", ".join(f"BANK({name}_sh_l{l})" for l in range(c.n_layers)))
        if name not in WIDE:
            lines.append(f"{name}_lutbank:: db BANK(lut_{name})")
            lines.append(f"{name}_lutaddr:: dw lut_{name}")
    lines.append("")

    WEIGHTS_ASM.write_text("\n".join(lines), encoding="utf-8")
    MODEL_INC.write_text(
        "; Generated by py/export.py - do not edit.\n"
        "IF !DEF(MODEL_INC)\nDEF MODEL_INC EQU 1\n" + "\n".join(consts) + "\nENDC\n",
        encoding="utf-8",
    )

    total = sum(s for _, s, _r in _blobs)
    r0 = sum(s for _, s, r in _blobs if r)
    print(f"{len(_blobs)} blobs, {total:,} bytes ({total / 16384:.1f} banks); ROM0 {r0:,} bytes")
    print(f"prompt tokens for 'Once upon a time': {tok.encode('Once upon a time')}")


if __name__ == "__main__":
    main()
