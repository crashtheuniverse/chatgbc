"""Drive build/rei.gbc and photograph it: build/shots/*.png.

    python py/rei_shots.py

The six pictures the v1.0.0 review asks for - splash, canned, reply_mid (the
teletype running, her mouth open), reply_done (the mood shown), history,
keyboard - taken from one short conversation. Needs `.\\build.ps1 -Rei`.

The helpers here (boot, press, read the pane back, lay text out the way the
pane does) are also what py/tests/test_rei_ui.py drives the ROM with.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness                                  # noqa: E402

ROOT = harness.ROOT
ROM = ROOT / "build" / "rei.gbc"
SYM = ROOT / "build" / "rei.sym"
SHOTS = ROOT / "build" / "shots"

MAP = 0x9800
PANE_X, PANE_Y, PANE_W, PANE_H = 7, 1, 12, 7    # src/app/rei.inc
FACE_X, FACE_Y = 1, 1
KEYS = "abcdefghi" "jklmnopqr" "stuvwxyz " ".,!?'-;:" + '"'


def boot():
    return harness.Rom(rom=ROM, sym=SYM)


def press(r, button, hold=3, after=8):
    r.pyboy.button_press(button)
    r.pyboy.tick(hold, False)
    r.pyboy.button_release(button)
    r.pyboy.tick(after, False)


def tilemap(r):
    """The visible BG map, 18 rows of 20 tile numbers."""
    return [list(r.pyboy.memory[MAP + y * 32: MAP + y * 32 + 20]) for y in range(18)]


def row_text(r, y, x0=0, x1=20):
    """Font tiles as text; art tiles as '#'."""
    cells = r.pyboy.memory[MAP + y * 32 + x0: MAP + y * 32 + x1]
    return "".join(chr(t + 32) if t < 96 else "#" for t in cells)


def pane(r):
    return [row_text(r, PANE_Y + y, PANE_X, PANE_X + PANE_W) for y in range(PANE_H)]


def face_shown(r):
    """Which of the four pictures in wReiFaces is in VRAM, or None."""
    cells = []
    for y in range(4):
        a = MAP + (FACE_Y + y) * 32 + FACE_X
        cells += list(r.pyboy.memory[a:a + 4])
    faces = r.read("wReiFaces", 64)
    for i in range(4):
        if cells == list(faces[i * 16:(i + 1) * 16]):
            return i
    return None


def layout(text, w=PANE_W, h=PANE_H):
    """Python's copy of Rei_PanePut: what the pane shows after `text`."""
    rows = [[]]
    for ch in text:
        if ch == "\n":
            continue
        row = rows[-1]
        if not row:
            if ch == " ":
                continue                        # a row never starts with a space
        elif len(row) == w:
            if ch == " ":
                rows.append([])                 # the space is the line break
                continue
            k = 0                               # carry the unfinished word down
            for i in range(w - 1, -1, -1):
                if row[i] == " ":
                    k = w - 1 - i
                    break
            carried = row[w - k:] if k else []
            if k:
                row[w - k:] = [" "] * k
            rows.append(list(carried))
        rows[-1].append(ch)
    rows = rows[-h:]
    rows += [[]] * (h - len(rows))
    return ["".join(row).ljust(w) for row in rows]


def wait_ready(r, max_frames=40000, each_frame=None):
    """Tick until the reply is complete (wReady). Returns frames elapsed."""
    ready, magic = r.addr("wReady"), r.defs["READY_MAGIC"]
    for n in range(max_frames):
        r.pyboy.tick(1, False)
        if each_frame:
            each_frame()
        if r.pyboy.memory[ready] == magic:
            r.pyboy.tick(4, False)              # the help panel lands after wReady
            return n
    raise TimeoutError("the reply never finished")


def start(r):
    """Boot to the splash, then START to the main screen."""
    r.pyboy.tick(150, False)
    press(r, "start", after=30)


def pick(r, page, row):
    """From the top of page 0, move the list cursor there."""
    for _ in range(page):
        press(r, "right")
    for _ in range(row):
        press(r, "down")


def type_text(r, text, cell=0):
    """Type on the keyboard from cursor `cell`; returns the cursor after."""
    for ch in text:
        target = KEYS.index(ch)
        while cell % 9 != target % 9:
            press(r, "right")
            cell = (cell + 1) % 36
        while cell != target:
            press(r, "down")
            cell = (cell + 9) % 36
        press(r, "a")
    return cell


def main():
    if not ROM.exists():
        sys.exit(f"{ROM} missing - run .\\build.ps1 -Rei")
    SHOTS.mkdir(parents=True, exist_ok=True)
    r = boot()
    r.pyboy.tick(150, False)
    r.screenshot(SHOTS / "splash.png")
    press(r, "start", after=30)
    r.screenshot(SHOTS / "canned.png")

    press(r, "a")                               # "hello"
    wait_ready(r)
    press(r, "a")
    pick(r, 0, 2)                               # "my name is tom"
    press(r, "a")
    for _ in range(40000):                      # a few words in, mouth open
        r.pyboy.tick(1, False)
        if r.read("wReiReplyLen")[0] >= 9 and face_shown(r) == 3:
            break
    r.screenshot(SHOTS / "reply_mid.png")
    wait_ready(r)
    r.screenshot(SHOTS / "reply_done.png")

    press(r, "up")
    r.screenshot(SHOTS / "history.png")
    press(r, "down")

    press(r, "a")
    press(r, "select")
    type_text(r, "i like chess")
    r.screenshot(SHOTS / "keyboard.png")
    r.close()
    print(f"wrote six pictures to {SHOTS}")


if __name__ == "__main__":
    main()
