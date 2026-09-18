"""The Rei screen shows exactly what the model said, where it should - and the
cartridge remembers it.

Drives build/rei.gbc (the app ROM with the game screen) through a conversation
and checks it against the integer twin turn by turn. The first group of tests
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
SAVE_BODY = 11 + 192 + 8 * 97 + 64 * 19        # src/app/rei_save.asm: 2,195 bytes


def pool():
    text = (APP / "src" / "app" / "rei_input.asm").read_text(encoding="utf-8")
    return re.findall(r'^\.p\d: db "([^"]*)", 0', text, re.M)


@pytest.fixture(scope="module")
def twin():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    return twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts())), tok


class Talk:
    """A ROM and the twin, in the same conversation."""

    def __init__(self, twin, sram=None):
        self.rom = ui.boot(sram)
        self.q, self.tok = twin
        self.st = twin5.QState5(self.q.cfg)
        self.said = []            # the twin's replies, newline stripped
        self.lines = []           # the whole conversation, for the log: (who, text)

    def expect(self, text):
        """The twin's reply to `text`, which the ROM is about to be sent."""
        reply = golden5.chat_turn(self.q, self.tok, self.st, text, first=not self.said)
        self.said.append(reply.rstrip("\n"))
        self.lines += [(1, text), (0, self.said[-1])]
        return self.said[-1]

    def rom_reply(self):
        n = self.rom.read("wReiReplyLen")[0]
        return bytes(self.rom.read("wReiReply", n)).decode("ascii")

    def send_from_list(self, page, row):
        r = self.rom
        assert r.read("wReiMode")[0] == 0
        ui.press_until(r, "left", lambda: r.read("wReiPage")[0] == 0)   # page 0, row 0
        ui.press_until(r, "up", lambda: r.read("wReiPick")[0] == 0)
        ui.pick(r, page, row)
        text = pool()[page * 3 + row]
        assert ui.row_text(r, 10, 1, 19).rstrip() == text
        want = self.expect(text)
        ui.press(r, "a", after=0)
        ui.wait_ready(r)
        assert self.rom_reply() == want
        assert ui.pane(r) == ui.layout(want)
        return want


@pytest.fixture(scope="module")
def talk(twin):
    t = Talk(twin)
    yield t
    t.rom.close()


def changed(before, after):
    return {(x, y) for y in range(18) for x in range(20) if before[y][x] != after[y][x]}


def test_pool_is_in_vocabulary():
    tok = Tokenizer()
    prompts = pool()
    assert len(prompts) == 9
    for p in prompts:
        assert p == p.lower() and len(p) <= 17
        assert 0 not in tok.encode("> " + p + "\n"), f"{p!r} has an unknown piece"


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
    assert m[0][0] == ART["T_FR_TL"] and m[17][19] == ART["T_FR_BR"]
    assert ui.row_text(r, 0, 8, 11) == "REI"


def test_first_screen_is_the_list(talk):
    r = talk.rom
    assert r.read("wReiMode")[0] == 0
    prompts = pool()
    for i in range(3):
        assert ui.row_text(r, 13 + i, 2, 19).rstrip() == prompts[i]
    assert ui.row_text(r, 10, 1, 19).rstrip() == prompts[0], "the prompt row shows what will be sent"
    assert "START:log" in ui.row_text(r, 17) and "SEL:keys" in ui.row_text(r, 12)
    assert ui.pane(r) == [" " * 12] * 7, "she has not spoken yet"
    assert ui.face_shown(r) in (0, 1)


def test_hello_lands_in_the_pane_only(talk):
    r = talk.rom
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

    # No after-reply screen: the list is back as it was, her reply stays up.
    after = ui.tilemap(r)
    assert not changed(before, after) - PANE - FACE - MOOD - MARKER
    assert ui.row_text(r, 13, 2, 19).rstrip() == "hello"
    assert r.pyboy.memory[1, 0x9800 + 13 * 32 + 5] == ART["PAL_PICK"], "the cursor is back"
    assert ui.row_text(r, 8, 15, 18) == "1/8"

    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    assert "rei" in want
    assert r.read("wReiMood")[0] == HAPPY          # "hello!"
    assert ui.face_shown(r) in (0, 1)
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hello", "the prompt row shows what A would send"


def test_the_state_carries(talk):
    talk.send_from_list(0, 2)                       # "my name is tom"
    want = talk.send_from_list(1, 0)                # "what is my name"
    assert "tom" in want, "she forgot the name"


def test_edge_paging_from_the_list(talk):
    r = talk.rom
    newest, before = talk.said[-1], talk.said[-2]
    assert ui.row_text(r, 8, 15, 18) == "3/8"
    assert r.read("wReiPick")[0] == 0
    ui.press(r, "up")                               # off the top of the list
    assert ui.pane(r) == ui.layout(before)
    assert ui.row_text(r, 8, 15, 18) == "2/8"
    assert r.read("wReiPick")[0] == 0, "the cursor stays"
    ui.press(r, "up")
    ui.press(r, "up")                               # there is nothing before the first
    assert ui.pane(r) == ui.layout(talk.said[0])
    assert ui.row_text(r, 8, 15, 18) == "1/8"
    ui.press(r, "down")                             # inside the list DOWN only moves
    assert r.read("wReiPick")[0] == 1 and ui.row_text(r, 8, 15, 18) == "1/8"
    ui.press(r, "down")
    ui.press(r, "down")                             # off the bottom
    assert ui.row_text(r, 8, 15, 18) == "2/8"
    ui.newer(r)
    ui.newer(r)                                     # and nothing after the newest
    assert ui.pane(r) == ui.layout(newest)
    assert ui.row_text(r, 8, 15, 18) == "3/8"


