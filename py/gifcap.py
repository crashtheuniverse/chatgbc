"""Record build/chatgbc.gbc generating text, as an animated GIF.

Two steps, deliberately separate:

    python py/gifcap.py capture     ROM -> captures/frame_NNNN.png
    python py/gifcap.py build       captures/*.png -> build/chatgbc.gif
    python py/gifcap.py             both

Splitting them means retiming, trimming or hand-picking frames costs nothing -
the emulator run is the slow part and it only has to happen once. captures/ is
gitignored.

One frame is captured per token emitted rather than per emulated frame. The ROM
prints a token every few seconds, which is fine on a handheld and useless as a
demo loop, so the result is honest about what it prints and dishonest only about
how long it took. The caption has to say so.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Rom, ROOT

CAPTURES = ROOT / "captures"
OUT = ROOT / "build" / "chatgbc.gif"

CAP = 170               # frame cap; generation normally ends first
OPEN_MS = 1500          # hold on the entry screen
STEP_MS = 120           # per token, which works out around 40x the hardware
CLOSE_MS = 2500         # and on the finished text, before the loop restarts
SCALE = 2


def grab(rom):
    rom.pyboy.tick(1, True)
    return rom.pyboy.screen.image.convert("RGB").resize(
        (160 * SCALE, 144 * SCALE), 0)


def capture():
    CAPTURES.mkdir(exist_ok=True)
    for old in CAPTURES.glob("frame_*.png"):
        old.unlink()

    rom = Rom()
    rom.pyboy.tick(400, False)                      # boot to the entry screen

    n = 0
    grab(rom).save(CAPTURES / f"frame_{n:04d}.png")
    n += 1

    rom.pyboy.button_press("start")
    rom.pyboy.tick(4, False)
    rom.pyboy.button_release("start")

    def printed():
        buf = rom.read("wConsole", rom.defs["CON_SIZE"])
        return sum(1 for b in buf if b != ord(" ") - rom.defs["FONT_FIRST"])

    # Stop on the ROM's own done-flag as well as the frame cap. Watching the
    # screen alone spins forever once generation ends, because nothing on it
    # changes again.
    ready, magic = rom.addr("wReady"), rom.defs["READY_MAGIC"]
    seen = printed()
    while n < CAP:
        rom.pyboy.tick(30, False)
        if rom.pyboy.memory[ready] == magic:
            print("  ROM finished generating", flush=True)
            break
        now = printed()
        if now != seen:
            seen = now
            grab(rom).save(CAPTURES / f"frame_{n:04d}.png")
            n += 1
            if n % 20 == 0:
                print(f"  {n} frames, {rom.read('wGenCount')[0]} tokens",
                      flush=True)
    rom.close()
    print(f"captured {n} frames into {CAPTURES}")


def build():
    from PIL import Image

    paths = sorted(CAPTURES.glob("frame_*.png"))
    if not paths:
        sys.exit(f"no frames in {CAPTURES} - run `gifcap.py capture` first")

    frames = [Image.open(p) for p in paths]
    frames.append(frames[-1])                       # hold the last one
    durations = [OPEN_MS] + [STEP_MS] * (len(frames) - 2) + [CLOSE_MS]
    frames[0].save(
        OUT, save_all=True, append_images=frames[1:],
        duration=durations, loop=0, optimize=True,
    )
    print(f"wrote {OUT} ({len(frames)} frames, {sum(durations) / 1000:.1f}s, "
          f"{OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "both"
    if what in ("capture", "both"):
        capture()
    if what in ("build", "both"):
        build()
