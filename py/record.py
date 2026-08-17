"""Record the ROM generating text, as an animated GIF.

Captures the screen while the model runs so the token-by-token output is
visible, rather than only the finished frame.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Rom  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "run.gif"
SCALE = 3


def main():
    max_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    r = Rom()
    frames, last_count = [], -1

    def grab():
        img = r.pyboy.screen.image.convert("RGB")
        frames.append(img.resize((img.width * SCALE, img.height * SCALE), 0))

    for i in range(max_frames):
        # Render on the tick so screen.image is current.
        r.pyboy.tick(1, True)
        count = r.read("wGenCount")[0]
        if count != last_count:      # one frame per token emitted
            last_count = count
            grab()
            print(f"token {count} at frame {i}", flush=True)
        if r.read("wReady")[0] == r.defs["READY_MAGIC"]:
            break

    for _ in range(12):              # hold the final screen
        grab()

    frames[0].save(OUT, save_all=True, append_images=frames[1:],
                   duration=380, loop=0, optimize=True)
    print(f"wrote {OUT} ({len(frames)} frames, {OUT.stat().st_size // 1024} KB)")
    print(f"cycles/token: {r.read_u32('wTokCycles'):,}")
    r.close()


if __name__ == "__main__":
    main()
