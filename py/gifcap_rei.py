"""Record build/rei.gbc in conversation, as an animated GIF: docs/versions/v1.0.gif.

    python py/gifcap_rei.py

The splash, then "hello" from the topic tree, "my name is tom" on the
keyboard (no tree line gives a name) and "what is my name" from the tree -
and her answers as they are typed. One frame per character
of hers and per button press; the time between presses is cut, and so is the
time she spends thinking before her first character, which the caption has to
say. Needs `.\\build.ps1 -Rei`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rei_shots as ui           # noqa: E402

OUT = ui.ROOT / "docs" / "versions" / "v1.0.gif"
SCALE = 2
DURATION = {"hold": 1800, "key": 350, "char": 70, "rest": 1600, "close": 3000}


class Recorder:
    def __init__(self, rom):
        self.rom, self.frames, self.durations = rom, [], []

    def frame(self, kind):
        self.rom.pyboy.tick(1, True)
        img = self.rom.pyboy.screen.image.convert("RGB")
        self.frames.append(img.resize((160 * SCALE, 144 * SCALE), 0))
        self.durations.append(DURATION[kind])

    def press(self, button):
        ui.press(self.rom, button)
        self.frame("key")


def exchange(rec, topic, line):
    r = rec.rom
    if r.read("wReiMode")[0] == 1 and r.read("wReiTopic")[0] != topic:
        rec.press("b")
    if r.read("wReiMode")[0] == 0:
        if r.read("wReiTopic")[0] // 5 != topic // 5:
            rec.press("right")
        while r.read("wReiTopic")[0] != topic:
            rec.press("down")
        rec.press("a")
    while r.read("wReiPick")[0] != line % 5:
        rec.press("down")
    ui.press(r, "a", after=0)
    seen = 0
    ready = r.addr("wReady")
    while r.pyboy.memory[ready] != r.defs["READY_MAGIC"]:
        r.pyboy.tick(2, False)
        n = r.read("wReiReplyLen")[0]
        if n != seen:
            seen = n
            rec.frame("char")
    r.pyboy.tick(8, False)
    rec.frame("rest")


def typed(rec, text):
    """The player's own line: the keyboard, one frame a key, then OK."""
    r = rec.rom
    if r.read("wReiMode")[0] != 2:
        rec.press("select")
    cell = r.read("wReiKey")[0]
    for ch in text + ui.OK:
        cell = ui.type_text(r, ch, cell)
        rec.frame("key")
    seen = 0
    ready = r.addr("wReady")
    while r.pyboy.memory[ready] != r.defs["READY_MAGIC"]:
        r.pyboy.tick(2, False)
        n = r.read("wReiReplyLen")[0]
        if n != seen:
            seen = n
            rec.frame("char")
    r.pyboy.tick(8, False)
    rec.frame("rest")
    rec.press("select")                          # back to the list


def main():
    if not ui.ROM.exists():
        sys.exit(f"{ui.ROM} missing - run .\\\\build.ps1 -Rei")
    r = ui.boot()
    rec = Recorder(r)
    r.pyboy.tick(150, False)
    rec.frame("hold")
    ui.press(r, "start", after=60)
    rec.frame("hold")
    exchange(rec, 0, 0)                          # hello
    typed(rec, "my name is tom")
    exchange(rec, 1, 0)                          # what is my name
    rec.frame("close")
    r.close()

    from PIL import Image
    colours = sorted({c for f in rec.frames for _, c in f.getcolors(maxcolors=1 << 16)})
    pal = Image.new("P", (1, 1))
    flat = [v for c in colours[:256] for v in c]
    pal.putpalette(flat + [0] * (768 - len(flat)))
    frames = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in rec.frames]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=rec.durations,
                   loop=0, optimize=True)
    print(f"wrote {OUT} ({len(frames)} frames, {sum(rec.durations) / 1000:.1f} s, "
          f"{OUT.stat().st_size / 1024:.0f} KB, {len(colours)} colours)")


if __name__ == "__main__":
    main()
