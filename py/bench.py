"""Measure how fast PyBoy actually runs this ROM, printing incrementally."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Rom  # noqa: E402


def main():
    frames = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    chunk = max(1, frames // 10)
    t0 = time.time()
    r = Rom()
    print(f"boot {time.time() - t0:.2f}s", flush=True)

    t0 = time.time()
    done = 0
    while done < frames:
        r.pyboy.tick(chunk, False)
        done += chunk
        dt = time.time() - t0
        print(f"{done:>6} frames  {dt:6.1f}s  {done / dt:7.1f} fps  "
              f"gen={r.read('wGenCount')[0]} pos={r.read('wPos')[0]} "
              f"layer={r.read('wLayer')[0]}", flush=True)
    print("cyc/token:", f"{r.read_u32('wTokCycles'):,}")
    print("output:", [l for l in r.console_lines()[6:] if l])
    r.close()


if __name__ == "__main__":
    main()
