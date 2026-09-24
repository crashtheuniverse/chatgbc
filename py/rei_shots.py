"""Drive build/rei.gbc and photograph it: build/shots/*.png.

    python py/rei_shots.py

The pictures the reviews ask for - splash_menu (a save present), topics,
sentences (and sentences_page2), reply_mid (the teletype running, her mouth
open), reply_done (her reply up, the list back, START:LOG under the mood), log,
keyboard, and the world: world_beach, world_garden, world_playroom (walking),
world_<scene>_thought, world_pause, world_thought_mid, back_from_world - taken from one short conversation, a walk
on the beach and a power cycle. Needs `.\\build.ps1 -Rei`.

The helpers here (boot, press, read the pane back, lay text out the way the
pane and the log do) are also what the Rei test suites drive the ROM with.
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
OK = "\n"                                       # the keyboard's last cell: send
KEYS = "abcdefghi" "jklmnopqr" "stuvwxyz " ".,!?'-;:" + OK
REI_WANDERS = 20 * 60                           # src/app/rei.inc: idle frames before the world
LOG_MAP = 0x9C00                                # the log screen's own BG map
LOG_W, LOG_H = 18, 16


def boot(sram=None):
    """A cold boot; `sram` is the cartridge RAM an earlier instance left."""
    return harness.Rom(rom=ROM, sym=SYM, sram=sram)


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


def wrap(text, w, first=""):
    """Python's copy of the ROM's word wrap (Rei_PanePut, ReiLog_Put): every
    row `text` makes at width `w`, the first one opening with `first`."""
    rows = [list(first)]
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
    return ["".join(row).ljust(w) for row in rows]


def layout(text, w=PANE_W, h=PANE_H):
    """What her pane shows after `text`: the last `h` rows."""
    rows = wrap(text, w)[-h:]
    return rows + [" " * w] * (h - len(rows))


def log_rows(lines):
    """The log's rows for [(who, text)]: who is 1 for the player, 0 for her."""
    out = []
    for who, text in lines:
        out += [(who, row) for row in wrap(text, LOG_W, "> " if who else "")]
    return out


def log_screen(r):
    """The log screen's text rows, as (who, text); who from the row's palette."""
    rows = []
    for y in range(1, 1 + LOG_H):
        a = LOG_MAP + y * 32 + 1
        text = "".join(chr(t + 32) if t < 96 else "#" for t in r.pyboy.memory[a:a + LOG_W])
        rows.append((1 if r.pyboy.memory[1, a] else 0, text))
    return rows


def log_open(r):
    return bool(r.pyboy.memory[0xFF40] & 0x08)  # LCDC: the BG reads $9C00


def wait_ready(r, max_frames=40000, each_frame=None):
    """Tick until the reply is complete and saved (wReady), and the input
    screen is back. Sending clears wReady, so this is called after a send."""
    ready, magic = r.addr("wReady"), r.defs["READY_MAGIC"]
    for n in range(max_frames):
        r.pyboy.tick(1, False)
        if each_frame:
            each_frame()
        if r.pyboy.memory[ready] == magic:
            r.pyboy.tick(8, False)              # the list or the keys come back
            return n
    raise TimeoutError("the reply never finished")


def choose(r, topic, line):
    """From any state of the input screen: the cursor on sentence `line` of
    topic `topic` (both counted from 0), ready for A to send it."""
    if r.read("wReiMode")[0] == 2:
        press(r, "select")                      # the keyboard -> the list
    if r.read("wReiMode")[0] == 1 and r.read("wReiTopic")[0] != topic:
        press(r, "b")                           # up to the topics
    if r.read("wReiMode")[0] == 0:
        if r.read("wReiTopic")[0] // 5 != topic // 5:
            press(r, "right")                   # the other column
        press_until(r, "down", lambda: r.read("wReiTopic")[0] == topic)
        press(r, "a")
    assert r.read("wReiMode")[0] == 1 and r.read("wReiTopic")[0] == topic
    if r.read("wReiPage")[0] != line // 5:
        press(r, "right")
    press_until(r, "down", lambda: r.read("wReiPick")[0] == line % 5)


def type_text(r, text, cell=0):
    """Type on the keyboard from cursor `cell`; returns the cursor after.
    Left and right run round the whole grid; up and down stay inside it (off
    the top or bottom row they page her replies instead)."""
    for ch in text:
        target = KEYS.index(ch)
        while cell % 9 != target % 9:
            press(r, "right")
            cell = (cell + 1) % 36
        while cell != target:
            step = "down" if cell < target else "up"
            press(r, step)
            cell += 9 if step == "down" else -9
        press(r, "a")
    return cell


# --- the world ---------------------------------------------------------------

THINK_W, THINK_H = 18, 4                        # the thought box, on the window map


def world_on(r):
    return bool(r.read("wWorldOn")[0])


