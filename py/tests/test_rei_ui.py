"""The Rei screen shows exactly what the model said, where it should - and the
cartridge remembers it.

Drives build/rei.gbc (the app ROM with the game screen) through a conversation
(the topic tree, the keyboard, the log) and checks it against the integer twin
turn by turn. The first group of tests
shares one booted ROM and one twin state and runs in file order: each leaves
the conversation where the next picks it up. The save tests at the end power
the cartridge off and on: a new emulator booted with the cartridge RAM the
last one left (harness.Rom.sram), nothing touching the disk.

Only meaningful for the chat export - `.\\build.ps1 -Rei` and the chat
environment (test.ps1 sets both up); skipped otherwise.
"""
import copy
import re

import pytest

import export5                    # noqa: E402
from conftest import APP

if not export5.CHAT:
    pytest.skip("the Rei suite needs the chat export", allow_module_level=True)
if not (APP / "build" / "rei.gbc").exists():
    pytest.skip("build/rei.gbc missing - run .\\build.ps1 -Rei", allow_module_level=True)

import golden5                    # noqa: E402
import harness                    # noqa: E402
import rei_shots as ui            # noqa: E402
import twin5                      # noqa: E402
from model5 import Model5, Tokenizer   # noqa: E402

ART = harness.load_defs(APP / "src" / "rei_art.inc")
HAPPY, SAD = 1, 3                 # MOOD_* in src/app/rei.inc

PANE = {(x, y) for x in range(7, 19) for y in range(1, 8)}
FACE = {(x, y) for x in range(1, 5) for y in range(1, 5)}
MOOD = {(x, y) for x in range(0, 6) for y in range(6, 9)}
MARKER = {(x, 8) for x in range(13, 18)}
# src/app/rei_save.asm: 2,195 bytes, and the name slot's twelve with the name
# opcodes (version 2)
NAME_OPS = "NAME_OPS" in harness.load_defs(APP / "src" / "model.inc")
SAVE_BODY = 11 + 192 + 8 * 97 + 64 * 19 + (12 if NAME_OPS else 0)
MAGIC = b"REI" + bytes([2 if NAME_OPS else 1])


import rei_topics                 # noqa: E402
from rei_talk import Talk, measured, twin, where   # noqa: E402,F401  (twin is a fixture)


@pytest.fixture(scope="module")
def talk(twin):
    t = Talk(twin)
    yield t
    t.rom.close()


def changed(before, after):
    return {(x, y) for y in range(18) for x in range(20) if before[y][x] != after[y][x]}


def test_topics_are_in_vocabulary_and_in_the_rom():
    """Every sentence encodes with no unknown piece (py/rei_topics.py asked the
    twin about each when the table was made), and the table the ROM carries is
    the one that script holds."""
    tok = Tokenizer()
    rei_topics.check_shape()
    for _, lines in rei_topics.TOPICS:
        for s in lines:
            assert 0 not in tok.encode("> " + s + "\n"), f"{s!r} has an unknown piece"
    inc = (APP / "src" / "rei_topics.inc").read_text(encoding="utf-8")
    assert re.findall(r'^    db "([^"]*)", 0', inc, re.M) == \
        [s for _, lines in rei_topics.TOPICS for s in lines]
    assert [n.strip() for n in re.findall(r'^    db "([^"]{8})"$', inc, re.M)] == \
        [name for name, _ in rei_topics.TOPICS]


def test_splash_then_start(talk):
    r = talk.rom
    r.pyboy.tick(150, False)
    assert ui.row_text(r, 10).strip() == "PRESS START"
    assert "continue" not in ui.row_text(r, 9), "a blank cartridge has nothing to continue"
    assert "v1.0.0" in ui.row_text(r, 14)
    assert r.read("wReady")[0] == 0
    r.pyboy.tick(120, False)
    assert ui.row_text(r, 10).strip() == "PRESS START", "the splash waits for START"
    ui.press(r, "start", after=60)
    m = ui.tilemap(r)
    assert m[0][0] == ART["T_FR_TL"] and m[11][19] == ART["T_FR_BR"]
    assert ui.row_text(r, 0, 8, 11) == "REI"


