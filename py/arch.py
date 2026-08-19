"""What would a given architecture cost on the cartridge?

Training a model to find out it does not fit is the expensive way to learn that.
This predicts cycles per token from a shape, using coefficients measured on the
real ROM by stubbing kernels, so a candidate can be rejected in milliseconds.

The coefficients are fitted, not derived. Each is a measurement from docs/LOG.md
divided by the work it covers at the current shape, so the model reproduces the
current shape exactly by construction. Its value is in the *ratios* between
shapes, and it is only trustworthy near the shape it was fitted at - a wildly
different model would need re-measuring.

The rule it exists to make concrete:

  Plumbing scales with inputs + outputs. MACs scale with inputs x outputs.
  So fewer, larger matvecs beat more, smaller ones - wide beats deep.
"""

import argparse
from dataclasses import dataclass

# --- measured on the ROM, steady state with the window full -----------------
MAC_4BIT = 19       # matvec inner loop, hand-counted and confirmed by stubbing
MAC_CLS = 37        # the classifier's two-lookup kernel
LUT_BUILD = 200     # copying one activation's 32-byte product table into HRAM
REQUANT = 300       # one output: shift, saturate, store
ELEMENT = 759       # rmsnorm, rope, silu, residuals: the residual, solved so
                    # the total matches the ROM's 23,326,656 exactly

ATT_SCORE = 187     # per MAC in Attn_Scores, after quarter squares
ATT_WEIGHT = 286    # per MAC in Attn_Weighted
ATT_SOFTMAX = 1395  # per head-position, independent of head size

CYCLES_PER_SECOND = 2_097_152


@dataclass
class Shape:
    dim: int = 64
    hidden: int = 172
    layers: int = 5
    heads: int = 8
    kv_heads: int = 4
    vocab: int = 512
    window: int = 64

    @property
    def head_size(self):
        return self.dim // self.heads

    @property
    def kv_dim(self):
        return self.kv_heads * self.head_size

    def matvecs(self):
        """(inputs, outputs) for every matrix multiplied once per token."""
        d, h, k = self.dim, self.hidden, self.kv_dim
        per_layer = [(d, d), (d, k), (d, k), (d, d), (d, h), (d, h), (h, d)]
        return [m for _ in range(self.layers) for m in per_layer]

    def params(self):
        return sum(i * o for i, o in self.matvecs()) + self.vocab * self.dim


def cost(s: Shape):
    """Cycles per token, broken down. Steady state, window full."""
    macs = sum(i * o for i, o in s.matvecs())
    lut = sum(i for i, _ in s.matvecs()) + s.dim          # + the classifier's
    req = sum(o for _, o in s.matvecs()) + s.vocab

    head_pos = s.layers * s.heads * s.window
    att_macs = head_pos * s.head_size

    return {
        "matvec": macs * MAC_4BIT,
        "classifier": s.vocab * s.dim * MAC_CLS,
        "lut builds": lut * LUT_BUILD,
        "requant": req * REQUANT,
        "elementwise": s.layers * (4 * s.dim + 3 * s.hidden) * ELEMENT,
        "attn scores": att_macs * ATT_SCORE,
        "attn weighted": att_macs * ATT_WEIGHT,
        "attn softmax": head_pos * ATT_SOFTMAX,
    }


def report(name, s: Shape, chars_per_token=2.43):
    c = cost(s)
    total = sum(c.values())
    secs = total / CYCLES_PER_SECOND
    print(f"\n  {name}: dim {s.dim}, hidden {s.hidden}, {s.layers} layers, "
          f"{s.heads} heads, vocab {s.vocab}, window {s.window}")
    print(f"  {s.params():,} parameters")
    for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<16}{v:>12,}{v / total * 100:>7.1f}%")
    print(f"    {'TOTAL':<16}{total:>12,}")
    print(f"  {secs:.2f} s/token, {secs / chars_per_token:.2f} s/char, "
          f"{s.params() / total * 1000:.2f} params per 1000 cycles")
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=3.0,
                    help="target seconds per character")
    args = ap.parse_args()

    current = Shape()
    base = report("shipped", current)

    print("\n  --- same parameter count, different shapes ---")
    for name, s in [
        ("wider, shallower", Shape(dim=96, hidden=256, layers=2)),
        ("wider still, 1 layer", Shape(dim=128, hidden=344, layers=1)),
        ("narrower, deeper", Shape(dim=48, hidden=128, layers=9)),
        ("half the window", Shape(window=32)),
        ("bigger vocab, wide", Shape(dim=96, hidden=256, layers=2, vocab=1024)),
    ]:
        total = report(name, s)
        print(f"  vs shipped: {total / base:.2f}x cycles, "
              f"{s.params() / current.params():.2f}x parameters, "
              f"{(s.params() / total) / (current.params() / base):.2f}x "
              f"parameters per cycle")


if __name__ == "__main__":
    main()
