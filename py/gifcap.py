"""Record build/chatgbc.gbc being used, as an animated GIF.

Two steps, deliberately separate:

    python py/gifcap.py capture     ROM -> captures/frame_NNNN_phase.png
    python py/gifcap.py build       captures/*.png -> build/chatgbc.gif
    python py/gifcap.py             both

Splitting them means retiming, trimming or hand-picking frames costs nothing -
the emulator run is the slow part and it only has to happen once. captures/ is
gitignored.

The capture can drive the on-screen keyboard before pressing START - see TYPE
below. Kb_PickPrompt fixes the opening prompt at boot on purpose, so typing is
the only way a capture can show any other prompt, or the keyboard at all.

During generation one frame is captured per token rather than per emulated
frame. The ROM prints a token every few seconds, which is honest on a handheld
and useless as a demo loop, so the result is truthful about what it prints and
untruthful only about how long it took. The caption has to say so.
"""

import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Rom, ROOT

CAPTURES = ROOT / "captures"
OUT = ROOT / "build" / "chatgbc.gif"

# Appended to the prompt the ROM opens with, on the keyboard. Empty ships the
# iconic opener as-is. The machinery stays because Kb_PickPrompt fixes the first
# prompt at boot on purpose, so this is the only way a capture can demonstrate
# any other one - or the keyboard itself.
TYPE = ""
CAP = 220                    # token cap; generation normally ends first
SCALE = 2

OPEN_MS = 1800               # hold on the entry screen before anything happens
KEY_MS = 70                  # per button press while typing
SETTLE_MS = 900              # on the finished prompt, before START
TOKEN_MS = 90                # per token, which works out around 100x hardware
CLOSE_MS = 3000              # on the finished text, before the loop restarts

DURATION = {"open": OPEN_MS, "key": KEY_MS, "settle": SETTLE_MS,
            "tok": TOKEN_MS}

# The layout in src/keyboard.asm, lower case. Cell index is row * 9 + column.
LAYOUT = "abcdefghi" "jklmnopqr" "stuvwxyz " ".,!?'-;:" + '"'
COLS, CELLS = 9, len(LAYOUT)

# Left and right step the cell index by one and wrap across the whole grid, not
# per row; up and down step by a row and wrap the same way. So the keyboard is a
# ring of 36 with strides of 1 and 9, and the fewest presses between two cells
# is a four-move breadth-first search rather than a row/column difference.
MOVES = {"right": 1, "left": -1, "down": COLS, "up": -COLS}


def path_between(src, dst):
    """Fewest button presses from cell `src` to cell `dst`."""
    seen, queue = {src: []}, deque([src])
    while queue:
        cell = queue.popleft()
        if cell == dst:
            return seen[cell]
        for name, step in MOVES.items():
            nxt = (cell + step) % CELLS
            if nxt not in seen:
                seen[nxt] = seen[cell] + [name]
                queue.append(nxt)
    raise AssertionError(f"no path {src} -> {dst}")


class Recorder:
    def __init__(self, rom):
        self.rom = rom
        self.n = 0
        CAPTURES.mkdir(exist_ok=True)
        for old in CAPTURES.glob("frame_*.png"):
            old.unlink()

    def frame(self, phase):
        self.rom.pyboy.tick(1, True)
        img = self.rom.pyboy.screen.image.convert("RGB")
        img.resize((160 * SCALE, 144 * SCALE), 0).save(
            CAPTURES / f"frame_{self.n:04d}_{phase}.png")
        self.n += 1

    def press(self, button, phase="key"):
        self.rom.pyboy.button_press(button)
        self.rom.pyboy.tick(3, False)
        self.rom.pyboy.button_release(button)
        self.rom.pyboy.tick(3, False)
        self.frame(phase)


def type_text(rec, text):
    """Walk the cursor to each letter and press A, a frame per press.

    Frames are taken unconditionally here. The generation loop below captures on
    a change in the console buffer, which would drop every cursor move: the
    cursor is a CGB attribute in VRAM bank 1 and never touches that buffer.
    """
    cell = 0                                    # Keyboard_Run starts on 'a'
    for ch in text:
        target = LAYOUT.index(ch)
        for button in path_between(cell, target):
            rec.press(button)
        rec.press("a")
        cell = target


def capture():
    rom = Rom()
    rom.pyboy.tick(400, False)                  # boot to the entry screen
    rec = Recorder(rom)
    rec.frame("open")

    if TYPE:
        type_text(rec, TYPE)
        rec.frame("settle")

    prompt_len = rom.read("wPromptLen")[0]
    prompt = bytes(rom.read("wPromptText", prompt_len)).decode("ascii")
    print(f"  prompt: {prompt!r}")

    rec.press("start", phase="settle")

    def screen():
        """The whole shadow buffer, not a count of what is on it.

        Counting non-blank cells stops changing the moment the screen fills and
        starts scrolling - which is exactly the part of a long run worth
        watching, and it would have dropped every frame of it."""
        return bytes(rom.read("wConsole", rom.defs["CON_SIZE"]))

    # Stop on the ROM's own done-flag as well as the token cap. Watching the
    # screen alone spins forever once generation ends, because nothing on it
    # changes again.
    ready, magic = rom.addr("wReady"), rom.defs["READY_MAGIC"]
    seen, tokens = screen(), 0
    while tokens < CAP:
        rom.pyboy.tick(30, False)
        if rom.pyboy.memory[ready] == magic:
            print("  ROM finished generating", flush=True)
            break
        now = screen()
        if now != seen:
            seen = now
            rec.frame("tok")
            tokens += 1
            if tokens % 40 == 0:
                print(f"  {tokens} tokens", flush=True)
    rom.close()
    print(f"captured {rec.n} frames into {CAPTURES}")


def build():
    from PIL import Image

    paths = sorted(CAPTURES.glob("frame_*.png"))
    if not paths:
        sys.exit(f"no frames in {CAPTURES} - run `gifcap.py capture` first")

    frames = [Image.open(p).convert("RGB") for p in paths]
    durations = [DURATION[p.stem.split("_")[2]] for p in paths]

    # Quantize every frame against one fixed palette, taken from the colours the
    # ROM actually produces, with dithering off. Letting PIL pick a palette per
    # frame is what speckles flat areas and makes text edges crawl - there are
    # only ever four colours on this screen, so none of that is necessary.
    seen = sorted({c for f in frames for _, c in f.getcolors(maxcolors=1 << 16)})
    flat = [v for c in seen for v in c]
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat + [0] * (768 - len(flat)))
    frames = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    print(f"  {len(seen)} colours, fixed palette, no dithering")

    frames.append(frames[-1])                   # hold the last one
    durations.append(CLOSE_MS)
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
