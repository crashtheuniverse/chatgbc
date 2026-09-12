"""Train the v0.4 story model, in the regime the cartridge runs.

One recipe, settled by measurement on the chat line before it came here:
minGRU core, a four-expert ReLU² MLP, ternary weights with power-of-two row
scales, int8 activations and state, and a ternary tied classifier at one
scale for the whole tensor - so every matrix on the cartridge runs the same
block kernel. Training uses the Arenas residual (Sherry, arXiv 2601.07892):
a full-precision copy added to the ternary image and annealed to zero, which
is what makes ternary converge in a sane number of steps. Grading and baking
happen with the residual at zero, on the weights that ship.

The score is bits per character on held-out TinyStories, because that is
the one number two models with different tokenizers can share - and
seconds per character is the one the reader feels. Both are reported against
v0.3's measured figures.

    python py/fit.py --tokenizer models/tok_ts512.bin --steps 20000
    python py/fit.py --tokenizer models/tok_ts512.bin --layers 4 --name ts4L
    python py/fit.py --price --layers 4 --dim 64 --hidden 352 --vocab 1024

The price. Before a run, price() says what a shape costs a token on the v0.9
cartridge, stage by stage, from the kernels' own counted listings (the block
comment above price_stages has every term): the output-major sweep for wz,
wh, wo, w1 and the router (three table builds and 3d + H + E rows a layer,
302 + 8s a row at d = 64), the sparse w2 (per nonzero u and per nonzero
pair, at the measured sparsity), 2L + 1 norms at ~23K, the gate, ReLU^2, the
adds, the embedding and the block-4 classifier (build + ~223 a row). At the
shipped shape it reproduces the 973K census within 1%; --price prints the
breakdown beside the census and exits. It is for choosing v1.0's shape.
"""

import argparse
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py"))

import numpy as np   # noqa: E402
# torch is imported where the training path needs it (held_out, grade, bake,
# main), not here: the price model above main() is plain arithmetic, and
# py/tests/test_fit_price.py imports this module for it without the 25 s a
# cold torch import costs.

HZ = 2_097_152       # M-cycles per second, CGB double speed

# --- price: the v0.9 kernels, counted from their listings, checked against ---
# --- the census -------------------------------------------------------------
#
# Every term below is a cycle count from a kernel's file header (src/*.asm),
# written as a function of the shape - L layers, width d, expert hidden H,
# vocab V, E experts - and the whole is checked against the 8-token census of
# the shipped shape, 3L / 64d / 4 x 176 / V 1024: 973,032 cycles a token
# staged, 972,744 on the app's own counter (docs/LOG.md, v0.9 wave 2).
# price() lands within 1% of the staged figure (py/tests/test_fit_price.py
# holds it under 3%), and price_breakdown() prints the stages beside the
# census so a drift shows where it is. A shape's price is an estimate for
# choosing between shapes; the cartridge measures the truth.
#
# The sweep (src/sweep.asm, src/matvec3.asm): wz, wh, wo, w1 and the router
#   are output-major rows over resident block tables of the input vector.
#   Blocks of three inputs, B = ceil(d / 3). The tables of one vector cost
#   (d // 3) x 398 + 34 for a partial last block + 19; three vectors a layer
#   (xb serves wz and wh, h serves wo, xf serves the router and w1). A row
#   costs 15 + 12 (B - 1) + (B - 1) // 4 + 30 + 8 s, s its requant shift:
#   302 + 8 s at d = 64. The shipped streams' shifts are 2..5, rows-weighted
#   mean 3.2 (decoded from build/blobs). The router's E rows carry no shift
#   and end in a ~40-cycle compare; a group of rows ends with 9.
# The sparse w2 (src/matvec_sparse.asm): 339 to zero the accumulators and
#   read the manifest, ~60 for W2_Run to choose the path, 74 per nonzero u,
#   and per (nonzero u, nonzero weight) pair 13 without a carry, 18 with
#   (11 / 16 of body plus the 2 of loop control over two pairs).
#   Measured on 6,291 tokens (docs/audit measure_sparse_w2.py): 27 / 23 / 42
#   nonzero u of 176 a layer = 0.174 of H, ~40 nonzero weights a column =
#   0.63 of d. The pair term is 16: the census's 67,624 a token less the
#   counted fixed and per-u parts, over the mean 3,714 pairs, lands there,
#   between the two counted paths (about 60% carries, or the census tokens
#   carrying more pairs than the corpus mean). w2's requant
#   (Requant_All16, src/state.asm): ~103 a row at w2's shifts.
# The norm (src/rmsnorm.asm): 313 an element and 33 for its square, ~1,010 a
#   norm for the x*r tables, idx and r; 2 L + 1 norms a token.
# The gate (src/gate.asm): 47 an element, ~30 a layer.
# ReLU^2 (src/relu2.asm): 12.75 an element (12 and the four-a-turn loop),
#   17 a nonzero, 43 a layer.
# The residual adds (src/addsat.asm): 34 an element and ~36, two a layer.
# The embedding (EmbedToken, src/forward.asm): 71 and 5.5 a byte, one row.
# The classifier (src/cls4.asm): blocks of four, C = ceil(d / 4); the build
#   C x 1,128 + 24; the scan V x (223 + 14 (C - 16)) + ~150 of glue. 223 a
#   row is the census's 246,712 less the build and glue over 1,024 rows, so
#   it carries the equal-high-byte compares, the takes and the no-repeat
#   rescans at their measured rates. The kernel is unrolled for C = 16, one
#   bank of tables; another d means a kernel change, and the term projects.
SWEEP_MEAN_SHIFT = 3.2      # the shipped streams, rows weighted (2..5)
W2_U_FRAC = 0.174           # nonzero u a layer as a fraction of H, measured
W2_COL_FRAC = 0.63          # nonzero weights a column as a fraction of d, measured
W2_PAIR = 16                # per pair, calibrated: between 13 (no carry) and 18
REQUANT_ROW = 103           # Requant_All16 a row at small shifts
NORM_ELEM, NORM_FIXED = 313 + 33, 1_010
GATE_ELEM, GATE_FIXED = 47, 30
RELU2_ELEM, RELU2_NZ, RELU2_FIXED = 12.75, 17, 43
ADD_ELEM, ADD_FIXED = 34, 36
CLS_BUILD_BLOCK, CLS_ROW, CLS_ROW_BLOCK = 1_128, 223, 14

