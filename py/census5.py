"""Where a pip token goes, stage by stage, measured in place.

Runs the census ROM (build.ps1 -Census: the lab entry with cycle timers
compiled around every stage of the forward pass), generates a few tokens,
and prints each stage's share of a token. The classifier is not timed here -
its own bench already puts it at 921,088 - and whatever the stages and the
classifier together fail to explain is printed as the unaccounted tail, which
is the number this exists to shrink.

    python apps/v05/py/census5.py --tokens 6
"""

import argparse
import struct
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP
sys.path.insert(0, str(ROOT / "py"))
from harness import Rom          # noqa: E402
import export5                   # noqa: E402

# Stages 3 (sigmoid) and 17 (debug snapshots) keep their names so the tables
# line up across versions: the sigmoid is folded into the gate table, and
# the layer-0 snapshots assemble only into the lab ROM (build.ps1 -Lab), so
# the census - the shipping path with timers - reads 0 for both.
STAGES = [
    "rms_att", "wz matvec", "wz requant", "sigmoid", "wh matvec",
    "wh requant", "gate", "wo matvec", "wo requant", "add (att)",
    "rms_ffn", "w1 matvec", "w1 requant", "relu2", "w2 matvec",
    "w2 requant", "add (ffn)", "debug snapshots", "embed", "rms_final",
    "classifier",
]
HZ = 2_097_152


def counters(rom):
    rom.pyboy.memory[0xFF70] = 1
    raw = bytes(rom.read("wStage", len(STAGES) * 4))
    return [struct.unpack_from("<I", raw, i * 4)[0] for i in range(len(STAGES))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=6)
    args = ap.parse_args()

    rom = Rom(rom=APP / "build" / "chatgbc-census.gbc",
              sym=APP / "build" / "chatgbc-census.sym", lab=True)
    rom.pyboy.tick(400, False)
    before = counters(rom)
    rom.lab_run(steps=args.tokens, prompt=export5.PROMPT)
    after = counters(rom)
    rom.close()

    per = [(a - b) / args.tokens for a, b in zip(after, before)]
    total = sum(per)
    print(f"  {args.tokens} tokens through the census ROM\n")
    print("  {:<18}{:>12}{:>8}".format("stage", "cycles/tok", "share"))
    for name, cyc in sorted(zip(STAGES, per), key=lambda t: -t[1]):
        print("  {:<18}{:>12,.0f}{:>7.1%}".format(name, cyc, cyc / total))
    print(f"\n  staged total {total:,.0f} cycles/token = {total / HZ:.2f} s/token"
          f" (the app's own counter is the authority; the stages should sum"
          f" to within a percent of it)")


if __name__ == "__main__":
    main()