def art_map(label):
    """The rows of tile numbers under `label` in src/rei_art.inc."""
    text = (APP / "src" / "rei_art.inc").read_text(encoding="utf-8")
    body = text.split(f"{label}::")[1].split("\n\n")[0]
    return [[int(v) for v in line.split("db")[1].split(",")]
            for line in body.splitlines() if line.strip().startswith("db")]


def bar(name, page=None):
    """The bar's twenty tiles as the generator drew them; `page` (0 or 1) lays
    the "<>:PAGE n/2" span over the sentences' bar."""
    tiles = list(art_map(f"ReiBar{name}")[0])
    if page is not None:
        x = ART["BAR_PAGE_X"]
        tiles[x:x + ART["BAR_PAGE_W"]] = art_map("ReiBarPages")[page]
    return tiles


def bar_row(r):
    return ui.tilemap(r)[12]


def test_the_bars_say_what_they_should():
    """The bar is tiny capitals drawn as tiles, so the screen tests below can
    only compare tile numbers; this one reads the words."""
    import gen_rei_art as art
    assert art.BARS["TOPICS"].split() == ["TOPIC", "<^v>:MOVE", "A:SELECT", "SEL:KEYS"]
    assert art.BARS["LINES"].split() == ["SAY", "A:SAY", "B:BACK", "SEL:KEYS"]
    assert art.BARS["KEYS"].split() == ["KEYS", "A:TYPE", "B:DEL", "OK:SAY", "SEL:LIST"]
    assert [t.strip() for t in art.BAR_PAGES] == ["<>:PAGE 1/2", "<>:PAGE 2/2"]
    for text in art.BARS.values():
        assert len(text) == 40 and text[0] == " " and text[-1] != " "
    assert ART["REI_MAIN_TILES"] <= 152
    assert len({tuple(bar("Topics")), tuple(bar("Lines")), tuple(bar("Lines", 0)),
                tuple(bar("Lines", 1)), tuple(bar("Keys"))}) == 5


def test_the_thinking_dots_are_centred():
    """While she thinks, the middle of the five rows is three dots whose middle
    one is on the screen's centre line (pixels 79 and 80 of 160), the others
    sixteen pixels either side: the row the generator drew, cut into tiles."""
    import gen_rei_art as art
    row = art.think_row()
    ink = [x for x in range(160) if any(row[y][x] for y in range(8))]
    assert ink == [63, 64, 79, 80, 95, 96]
    tiles = art_map("ReiThinkMap")[0]
    blank = ART["REI_TILE_BASE"]                    # T_BLANK: the rest of the row is paper
    assert [x for x, t in enumerate(tiles) if t != blank] == [7, 8, 9, 10, 11, 12]


def bar_is_solid(r):
    attrs = r.pyboy.memory[1, 0x9800 + 12 * 32: 0x9800 + 12 * 32 + 20]
    return all(a == ART["PAL_PICK"] for a in attrs)


def frame_tiles_below_the_bar(r):
    frame = {v for k, v in ART.items() if k.startswith("T_FR_")}
    m = ui.tilemap(r)
    return [(x, y) for y in range(12, 18) for x in range(20) if m[y][x] in frame]


def cursor_cells(r):
    return {(x, y) for y in range(13, 18) for x in range(20)
            if r.pyboy.memory[1, 0x9800 + y * 32 + x] == ART["PAL_CURSOR"]}


def test_first_screen_is_the_topics(talk):
    r = talk.rom
    assert r.read("wReiMode")[0] == 0
    assert bar_row(r) == bar("Topics")
    assert bar_is_solid(r) and not frame_tiles_below_the_bar(r)
    names = [name for name, _ in rei_topics.TOPICS]
    for i in range(5):
        assert ui.row_text(r, 13 + i, 1, 9).rstrip() == names[i]
        assert ui.row_text(r, 13 + i, 11, 19).rstrip() == names[5 + i]
    assert ui.tilemap(r)[13][0] == ART["T_ARROW_R"]
    assert cursor_cells(r) == {(x, 13) for x in range(10)}
    assert ui.row_text(r, 10, 1, 19).strip() == "", "nothing is chosen yet"
    assert ui.pane(r) == [" " * 12] * 7, "she has not spoken yet"
    assert ui.row_text(r, 8, 7, 19) == "#" * 12, "no paging marker in her frame"
    assert ui.face_shown(r) in (0, 1)