def to_world(r):
    """The only way there: nobody touches anything. The idle counter is WRAM,
    so the wait is a moment instead of twenty seconds."""
    set_word(r, "wReiIdle", REI_WANDERS - 8)
    r.pyboy.tick(30, False)
    assert world_on(r)


def set_word(r, name, value):
    a = r.addr(name)
    r.pyboy.memory[a] = value & 0xFF
    r.pyboy.memory[a + 1] = value >> 8


def thought_box(r):
    """The thought box's four rows of text, off the window's map."""
    rows = []
    for y in range(1, 1 + THINK_H):
        a = LOG_MAP + y * 32 + 1
        rows.append("".join(chr(t + 32) if t < 96 else "#" for t in r.pyboy.memory[a:a + THINK_W]))
    return rows


def think_now(r, max_frames=200):
    """Run the thought timer out; returns once the thought has begun."""
    set_word(r, "wWorldThinkT", 2)
    for _ in range(max_frames):
        r.pyboy.tick(1, False)
        if r.read("wWorldThinking")[0]:
            return
    raise TimeoutError("she never started thinking")


def thought_done(r, max_frames=40000, each_frame=None):
    """Tick until the thought is whole and lingering in the box."""
    a = r.addr("wWorldLinger")
    for _ in range(max_frames):
        r.pyboy.tick(1, False)
        if each_frame:
            each_frame()
        if r.pyboy.memory[a] | r.pyboy.memory[a + 1]:
            r.pyboy.tick(6, False)              # the last cell, or the last rows of a wrap
            return
    raise TimeoutError("the thought never finished")


def press_until(r, button, done, most=12):
    """Press `button` until `done()`. Bounded: a screen that is not listening
    (the log left open by a failed test) must fail, not hang the suite."""
    for _ in range(most):
        if done():
            return
        press(r, button)
    assert done(), f"{button} never got there"


def main():
    if not ROM.exists():
        sys.exit(f"{ROM} missing - run .\\build.ps1 -Rei")
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in ("canned.png", "reply_done_input.png", "world_walk.png", "world_thought_done.png",
                "world_idle.png"):
        (SHOTS / old).unlink(missing_ok=True)
    r = boot()
    r.pyboy.tick(150, False)
    press(r, "start", after=60)
    r.screenshot(SHOTS / "topics.png")
    press(r, "a")                               # the first topic: hello
    r.screenshot(SHOTS / "sentences.png")

    press(r, "a", after=0)                      # "hello"
    for _ in range(40000):                      # a few words in, mouth open
        r.pyboy.tick(1, False)
        if r.read("wReiReplyLen")[0] >= 9 and face_shown(r) == 3:
            break
    r.screenshot(SHOTS / "reply_mid.png")
    wait_ready(r)
    r.screenshot(SHOTS / "reply_done.png")      # a heart, START:LOG under it, the list back

    choose(r, 1, 0)                             # me: "my name is tom"
    press(r, "a", after=0)
    wait_ready(r)
    choose(r, 1, 2)                             # "what is my name"
    press(r, "a", after=0)
    wait_ready(r)
    choose(r, 2, 8)                             # rei, second page
    r.screenshot(SHOTS / "sentences_page2.png")
    press(r, "start", after=12)
    r.screenshot(SHOTS / "log.png")
    press(r, "select", after=12)

    press(r, "select")
    type_text(r, "i like chess")
    r.screenshot(SHOTS / "keyboard.png")

    r.pyboy.memory[r.addr("wWorldRng")] = 40
    r.pyboy.memory[r.addr("wWorldTurn")] = 0        # the first scene is seeded at START: pin it
    for scene in ("beach", "garden", "playroom"):   # left alone: each visit the next scene
        to_world(r)
        set_word(r, "wWorldThinkT", 60000)      # no thought until the walk is on film
        for _ in range(600):
            r.pyboy.tick(1, False)
            if not r.read("wWorldAct")[0] and r.pyboy.memory[0xFE02] == 16:
                break
        r.screenshot(SHOTS / f"world_{scene}.png")
        if scene == "beach":
            for _ in range(3000):
                r.pyboy.tick(1, False)
                if r.read("wWorldAct")[0]:
                    break
            r.pyboy.tick(4, False)
            r.screenshot(SHOTS / "world_pause.png")
        think_now(r)
        if scene == "beach":
            for _ in range(40000):
                r.pyboy.tick(1, False)
                if r.read("wReiReplyLen")[0] >= 12:
                    break
            r.screenshot(SHOTS / "world_thought_mid.png")
        thought_done(r)
        r.screenshot(SHOTS / f"world_{scene}_thought.png")
        if scene != "playroom":
            press(r, "b", after=12)
    press(r, "b", after=12)
    r.screenshot(SHOTS / "back_from_world.png")
    saved = r.sram()
    r.close()

    r = boot(saved)                             # the power switch
    r.pyboy.tick(150, False)
    r.screenshot(SHOTS / "splash_menu.png")
    r.close()
    print(f"wrote the pictures to {SHOTS}")


if __name__ == "__main__":
    main()