# The census of the shipped shape, for price_breakdown's comparison column:
# 8 tokens through build.ps1 -Census on the v0.9 tree (staged 973,032).
CENSUS_V09 = {
    "wz (tables + rows)": 89_248, "wh (rows)": 63_408, "wo (tables + rows)": 89_072,
    "w1 + router (tables + rows)": 202_728, "w2 sparse": 67_624, "w2 requant": 19_800,
    "rms_att": 68_888, "rms_ffn": 70_112, "rms_final": 23_720, "gate": 9_192,
    "relu2": 8_752, "adds": 6_640 + 6_632, "embed": 448, "classifier": 246_712,
}
SHIPPED = dict(layers=3, dim=64, hid_exp=176, vocab=1024)

# One-bit weights with int8 activations run subset-sum tables (src/binbench.asm
# on the lab branch, bit-exact, measured): a block of 5 in HRAM costs 6.97
# cycles a MAC at 64 outputs and 4.82 at 176; a block of 8 in WRAM costs 3.08
# at 1024 outputs. The activation width does not enter - only the bit-plane
# kernel (2.23 a MAC per activation bit) cares, and it loses to the tables
# at every width above two bits. These stay for the binary branch, which is
# still on the tree (src/matvec4b.asm under IF BINARY, the CLS_BINARY planes)
# and has no v0.9 sweep: its price is the v0.9 overheads plus these.
BIN_MAC_64, BIN_MAC_176 = 7.22, 5.48   # block 4 in HRAM, from the bench (tiles 64/96/176/256)
# The one-bit classifier, from the census of the real kernel at 1024 outputs
# and 64 inputs: 295,808 cycles (loops and zeroing included, so a little
# above the bench's 3.08 for the bare block-8 body).
BIN_MAC_CLS = 4.51
MAC_BIT = 2.23       # DIRECT: src/bitbench.asm, one-bit weights, per activation bit plane


