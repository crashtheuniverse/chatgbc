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
SEQ = 64                  # KV cache: one WRAM bank per layer holds exactly 64 positions
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


def main():
    BLOBS.mkdir(parents=True, exist_ok=True)
    model, tok = ref.Model(), ref.Tokenizer()
    c = model.cfg
    print("calibrating...", flush=True)
    sites = Q.calibrate(model, seq_len=SEQ)
    q = Q.quantize_model(model, sites, weight_bits=WEIGHT_BITS)

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
    blob("tbl_exp", t["exp"].astype("<u2").tobytes())
    blob("tbl_recip", t["recip"].astype("<u2").tobytes())
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
    cls_off = q.indices["tok_emb"].T.astype(np.int32) * 2 + HLUT_BASE
    nparts, per = blob_split("cls_w", cls_off.astype(np.uint8).tobytes(), c.dim)
    const("CLS_PARTS", nparts)
    const("CLS_INPUTS_PER_PART", per)
    rex = q.rowexp["tok_emb"].astype(np.int32)
    blob("cls_lshift", sbytes(rex - rex.min()))
    blob("lut_cls", product_lut(q.codebooks["tok_emb"]), rom0=False)

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
        blob(f"lut_{name}", product_lut(q.codebooks[name]), rom0=False)
        for l in range(c.n_layers):
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
    pieces, offsets = bytearray(), []
    for i, piece in enumerate(tok.vocab):
        m = ref._BYTE_PIECE.fullmatch(piece)
        if m:
            piece = bytes([int(m.group(1), 16)])
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
    for name in MATS:
        lines.append(f"{name}_banks:: db " + ", ".join(f"BANK({name}_l{l})" for l in range(c.n_layers)))
        lines.append(f"{name}_addrs:: dw " + ", ".join(f"{name}_l{l}" for l in range(c.n_layers)))
        lines.append(f"{name}_shifts:: dw " + ", ".join(f"{name}_sh_l{l}" for l in range(c.n_layers)))
        lines.append(f"{name}_shbanks:: db " + ", ".join(f"BANK({name}_sh_l{l})" for l in range(c.n_layers)))
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