def test_sending_snaps_to_the_newest(talk):
    r = talk.rom
    ui.older(r)
    ui.older(r)
    assert ui.row_text(r, 8, 15, 18) == "1/8"
    talk.send_from_list(1, 1)                       # "i like chess"
    assert ui.row_text(r, 8, 15, 18) == "4/8"


def test_keyboard_ok_sends_and_edges_page(talk):
    r = talk.rom
    ui.press(r, "select")
    assert r.read("wReiMode")[0] == 1
    assert ui.row_text(r, 13, 2, 19) == "a b c d e f g h i"
    assert ui.tilemap(r)[16][18] == ART["T_OK"]
    assert "SEL:list" in ui.row_text(r, 12)

    ui.press(r, "up")                               # off the top row of keys
    assert ui.pane(r) == ui.layout(talk.said[-2]) and ui.row_text(r, 8, 15, 18) == "3/8"
    assert r.read("wReiKey")[0] == 0
    for _ in range(3):
        ui.press(r, "down")
    assert r.read("wReiKey")[0] == 27 and ui.row_text(r, 8, 15, 18) == "3/8"
    ui.press(r, "down")                             # off the bottom row
    assert ui.pane(r) == ui.layout(talk.said[-1]) and ui.row_text(r, 8, 15, 18) == "4/8"

    cell = ui.type_text(r, ui.OK, 27)
    assert r.read("wReady")[0] and not r.read("wTypeOn")[0], "an empty message is not sent"
    cell = ui.type_text(r, "hiz", cell)
    ui.press(r, "b")                                # B deletes
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hi_"

    ui.press(r, "start", after=12)                  # START is the log now, not send
    assert ui.log_open(r) and r.read("wReady")[0] and not r.read("wTypeOn")[0]
    ui.press(r, "select", after=12)
    assert not ui.log_open(r)
    assert r.read("wReiMode")[0] == 1, "leaving the log is not a mode switch"
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hi_"

    want = talk.expect("hi")
    ui.type_text(r, ui.OK, cell)
    assert not r.read("wReady")[0]
    ui.wait_ready(r)
    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    assert ui.row_text(r, 13, 2, 19) == "a b c d e f g h i", "the keyboard is back"
    assert ui.row_text(r, 10, 1, 19).rstrip() == "_"
    ui.press(r, "select")                           # back to the list for the rest


def test_the_log_shows_both_sides(talk):
    r = talk.rom
    talk.send_from_list(1, 2)                       # "what do i like": enough rows to scroll
    rows = ui.log_rows(talk.lines)
    assert len(rows) > ui.LOG_H
    main = ui.tilemap(r)
    attrs = bytes(r.pyboy.memory[1, 0x9800:0x9800 + 18 * 32])

    ui.press(r, "start", after=12)
    assert ui.log_open(r)
    assert ui.row_text(r, 0, 8, 11) == "REI", "the main screen's map is not the one showing"
    assert ui.log_screen(r) == rows[-ui.LOG_H:], "newest at the bottom"
    assert rows[0] == (1, "> hello".ljust(18))
    top = r.pyboy.memory[ui.LOG_MAP + 17], r.pyboy.memory[ui.LOG_MAP + 17 * 32 + 17]
    assert top == (ART["T_ARROW_UP"], ART["T_FR_B"]), "more above, nothing below"

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
    assert r.read("wReiMode")[0] == 0


def test_long_reply_scrolls(talk):
    """A reply longer than the pane. The model never says this much, so the
    text is planted in the newest history slot and shown the way any old reply
    is: replayed through Rei_PanePut, the writer the teletype uses."""
    r = talk.rom
    long = ("the quick brown fox jumps over the lazy dog and then she said "
            "supercalifragilistic words!")
    long = long[:96]
    assert len(long) > 84
    assert not ui.layout(long)[0].startswith("the quick"), "this text should not fit"
    slot = (r.read("wReiHistNext")[0] - 1) & 7
    base = r.addr("wReiHist") + slot * 97
    r.pyboy.memory[2, base] = len(long)
    for i, ch in enumerate(long.encode("ascii")):
        r.pyboy.memory[2, base + 1 + i] = ch
    ui.older(r)
    ui.newer(r)
    assert ui.pane(r) == ui.layout(long)
    m = ui.tilemap(r)
    assert m[0][6] == ART["T_FR_TL"] and m[8][6] == ART["T_FR_BL"], "the frame survived the scroll"
    assert all(m[y][6] == ART["T_FR_L"] and m[y][19] == ART["T_FR_R"] for y in range(1, 8))


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
    t.send_from_list(0, 2)                          # "my name is tom"
    sram = t.rom.sram()
    t.rom.close()
    return sram, t


def test_a_save_is_written(saved):
    sram, _ = saved
    assert sram[:4] == b"REI\x01"
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
    assert ui.row_text(r, 8, 15, 18) == "1/8"
    want = t.send_from_list(1, 0)                   # "what is my name"
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
    assert r.sram()[:4] == b"REI\x01"
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
