"""Record build/chatgbc.gbc generating text, as an animated GIF.

The ROM prints roughly a token every five seconds, which is fine to watch on a
handheld and useless as a demo loop. So this captures one frame per token
emitted rather than one frame per emulated frame: the result is honest about
what the ROM prints and dishonest only about how long it took, which the caption
has to say out loud.

A GIF holds a still by giving one frame a long duration, not by repeating it -
repeating a frame and then also stretching each copy is how you end up with an
eleven-second pause on the title screen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Rom, ROOT

CAP = 170               # frame cap; generation normally ends first
OPEN_MS = 1500          # sit on the entry screen
STEP_MS = 120           # per token, which works out around 40x the hardware
CLOSE_MS = 2500         # and on the finished text, before the loop restarts
SCALE = 2


def grab(rom):
    rom.pyboy.tick(1, True)
    img = rom.pyboy.screen.image.convert("RGB")
    return img.resize((160 * SCALE, 144 * SCALE), 0)


def main():
    out = ROOT / "build" / "chatgbc.gif"
    rom = Rom()
    rom.pyboy.tick(400, False)                      # boot to the entry screen

    frames = [grab(rom)]
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
    while len(frames) < CAP:
        rom.pyboy.tick(30, False)
        if rom.pyboy.memory[ready] == magic:
            print("  ROM finished generating", flush=True)
            break
        now = printed()
        if now != seen:
            seen = now
            frames.append(grab(rom))
            if len(frames) % 20 == 0:
                print(f"  {len(frames)} frames, "
                      f"{rom.read('wGenCount')[0]} tokens", flush=True)

    frames.append(frames[-1])
    durations = [OPEN_MS] + [STEP_MS] * (len(frames) - 2) + [CLOSE_MS]
    frames[0].save(
        out, save_all=True, append_images=frames[1:],
        duration=durations, loop=0, optimize=True,
    )
    rom.close()
    secs = sum(durations) / 1000
    print(f"wrote {out} ({len(frames)} frames, {secs:.1f}s, "
          f"{out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
