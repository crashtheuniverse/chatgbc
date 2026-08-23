"""Are we multiplying a lot of zeros?

Softmax weights are Q0.12 - units of 1/4096 - so anything below 1/8192 of the
mass rounds to exactly zero. A zero weight contributes exactly nothing to the
weighted sum of V, and the ROM spends full price computing it anyway.

This instruments the twin at steady state and reports, per attended distance:
how often the weight is exactly zero, and how much of the mass sits where.
"""
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(r"C:\crashcode\chatgbc_x") / "py"))
import quant as Q
import reference as ref
from eval import DEV, HELD_OUT, SEQ

captured = []          # (position, weights-by-slot)
_orig = Q.softmax_weights
POS = [0]


def spy(scores, score_exp):
    w = _orig(scores, score_exp)
    captured.append((POS[0], np.asarray(w).copy()))
    return w


def main():
    Q.softmax_weights = spy
    model, tok = ref.Model(), ref.Tokenizer()
    sites = Q.calibrate(model, seq_len=SEQ)
    q = Q.quantize_model(model, sites, weight_bits=4, bits_override={"tok_emb": 8})
    rtbl = Q.rope_table(256, q.cfg.head_size)   # running past the window

    # Run well past the window so most samples are at a full 64 positions.
    for prompt in (DEV + HELD_OUT)[:6]:
        state = Q.QState(q.cfg, SEQ)
        ids = tok.encode(prompt)
        token = ids[0]
        for pos in range(90):
            POS[0] = pos
            logits = Q.forward_q(q, state, token, pos, rtbl)
            nxt = ids[pos + 1] if pos + 1 < len(ids) else int(logits.argmax())
            if nxt == ref.EOS:
                break
            token = nxt

    full = [(p, w) for p, w in captured if len(w) == SEQ and p >= SEQ]
    print(f"  {len(captured):,} softmax calls, {len(full):,} at a full "
          f"{SEQ}-position window\n")

    # The cache is a ring, so a column is a SLOT, not a recency. Slot p mod 64
    # holds the current token; distance runs backwards from there. Rolling each
    # sample by its own position is the only way to compare them.
    W = np.stack([np.roll(w, -(p % SEQ))[::-1] for p, w in full]).astype(np.int64)
    W = np.roll(W, 1, axis=1)                  # column 0 = distance 0
    total = W.sum(axis=1)
    print(f"  weights sum to {total.mean():.0f} on average (Q0.12, so 4096 = 1.0)")

    zero_frac = (W == 0).mean()
    print(f"  exactly zero: {zero_frac * 100:.1f}% of all attended positions\n")

    # Distance 0 = the current token, 63 = the oldest still in the window.
    dist = np.arange(SEQ)   # 0 = current token after the roll above
    print(f"  {'distance':>9}{'zero %':>9}{'mean weight':>13}{'share of mass':>15}")
    mass = W.sum(axis=0).astype(float)
    mass /= mass.sum()
    for lo, hi in [(0, 1), (1, 2), (2, 4), (4, 8), (8, 16), (16, 32), (32, 64)]:
        sel = (dist >= lo) & (dist < hi)
        band = W[:, sel]
        print(f"  {lo:>4}-{hi - 1:<4}{(band == 0).mean() * 100:>8.1f}%"
              f"{band.mean():>13.1f}{mass[sel].sum() * 100:>14.2f}%")

    print()
    for w in (8, 16, 32):
        keep = dist < w
        print(f"  a {w:>2}-position window keeps "
              f"{mass[keep].sum() * 100:5.2f}% of the weight mass")

    # How many positions actually carry the distribution?
    srt = np.sort(W, axis=1)[:, ::-1]
    cum = np.cumsum(srt, axis=1) / np.maximum(total[:, None], 1)
    for frac in (0.9, 0.99):
        n = (cum < frac).sum(axis=1) + 1
        print(f"  {frac:.0%} of the mass sits in {n.mean():.1f} positions on "
              f"average (median {int(np.median(n))}, max {n.max()})")


if __name__ == "__main__":
    main()