def test_the_grid_wraps(talk):
    r = talk.rom
    for button, topic in (("up", 4), ("down", 0), ("left", 5), ("down", 6), ("right", 1), ("up", 0)):
        ui.press(r, button)
        assert r.read("wReiTopic")[0] == topic, button
    ui.press(r, "right")
    ui.press(r, "down")
    assert cursor_cells(r) == {(x, 14) for x in range(10, 20)}
    assert ui.tilemap(r)[14][10] == ART["T_ARROW_R"]
    ui.press(r, "left")
    ui.press(r, "up")
    assert r.read("wReiTopic")[0] == 0


def test_a_topic_opens_its_sentences(talk):
    r = talk.rom
    ui.press_until(r, "down", lambda: r.read("wReiTopic")[0] == 2)     # rei: ten sentences
    ui.press(r, "a")
    lines = rei_topics.TOPICS[2][1]
    assert r.read("wReiMode")[0] == 1
    assert bar_row(r) == bar("Lines", 0) and bar_is_solid(r)     # "<>:PAGE 1/2"
    assert [ui.row_text(r, 13 + i, 1, 20).rstrip() for i in range(5)] == lines[:5]
    assert cursor_cells(r) == {(x, 13) for x in range(20)}
    assert ui.row_text(r, 10, 1, 19).rstrip() == lines[0], "the prompt row shows what A sends"
    ui.press(r, "up")                               # wraps inside the page
    assert r.read("wReiPick")[0] == 4
    ui.press(r, "right")                            # the other page
    assert bar_row(r) == bar("Lines", 1)
    assert [ui.row_text(r, 13 + i, 1, 20).rstrip() for i in range(5)] == lines[5:]
    assert ui.row_text(r, 10, 1, 19).rstrip() == lines[9]
    ui.press(r, "left")
    ui.press(r, "b")                                # back up, the cursor where it was
    assert r.read("wReiMode")[0] == 0 and r.read("wReiTopic")[0] == 2
    assert ui.row_text(r, 10, 1, 19).strip() == ""

    ui.choose(r, 0, 0)                              # hello: two pages too
    short = [t for t, (_, lines) in enumerate(rei_topics.TOPICS) if 5 < len(lines) < 10]
    assert short, "a topic whose second page is shorter than the first"
    ui.choose(r, short[0], 0)                       # things: nine sentences, four on page 2
    ui.press_until(r, "down", lambda: r.read("wReiPick")[0] == 4)
    ui.press(r, "right")
    assert r.read("wReiPick")[0] == len(rei_topics.TOPICS[short[0]][1]) - 6,         "the cursor stays on a sentence"
    assert ui.row_text(r, 17, 1, 20).strip() == ""
    ui.press(r, "b")


def test_hello_lands_in_the_pane_only(talk):
    r = talk.rom
    ui.choose(r, 0, 0)
    want = talk.expect("hello")
    before = ui.tilemap(r)
    ui.press(r, "a", after=0)

    type_on = r.addr("wTypeOn")
    seen = {"last": None, "stray": set(), "frames": 0, "mouth": False}

    def watch():
        if not r.pyboy.memory[type_on]:
            seen["last"] = None
            return
        now = ui.tilemap(r)
        if seen["last"] is not None:
            seen["stray"] |= changed(seen["last"], now) - PANE - FACE
        seen["last"] = now
        seen["frames"] += 1
        seen["mouth"] |= ui.face_shown(r) == 3

    ui.wait_ready(r, each_frame=watch)
    assert seen["frames"] > 100, "the teletype never ran"
    assert not seen["stray"], f"tiles changed outside her pane during the reply: {sorted(seen['stray'])}"
    assert seen["mouth"], "her mouth never opened"

    # Back in the state it was sent from: the same topic, page and cursor.
    after = ui.tilemap(r)
    assert not changed(before, after) - PANE - FACE - MOOD
    assert r.read("wReiMode")[0] == 1 and r.read("wReiTopic")[0] == 0
    assert cursor_cells(r) == {(x, 13) for x in range(20)}, "the cursor is back"
    assert bar_is_solid(r)

    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    assert r.read("wReiMood")[0] == ui.mood_of(want)
    if measured():
        assert "rei" in want and ui.mood_of(want) == HAPPY     # "hello! i am rei."
    assert ui.face_shown(r) in (0, 1)
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hello", "the prompt row shows what A would send"


