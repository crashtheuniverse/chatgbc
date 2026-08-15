"""Find the frame where the CPU derails.

Ticks one frame at a time and prints where the PC sits plus the LCD state. When
PyBoy's tick() stops returning, the PPU has stopped producing frames - which
means the LCD was switched off or the CPU reached a `stop`. The last line
printed before the hang is the state just before that happened.

Run it via Start-Process redirection, not a PowerShell pipeline: pipelines
buffer a child's stdout until it exits, so an incremental probe looks silent.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Rom  # noqa: E402

R_LCDC, R_IE, R_IF, R_SVBK, R_KEY1 = 0xFF40, 0xFFFF, 0xFF0F, 0xFF70, 0xFF4D


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    r = Rom()
    syms = sorted((a, n) for n, a in r.syms.items() if a < 0x8000)

    def near(pc):
        best = ("?", 0)
        for a, n in syms:
            if a <= pc:
                best = (n, a)
            else:
                break
        return f"{best[0]}+{pc - best[1]}"

    t0 = time.time()
    for i in range(limit):
        t = time.time()
        r.pyboy.tick(1, False)
        dt = time.time() - t
        if i % every == 0 or dt > 1.0:
            m = r.pyboy.memory
            pc = r.pyboy.register_file.PC
            print(
                f"f{i:>5} {time.time() - t0:7.1f}s dt={dt:5.2f} "
                f"PC={pc:#06x} {near(pc):<28} "
                f"LCDC={m[R_LCDC]:#04x} IE={m[R_IE]:#04x} IF={m[R_IF]:#04x} "
                f"SVBK={m[R_SVBK]:#04x} SP={r.pyboy.register_file.SP:#06x} "
                f"pos={r.read('wPos')[0]} lay={r.read('wLayer')[0]} "
                f"gen={r.read('wGenCount')[0]}",
                flush=True,
            )
        if dt > 5.0:
            print("STALLED - the line above is the last good frame", flush=True)
            r.close()
            return
    print("no stall", flush=True)
    r.close()


if __name__ == "__main__":
    main()
