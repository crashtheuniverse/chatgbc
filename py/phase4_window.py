"""Does a smaller attention window pay for itself?

Attention is O(window) per token, so a shorter window is cheaper - but the
measured share is small, so the question is whether the quality loss is worth
the cycles saved. Cost figures come from stubbing Attention in the ROM:
538,496 cycles at an average of 32 attended positions, i.e. ~16.8K cycles per
position, against a 10,468,800-cycle token with attention removed.
"""

import numpy as np

import quant as Q
import reference as ref
from sweep import PROMPTS, SEQ, STEPS, reference_paths

BASE = 10_468_800          # token cost with attention stubbed out
PER_POS = 538_496 / 32     # attention cycles per attended position
HZ = 2_097_152
CHARS_PER_TOKEN = 2.52


def top1_windowed(q, paths, window):
    rtbl = Q.rope_table(SEQ, q.cfg.head_size)
    same = total = 0
    for seq, picks in paths:
        state = Q.QState(q.cfg, SEQ)
        for pos, token in enumerate(seq[: len(picks)]):
            logits = Q.forward_q(q, state, token, pos, rtbl, window)
            same += int(logits.argmax()) == picks[pos]
            total += 1
    return 100.0 * same / total


def main():
    model, tok = ref.Model(), ref.Tokenizer()
    print("calibrating...", flush=True)
    sites = Q.calibrate(model)
    q = Q.quantize_model(model, sites, weight_bits=4)
    paths = reference_paths(model, tok)

    print(f"\n{'window':>7} {'top-1 vs fp32':>14} {'cycles/token':>13} {'s/char':>8}  sample")
    for w in (8, 16, 32, 64, None):
        agree = top1_windowed(q, paths, w)
        eff = STEPS / 2 if w is None else min(w, STEPS)   # avg attended positions
        cyc = BASE + PER_POS * eff
        label = "full" if w is None else str(w)
        out = "".join(t for _, t in Q.generate_q(q, tok, PROMPTS[0], 40, SEQ, w))
        print(f"{label:>7} {agree:>13.1f}% {cyc:>13,.0f} "
              f"{cyc / HZ / CHARS_PER_TOKEN:>8.2f}")
        print(f"         {out[:96]!r}")


if __name__ == "__main__":
    main()
