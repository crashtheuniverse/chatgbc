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

# --- coefficients, with their provenance ------------------------------------
#
# Two kinds live here and they are not equally trustworthy.
#
# DIRECT: timed by a bench that runs the routine on fixed data, so nothing
# downstream can contaminate it. These are load-bearing.
#
# STUB: obtained by deleting a component and re-timing. Sound only if the rest
# of the model costs the same either way - and it does not. Requant_Shift loops
# on its shift count, and shift counts come from the activations, so removing a
# kernel changes what every later kernel costs and the difference is billed to
# the one removed. Stub profiling put RMSNorm at 16.5% of a token; a direct
# bench says 4-6%. Treat every STUB number below as an upper bound.

MAC_4BIT = 19       # DIRECT  matvec inner loop, hand-counted and benched
MAC_CLS = 37        # DIRECT  the classifier's two-lookup nibble kernel
MAC_BIT = 2.23      # DIRECT  src/bitbench.asm, one-bit weights, per activation
                    #         bit plane - 8.5x the product table
LUT_BUILD = 200     # STUB, copying one activation's 32-byte table into HRAM
REQUANT = 300       # STUB, one output: shift, saturate, store
ELEMENT = 759       # rmsnorm, rope, silu, residuals: the residual, solved so
                    # the total matches the ROM's 23,326,656 exactly

ATT_SCORE = 187     # STUB
ATT_WEIGHT = 286    # STUB
ATT_SOFTMAX = 1395  # STUB, per head-position, independent of head size

CYCLES_PER_SECOND = 2_097_152


@dataclass
class Shape:
    dim: int = 64
    hidden: int = 172
    layers: int = 5
    heads: int = 8
    kv_heads: int = 4
    vocab: int = 512
    window: int = 24
    # Weight levels and activation width. 16 is the shipped 4-bit codebook and
    # runs the product-table kernel; 2 and 3 run the popcount kernel, whose cost
    # is linear in activation bits because it works one bit plane at a time.
    levels: int = 16
    act_bits: int = 8

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


def mac_cycles(levels, act_bits):
    """What one MAC costs on the cartridge, from the two direct benches.

    Ternary needs two weight planes - a sign and a non-zero mask - so it pays
    twice what binary does at the same activation width. Anything above three
    levels is the product table, which does not care how wide the activation is.
    """
    if levels > 3:
        return MAC_4BIT
    return MAC_BIT * max(act_bits, 1) * (2 if levels == 3 else 1)


def cost(s: Shape):
    """Cycles per token, broken down. Steady state, window full.

    The matvec line is DIRECT and the rest is mostly STUB, so the total is an
    upper bound and the *ratios between shapes* are what this is for.
    """
    macs = sum(i * o for i, o in s.matvecs())
    lut = sum(i for i, _ in s.matvecs()) + s.dim          # + the classifier's
    req = sum(o for _, o in s.matvecs()) + s.vocab

    head_pos = s.layers * s.heads * s.window
    att_macs = head_pos * s.head_size

    per_mac = mac_cycles(s.levels, s.act_bits)
    # A one-bit kernel has no per-activation table to build: the weight *is* the
    # index. That removes the LUT line along with most of the matvec.
    build = 0 if s.levels <= 3 else lut * LUT_BUILD

    return {
        "matvec": macs * per_mac,
        "classifier": s.vocab * s.dim * MAC_CLS,
        "lut builds": build,
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
