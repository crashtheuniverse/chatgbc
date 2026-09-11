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
import torch         # noqa: E402

HZ = 2_097_152       # M-cycles per second, CGB double speed

# --- price, from the census of the chat cartridge (pip8, 3L 64d, 4x176) ----
#
# Measured per stage on the device, cycles per token: the three d x d gate
# matvecs 393K for 36,864 MACs, the expert w1 + router 332K for 34,560, the
# expert w2 344K for 33,792, the 512 x 64 classifier 272K; and 610K in norms,
# gate updates, relu² and requantization, which scale with layers rather than
# with MACs. So: ~10.5 cycles per block-kernel MAC, ~8.3 per classifier MAC,
# and ~203K a layer of overhead. A shape's price here is an estimate for
# choosing between shapes; the cartridge measures the truth.
CYC_PER_MAC, CYC_PER_CLS_MAC, CYC_PER_LAYER = 10.5, 8.3, 203_000


# One-bit weights with int8 activations run subset-sum tables (src/binbench.asm
# on the lab branch, bit-exact, measured): a block of 5 in HRAM costs 6.97
# cycles a MAC at 64 outputs and 4.82 at 176; a block of 8 in WRAM costs 3.08
# at 1024 outputs. The activation width does not enter - only the bit-plane
# kernel (2.23 a MAC per activation bit) cares, and it loses to the tables
# at every width above two bits.
BIN_MAC_64, BIN_MAC_176 = 7.22, 5.48   # block 4 in HRAM, from the bench (tiles 64/96/176/256)
# The classifiers, from the census of the real kernels at 1024 outputs and
# 64 inputs: one-bit planes 295,808 cycles (loops and zeroing included, so a
# little above the bench's 3.08 for the bare block-8 body); the ternary
# output-major block-4 tables (src/cls4.asm, v0.9) 246,712 - the build, the
# fused-argmax scan and the top-two bookkeeping, nothing stored.
BIN_MAC_CLS, TERN_MAC_CLS = 4.51, 3.76
MAC_BIT = 2.23       # DIRECT: src/bitbench.asm, one-bit weights, per activation bit plane


def price(layers, dim, hid_exp, vocab, levels=3, act_bits=8, emb_levels=35):
    """Ternary runs the measured block kernel; binary the measured subset-sum
    tables (block of 5 on the gates, w1 and w2, block of 8 on the classifier),
    or the bit-plane kernel where that is cheaper (2-bit activations)."""
    # The norms, gate and requantization scale with the width, not the
    # MACs: 203K a layer at 64 wide, measured 305K at 96.
    per_layer = CYC_PER_LAYER * dim / 64
    gates = layers * 3 * dim * dim
    w1 = layers * (dim * hid_exp + 4 * dim)
    w2 = layers * dim * hid_exp
    cls = vocab * dim
    cls_cost = (BIN_MAC_CLS if emb_levels == 22 else TERN_MAC_CLS) * cls
    if levels == 3:
        return layers * per_layer + CYC_PER_MAC * (gates + w1 + w2) + cls_cost
    planes = MAC_BIT * max(act_bits, 1)
    table = (BIN_MAC_64 * (gates + w2) + BIN_MAC_176 * w1 + cls_cost)
    return layers * per_layer + min(table, planes * (gates + w1 + w2 + cls))


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
    starts = np.nonzero(ids == ref.BOS)[0]
    starts = starts[starts + seq + 1 <= len(ids)][:n_seqs]
    span = np.arange(seq + 1)
    chunk = ids[starts[:, None] + span].astype(np.int64)
    return torch.from_numpy(chunk[:, :-1]), torch.from_numpy(chunk[:, 1:])


@torch.no_grad()
def grade(model, x, y, device, batch=128):
    import train
    lam = train.ARENAS["lam"]
    train.ARENAS["lam"] = 0.0            # grade what ships, never the residual
    model.eval()
    tot, n = 0.0, 0
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
    args = ap.parse_args()

    # The tokenizer names the token cache, so it must be chosen before the
    # reference module reads its default.
    os.environ["CHATGBC_TOKENIZER"] = str(args.tokenizer)
    import reference as ref
    import arch
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