def test_the_state_carries(talk):
    talk.type("my name is tom")                     # typed: no tree line gives a name
    want = talk.send(*where("what is my name"))     # me: a follow-up
    if measured():
        assert "tom" in want, "she forgot the name"
    talk.send(*where("tell me a story"))            # play, second page


def test_up_and_down_belong_to_the_list(talk):
    """Her pane no longer pages: whatever the d-pad does, her last reply stays."""
    r = talk.rom
    pane = ui.pane(r)
    for button in ("up", "up", "down", "left", "right", "b", "up", "down", "left"):
        ui.press(r, button)
        assert ui.pane(r) == pane
    assert ui.row_text(r, 8, 7, 19) == "#" * 12


def test_keyboard_and_the_ok_key(talk):
    r = talk.rom
    ui.choose(r, 3, 1)                              # somewhere in the list
    ui.press(r, "select")
    assert r.read("wReiMode")[0] == 2
    assert bar_row(r) == bar("Keys") and bar_is_solid(r)
    assert ui.row_text(r, 13, 1, 18) == "a b c d e f g h i"
    assert ui.tilemap(r)[16][17] == ART["T_OK"]
    assert ui.row_text(r, 17).strip() == "" and not frame_tiles_below_the_bar(r)
    cell = r.read("wReiKey")[0]                     # where the name was typed left it
    assert cursor_cells(r) == {(1 + 2 * (cell % 9), 13 + cell // 9)}
    ui.move_key(r, cell, 0)
    assert cursor_cells(r) == {(1, 13)}
    ui.press(r, "up")                               # the keys wrap, top to bottom
    assert r.read("wReiKey")[0] == 27
    ui.press(r, "down")

    cell = ui.type_text(r, ui.OK, 0)
    assert r.read("wReady")[0] and not r.read("wTypeOn")[0], "an empty message is not sent"
    cell = ui.type_text(r, "hiz", cell)
    ui.press(r, "b")                                # B deletes
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hi_"

    ui.press(r, "start", after=12)                  # START is the log, not send
    assert ui.log_open(r) and r.read("wReady")[0] and not r.read("wTypeOn")[0]
    ui.press(r, "select", after=12)
    assert not ui.log_open(r)
    assert r.read("wReiMode")[0] == 2, "leaving the log is not a mode switch"
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hi_"
    assert cursor_cells(r) == {(1 + 2 * (cell % 9), 13 + cell // 9)}

    want = talk.expect("hi")
    ui.type_text(r, ui.OK, cell)
    assert not r.read("wReady")[0]
    ui.wait_ready(r)
    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    assert ui.row_text(r, 13, 1, 18) == "a b c d e f g h i", "the keyboard is back"
    assert ui.row_text(r, 10, 1, 19).rstrip() == "_"
    ui.press(r, "select")                           # and SELECT goes back to where the list was
    assert r.read("wReiMode")[0] == 1 and r.read("wReiTopic")[0] == 3 and r.read("wReiPick")[0] == 1
    ui.press(r, "select")
    ui.press(r, "select")
    assert not ui.world_on(r), "SELECT is never the world"


def bg_palette(r, slot):
    """A BG palette's eight bytes, read back through BCPS/BCPD."""
    out = []
    for i in range(8):
        r.pyboy.memory[0xFF68] = slot * 8 + i
        out.append(r.pyboy.memory[0xFF69])
    return bytes(out)


def test_the_log_shows_both_sides(talk):
    r = talk.rom
    # "do you dream", and more of the rei topic until the log has rows to
    # scroll - how many that takes is up to the model
    for line in (5, 6, 7, 1, 0, 4):
        talk.send(2, line)
        rows = ui.log_rows(talk.lines)
        if len(rows) > ui.LOG_H:
            break
    assert len(rows) > ui.LOG_H
    main = ui.tilemap(r)
    attrs = bytes(r.pyboy.memory[1, 0x9800:0x9800 + 18 * 32])
    cursor = bg_palette(r, ART["PAL_CURSOR"])

    ui.press(r, "start", after=12)
    assert ui.log_open(r)
    assert ui.row_text(r, 0, 8, 11) == "REI", "the main screen's map is not the one showing"
    assert ui.log_screen(r) == rows[-ui.LOG_H:], "newest at the bottom"
    assert rows[0] == (1, "> hello".ljust(18))
    top = r.pyboy.memory[ui.LOG_MAP + 17], r.pyboy.memory[ui.LOG_MAP + 17 * 32 + 17]
    assert top == (ART["T_ARROW_UP"], ART["T_FR_B"]), "more above, nothing below"
    assert bg_palette(r, ART["PAL_CURSOR"]) != cursor, "the player's blue is in the slot"

    ui.press(r, "up", after=12)
    assert ui.log_screen(r) == rows[-ui.LOG_H - 1:-1]
    r.pyboy.button_press("up")                      # held: it repeats to the top
    r.pyboy.tick(40 + 6 * len(rows), False)
    r.pyboy.button_release("up")
    r.pyboy.tick(12, False)
    assert ui.log_screen(r) == rows[:ui.LOG_H]
    ui.press(r, "down", after=12)
    assert ui.log_screen(r) == rows[1:ui.LOG_H + 1]

    ui.press(r, "select", after=12)
    assert not ui.log_open(r)
    assert ui.tilemap(r) == main, "the main screen is as it was"
    assert bytes(r.pyboy.memory[1, 0x9800:0x9800 + 18 * 32]) == attrs
    assert bg_palette(r, ART["PAL_CURSOR"]) == cursor, "and so is the cursor's palette"
    assert r.read("wReiMode")[0] == 1


def test_speed_is_on_record(talk):
    r = talk.rom
    n = r.read("wGenCount")[0]
    assert n and 300_000 < r.read_u32("wGenTotal") // n < 1_200_000


# --- the battery save --------------------------------------------------------

def menu(r):
    """Boot to the splash; True if it offers to continue."""
    r.pyboy.tick(150, False)
    return ui.row_text(r, 9).strip() == "# continue"


@pytest.fixture(scope="module")
def saved(twin):
    """One exchange, then the power switch: the cartridge RAM it left."""
    t = Talk(twin)
    assert not menu(t.rom)
    ui.press(t.rom, "start", after=60)
    t.type("my name is tom")
    sram = t.rom.sram()
    t.rom.close()
    return sram, t


def test_a_save_is_written(saved):
    sram, _ = saved
    assert sram[:4] == MAGIC
    body = sram[6:6 + SAVE_BODY]
    assert int.from_bytes(sram[4:6], "little") == (0x5A17 + sum(body)) & 0xFFFF
    assert body[0:2] == b"\x01\x00" and body[2:4] == b"\x01\x00", "one visit, one line"
    assert body[4] == 1, "wChatStarted"
    assert any(body[11:11 + 192]), "wH: the state she carries"
    assert not any(sram[6 + SAVE_BODY:]), "nothing past the image"


def test_continue_is_exact(saved, twin):
    """The contract of the save: power off after "my name is tom", power on,
    continue, ask - and the reply is the uninterrupted conversation's, to the
    character. The twin never stopped: its second turn runs on the state of
    its first, and the ROM's must have come back from the cartridge."""
    sram, before = saved
    t = Talk(twin, sram)
    t.st, t.said, t.lines = copy.deepcopy(before.st), list(before.said), list(before.lines)
    r = t.rom
    assert menu(r)
    assert ui.row_text(r, 12).split() == ["visits", "1"]
    assert ui.row_text(r, 13).split() == ["lines", "1"]
    ui.press(r, "a", after=60)                      # continue

    assert r.read("wChatStarted")[0] == 1
    assert ui.pane(r) == ui.layout(t.said[0]), "her last reply is back in the pane"
    want = t.send(*where("what is my name"))
    if measured():
        assert "tom" in want

    ui.press(r, "start", after=12)                  # and the log has all of it
    assert ui.log_screen(r)[:len(ui.log_rows(t.lines))] == ui.log_rows(t.lines)
    ui.press(r, "select", after=12)

    again = r.sram()
    r.close()
    r = ui.boot(again)                              # the counters went up
    assert menu(r)
    assert ui.row_text(r, 12).split() == ["visits", "2"]
    assert ui.row_text(r, 13).split() == ["lines", "2"]
    r.close()


def test_a_long_reply_scrolls(saved):
    """A reply longer than her pane. The model never says this much, so the text
    is planted in the save as her last reply (checksum put right) and comes
    back on continue the way any reply does: replayed through Rei_PanePut, the
    writer the teletype uses, which has to scroll to get to the end of it."""
    long = ("the quick brown fox jumps over the lazy dog and then she said "
            "supercalifragilistic words!")[:96]
    assert len(long) > 84
    assert not ui.layout(long)[0].startswith("the quick"), "this text should not fit"
    sram = bytearray(saved[0])
    body = 6
    slot = (sram[body + 8] - 1) & 7                 # wReiHistNext: the newest is the one before
    at = body + 11 + 192 + slot * 97
    sram[at] = len(long)
    sram[at + 1:at + 1 + len(long)] = long.encode("ascii")
    total = (0x5A17 + sum(sram[body:body + SAVE_BODY])) & 0xFFFF
    sram[4:6] = total.to_bytes(2, "little")
    r = ui.boot(bytes(sram))
    assert menu(r)
    ui.press(r, "a", after=60)
    assert ui.pane(r) == ui.layout(long)
    m = ui.tilemap(r)
    assert m[0][6] == ART["T_FR_TL"] and m[8][6] == ART["T_FR_BL"], "the frame survived the scroll"
    assert all(m[y][6] == ART["T_FR_L"] and m[y][19] == ART["T_FR_R"] for y in range(1, 8))
    r.close()


@pytest.mark.parametrize("where", [4, 6 + 11, 6 + SAVE_BODY - 1, 0])
def test_a_corrupt_save_is_ignored(saved, where):
    sram = bytearray(saved[0])
    sram[where] ^= 0x40                             # checksum, wH, the last byte, the magic
    r = ui.boot(bytes(sram))
    assert not menu(r)
    assert ui.row_text(r, 10).strip() == "PRESS START"
    ui.press(r, "start", after=60)
    assert r.read("wChatStarted")[0] == 0 and r.read("wReiHistCount")[0] == 0
    assert ui.pane(r) == [" " * 12] * 7
    r.close()


def test_new_friend_forgets(saved):
    r = ui.boot(saved[0])
    assert menu(r)
    ui.press(r, "down")
    assert ui.row_text(r, 10).strip() == "# new friend"
    ui.press(r, "a")
    assert ui.row_text(r, 9).strip() == "forget everything?"
    ui.press(r, "b")                                # no
    assert ui.row_text(r, 10).strip() == "# new friend"
    assert r.sram()[:4] == MAGIC
    ui.press(r, "a")
    ui.press(r, "a", after=60)                      # yes
    assert r.sram()[0] == 0, "the save is gone from the cartridge"
    assert r.read("wChatStarted")[0] == 0
    assert r.read("wReiHistCount")[0] == 0 and r.read("wReiLogCount")[0] == 0
    assert not any(r.read("wH", 192))
    assert ui.pane(r) == [" " * 12] * 7
    assert r.read("wReiVisits", 2) == b"\x01\x00" and r.read("wReiLines", 2) == b"\x00\x00"
    blank = r.sram()
    r.close()
    r = ui.boot(blank)
    assert not menu(r)
    r.close()