def sweep_tables(d):
    """One vector's block tables (Matvec3_BuildAll): 8,411 at d = 64."""
    return (d // 3) * 398 + (34 if d % 3 else 0) + 19


def sweep_row(d, s):
    """One swept row at shift s: 302 + 8 s at d = 64."""
    b = -(-d // 3)
    return 15 + 12 * (b - 1) + (b - 1) // 4 + 30 + 8 * s


def price_stages(layers, dim, hid_exp, vocab, levels=3, act_bits=8, emb_levels=35, experts=4):
    """Cycles a token by stage, keyed as the census prints them."""
    L, d, H, V, E = layers, dim, hid_exp, vocab, experts
    nnz_u = W2_U_FRAC * H
    pairs = nnz_u * W2_COL_FRAC * d
    st = {}
    if levels == 3:
        row = sweep_row(d, SWEEP_MEAN_SHIFT)
        router = E * (sweep_row(d, 0) - 30 + 40) + 9
        st["wz (tables + rows)"] = L * (sweep_tables(d) + d * row + 9)
        st["wh (rows)"] = L * (d * row + 9)
        st["wo (tables + rows)"] = L * (sweep_tables(d) + d * row + 9)
        st["w1 + router (tables + rows)"] = L * (sweep_tables(d) + router + H * row + 9)
        st["w2 sparse"] = L * (339 + 60 + 74 * nnz_u + W2_PAIR * pairs)
        st["w2 requant"] = L * (REQUANT_ROW * d + 40)
    else:
        # Binary weights: the subset-sum tables (or the bit planes where
        # those are cheaper), input-major, every output requantized.
        gates, w1, w2 = L * 3 * d * d, L * (d * H + E * d), L * d * H
        table = BIN_MAC_64 * (gates + w2) + BIN_MAC_176 * w1
        planes = MAC_BIT * max(act_bits, 1) * (gates + w1 + w2)
        st["binary matvecs (gates, w1, w2)"] = min(table, planes)
        st["requants"] = L * (REQUANT_ROW * (4 * d + H) + 5 * 40)
    st["rms_att"] = L * (NORM_ELEM * d + NORM_FIXED)
    st["rms_ffn"] = L * (NORM_ELEM * d + NORM_FIXED)
    st["rms_final"] = NORM_ELEM * d + NORM_FIXED
    st["gate"] = L * (GATE_ELEM * d + GATE_FIXED)
    st["relu2"] = L * (RELU2_ELEM * H + RELU2_NZ * nnz_u + RELU2_FIXED)
    st["adds"] = 2 * L * (ADD_ELEM * d + ADD_FIXED)
    st["embed"] = 71 + 5.5 * d
    if emb_levels == 22:
        st["classifier"] = BIN_MAC_CLS * V * d
    else:
        c = -(-d // 4)
        st["classifier"] = c * CLS_BUILD_BLOCK + 24 + V * (CLS_ROW + CLS_ROW_BLOCK * (c - 16)) + 150
    return st


def price(layers, dim, hid_exp, vocab, levels=3, act_bits=8, emb_levels=35, experts=4):
    """Cycles a token for a shape on the v0.9 kernels: ternary runs the
    output-major sweep, the sparse w2 and the block-4 classifier; binary the
    measured subset-sum tables or bit planes, and the one-bit classifier."""
    return sum(price_stages(layers, dim, hid_exp, vocab, levels, act_bits, emb_levels, experts).values())


def price_breakdown(layers, dim, hid_exp, vocab, **kw):
    """The stages of price(), one a line, beside the shipped shape's census
    when the shape is the shipped one."""
    st = price_stages(layers, dim, hid_exp, vocab, **kw)
    shipped = dict(layers=layers, dim=dim, hid_exp=hid_exp, vocab=vocab) == SHIPPED and kw.get("levels", 3) == 3
    lines = ["  {:<30}{:>12}{:>12}{:>8}".format("stage", "model", "census" if shipped else "", "")]
    for name, cyc in st.items():
        if shipped and name in CENSUS_V09:
            m = CENSUS_V09[name]
            lines.append("  {:<30}{:>12,.0f}{:>12,}{:>+8.1%}".format(name, cyc, m, cyc / m - 1))
        else:
            lines.append("  {:<30}{:>12,.0f}".format(name, cyc))
    total = sum(st.values())
    if shipped:
        m = sum(CENSUS_V09.values())
        lines.append("  {:<30}{:>12,.0f}{:>12,}{:>+8.1%}".format("total", total, m, total / m - 1))
    else:
        lines.append("  {:<30}{:>12,.0f}".format("total", total))
    return "\n".join(lines)


def arenas_lambda(step_i, steps, warm=0.1):
    """1 through the warmup, then a cosine down to 0 at the last step."""
    w = int(steps * warm)
    if step_i < w:
        return 1.0
    t = (step_i - w) / max(1, steps - w)
    return 0.5 * (1 + math.cos(math.pi * t))


def held_out(ids, seq, n_seqs):
    """Teacher-forcing windows that start at story boundaries (BOS), `seq`
    tokens long: the protocol v0.3 was scored under, minus its window."""
    import reference as ref
    import torch
    starts = np.nonzero(ids == ref.BOS)[0]
    starts = starts[starts + seq + 1 <= len(ids)][:n_seqs]
    span = np.arange(seq + 1)
    chunk = ids[starts[:, None] + span].astype(np.int64)
    return torch.from_numpy(chunk[:, :-1]), torch.from_numpy(chunk[:, 1:])


def grade(model, x, y, device, batch=128):
    import torch
    import train
    lam = train.ARENAS["lam"]
    train.ARENAS["lam"] = 0.0            # grade what ships, never the residual
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(x), batch):
            xb, yb = x[i:i + batch].to(device), y[i:i + batch].to(device)
            _, loss = model(xb, yb)
            tot += float(loss) * xb.numel()
            n += xb.numel()
    model.train()
    train.ARENAS["lam"] = lam
    return tot / n / math.log(2)          # bits per token


def bake(model, levels):
    """Replace every latent with its quantized image, exactly as the forward
    pass sees it, so the checkpoint holds what the cartridge runs."""
    import torch
    import train
    with torch.no_grad():
        model.tok_emb.weight.copy_(train.qw(model.tok_emb.weight, model.emb_levels))
        for b in model.blocks:
            b.attn.wz.weight.copy_(train.qw(b.attn.wz.weight, levels))
            b.attn.wh.weight.copy_(train.qw(b.attn.wh.weight, levels))
            b.attn.wo.weight.copy_(train.qw(b.attn.wo.weight, levels))
            b.moe.w1.copy_(train.qw(b.moe.w1, levels))
            b.moe.w2.copy_(train.qw(b.moe.w2, levels))
            b.moe.router.weight.copy_(train.qw(b.moe.router.weight, train.TERNARY_ONE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", type=Path, default=ROOT / "models" / "tok_ts512.bin")
    ap.add_argument("--vocab", type=int, default=512, help="pieces in the tokenizer file")
    ap.add_argument("--corpus", type=Path, default=ROOT / "models" / "tinystories" / "ts_train.txt")
    ap.add_argument("--valid", type=Path, default=ROOT / "models" / "tinystories" / "ts_valid_v2.txt")
    ap.add_argument("--layers", type=int, default=3)
    ap.add_argument("--dim", type=int, default=64)
    ap.add_argument("--hidden", type=int, default=352, help="total FFN hidden; each of 4 experts gets half")
    ap.add_argument("--levels", type=int, default=3, help="3 ternary (the shipped kernel), 2 binary {-1,+1}, 21 binary {0,+1}")
    ap.add_argument("--act-bits", type=int, default=8, help="activation width into every matvec")
    ap.add_argument("--state-bits", type=int, default=8, help="the carried recurrent state")
    ap.add_argument("--emb-levels", type=int, default=35, help="tied embedding/classifier codebook: 35 ternary one-scale, 22 binary one-scale")
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--seq", type=int, default=96)
    ap.add_argument("--batch", type=int, default=96)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--grade-every", type=int, default=2000)
    ap.add_argument("--log-every", type=int, default=250)
    ap.add_argument("--eval-seq", type=int, default=256)
    ap.add_argument("--eval-stories", type=int, default=400)
    ap.add_argument("--name", default=None)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "models")
    ap.add_argument("--price", action="store_true",
                    help="print the shape's price a token, stage by stage, and exit")
    args = ap.parse_args()

    if args.price:
        cyc = price(args.layers, args.dim, args.hidden // 2, args.vocab,
                    args.levels, args.act_bits, args.emb_levels)
        print(f"  shape {args.layers}L {args.dim}d, 4 experts of {args.hidden // 2}, "
              f"vocab {args.vocab}, levels {args.levels}: ~{cyc / 1e6:.3f}M cyc/tok = "
              f"{cyc / HZ:.3f} s/tok")
        print(price_breakdown(args.layers, args.dim, args.hidden // 2, args.vocab,
                              levels=args.levels, act_bits=args.act_bits,
                              emb_levels=args.emb_levels))
        return

    # The tokenizer names the token cache, so it must be chosen before the
    # reference module reads its default.
    os.environ["CHATGBC_TOKENIZER"] = str(args.tokenizer)
    import reference as ref
    import arch
    import torch
    import train

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = ref.Tokenizer(args.tokenizer, vocab_size=args.vocab)
    vocab = len(tok.vocab)
    ids = train.load_tokens(args.corpus, tok)
    vids = train.load_tokens(args.valid, tok)
    v_chars = len(args.valid.read_text(encoding="utf-8"))
    chars_per_tok = v_chars / len(vids)
    vx, vy = held_out(vids, args.eval_seq, args.eval_stories)
    print(f"  train {len(ids):,} tokens, held-out {len(vids):,} tokens "
          f"({chars_per_tok:.3f} chars/token), grading on {vx.numel():,} "
          f"positions; {device}", flush=True)

    shape = arch.Shape(dim=args.dim, hidden=args.hidden, layers=args.layers,
                       heads=8, kv_heads=4, vocab=vocab)
    hid_exp = args.hidden // 2
    cyc = price(args.layers, args.dim, hid_exp, vocab, args.levels, args.act_bits, args.emb_levels)
    print(f"  shape {args.layers}L {args.dim}d, 4 experts of {hid_exp}, vocab {vocab}, "
          f"levels {args.levels}, {args.act_bits}-bit acts, {args.state_bits}-bit state: "
          f"~{cyc/1e6:.2f}M cyc/tok = {cyc/HZ:.2f} s/tok = {cyc/HZ/chars_per_tok:.3f} s/char "
          f"(v0.3: 2.26 s/char)", flush=True)

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    levels = args.levels
    train.POW2_SCALE["on"] = True
    model = train.Tiny(shape, levels=levels, seq=args.seq, window=24,
                       core="mingru", mlp="moe4", act_bits=args.act_bits,
                       state_bits=args.state_bits, gate_levels=None,
                       emb_levels=args.emb_levels).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  {n_params:,} parameters", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01,
                            betas=(0.9, 0.95))
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=args.lr, total_steps=args.steps, pct_start=0.1)
    stream = train.batches(ids, args.batch, args.seq, device, seed=args.seed)

    t0 = time.time()
    for step_i in range(args.steps):
        train.ARENAS["lam"] = arenas_lambda(step_i, args.steps)
        x, y = next(stream)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        if (step_i + 1) % args.log_every == 0 and (step_i + 1) % args.grade_every:
            print(f"    step {step_i + 1}: train {float(loss)/math.log(2):.3f} bits, "
                  f"{(time.time() - t0) / (step_i + 1):.2f} s/step", flush=True)
        if (step_i + 1) % args.grade_every == 0 or step_i + 1 == args.steps:
            bpt = grade(model, vx, vy, device)
            print(f"    step {step_i + 1}: held-out {bpt:.4f} bits/token = "
                  f"{bpt / chars_per_tok:.4f} bits/char  (train {float(loss)/math.log(2):.3f}, "
                  f"lam {train.ARENAS['lam']:.2f}, {time.time() - t0:.0f}s)", flush=True)
    train.ARENAS["lam"] = 0.0

    bpt = grade(model, vx, vy, device)
    # Grade BEFORE baking. The forward quantizes whatever it is given, and a
    # ternary row quantized twice is rescaled by its fraction of non-zeros -
    # so a baked model re-graded here scores nonsense (6.5 bits/token for a
    # 3.36 model). The twin and the cartridge read the baked image directly;
    # py/score5.py is the number to quote for what ships.
    bake(model, levels)
    name = args.name or f"ts{args.layers}L{args.dim}d_h{args.hidden}_v{vocab}_q{args.levels}a{args.act_bits}e{args.emb_levels}"
    path = args.out_dir / f"{name}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    n = train.save_pip5(model.cpu(), path)
    print(f"  {name}: held-out {bpt:.4f} bits/token = {bpt / chars_per_tok:.4f} bits/char; "
          f"~{cyc/HZ:.2f} s/tok, {cyc/HZ/chars_per_tok:.3f} s/char; "
          f"saved {path.name} ({n:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
