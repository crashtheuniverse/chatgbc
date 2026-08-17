"""Phase 4, experiment 1: how far can weight precision fall?

The biggest remaining cycle lever is a T-MAC style group lookup: with a group of
G activations, precompute the sum for every possible G-weight pattern, so one
table read plus one accumulate replaces G MACs. That is ~4x on the matvec - but
it only works for very low-precision weights, because the table has
levels**G entries.

  2 levels (binary), G=4  ->  16 entries   ideal
  3 levels (ternary), G=4 ->  81 entries   workable
  4 levels, G=4           -> 256 entries   too big for HRAM

So the question that decides whether to build it is quality, not cycles. This
measures teacher-forced top-1 against fp32 as the codebook shrinks, holding
per-output-row scales fixed (they are what make low precision survivable).
"""

import numpy as np

import quant as Q
import reference as ref
from sweep import PROMPTS, STEPS, SEQ, reference_paths, top1_agreement, weight_error


def ternary_codebook():
    """{-a, 0, +a} padded to 4 slots so the existing 2-bit path can carry it."""
    return np.array([-127, 0, 127, 127], dtype=np.int8)


def main():
    model, tok = ref.Model(), ref.Tokenizer()
    print("calibrating...", flush=True)
    sites = Q.calibrate(model)
    paths = reference_paths(model, tok)

    configs = [
        ("4-bit, 16 levels (current)", 4, None),
        ("3-bit, 8 levels", 3, None),
        ("2-bit, 4 levels", 2, None),
        ("ternary, 3 levels", 2, ternary_codebook()),
        ("binary, 2 levels", 1, None),
    ]

    print(f"\n{'scheme':<28} {'RMSE/sigma':>11} {'top-1 vs fp32':>14} {'matmul bytes':>13}")
    for label, bits, fixed_cb in configs:
        q = Q.quantize_model(model, sites, weight_bits=bits, fixed_codebook=fixed_cb)
        rom = sum(q.weights[n].size * bits // 8 for n in Q.MATMULS)
        agree = top1_agreement(q, paths)
        print(f"{label:<28} {weight_error(model, q):>11.4f} {agree:>13.1f}% {rom:>13,}")
        out = "".join(t for _, t in Q.generate_q(q, tok, PROMPTS[0], 32, SEQ))
        print(f"    {out!r}")


if __name__ == "__main__":
    main()
