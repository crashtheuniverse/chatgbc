"""Find the frame where the CPU derails.

Ticks one frame at a time, recording where the PC sits, and stops as soon as a
single tick takes an abnormally long time - which is what happens when the CPU
falls into a STOP or an unreachable loop and the PPU stops producing frames.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Rom  # noqa: E402


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    r = Rom()
    syms = sorted((a, n) for n, a in r.syms.items() if a < 0x8000)

    def near(pc):
        lo, hi = 0, len(syms) - 1
        best = ("?", 0)
        for a, n in syms:
            if a <= pc:
                best = (n, a)
            else:
                break
        return f"{best[0]}+{pc - best[1]}"

    history = []
    t0 = time.time()
    for i in range(limit):
        t = time.time()
        r.pyboy.tick(1, False)
        dt = time.time() - t
        pc = r.pyboy.register_file.PC
        history.append((i, pc))
        if i % 25 == 0:
            print(f"f{i:>5} {time.time() - t0:7.1f}s  PC {pc:#06x} {near(pc)}  "
                  f"pos={r.read('wPos')[0]} layer={r.read('wLayer')[0]} "
                  f"gen={r.read('wGenCount')[0]}", flush=True)
        if dt > 2.0:
            print(f"frame {i}: tick took {dt:.1f}s - CPU derailed", flush=True)
            print(f"  PC {pc:#06x} = {near(pc)}", flush=True)
            print("  last PCs before the stall:", flush=True)
            for j, p in history[-12:-1]:
                print(f"    f{j} {p:#06x} {near(p)}", flush=True)
            print(f"  pos={r.read('wPos')[0]} layer={r.read('wLayer')[0]} "
                  f"gen={r.read('wGenCount')[0]}", flush=True)
            r.close()
            return
    print(f"no stall in {limit} frames; PC {r.pyboy.register_file.PC:#06x} "
          f"= {near(r.pyboy.register_file.PC)}", flush=True)
    print(f"pos={r.read('wPos')[0]} layer={r.read('wLayer')[0]} "
          f"gen={r.read('wGenCount')[0]}", flush=True)
    r.close()


if __name__ == "__main__":
    main()
