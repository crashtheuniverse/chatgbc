"""The Rei screen shows exactly what the model said, where it should.

Drives build/rei.gbc (the app ROM with the game screen) through one
conversation and checks it against the integer twin turn by turn. The tests
share one booted ROM and one twin state and run in file order: each leaves the
conversation where the next picks it up.

Only meaningful for the chat export - `.\\build.ps1 -Rei` and the chat
environment (test.ps1 sets both up); skipped otherwise.
"""
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
KEYS_IN = {(x, y) for x in range(1, 19) for y in range(13, 17)}
MARKER = {(x, 8) for x in range(13, 18)}


def pool():
    text = (APP / "src" / "app" / "rei_input.asm").read_text(encoding="utf-8")
    return re.findall(r'^\.p\d: db "([^"]*)", 0', text, re.M)


class Talk:
    """The ROM and the twin, in the same conversation."""

    def __init__(self):
        self.rom = ui.boot()
        m = Model5(export5.CKPT)
        self.tok = Tokenizer()
        self.q = twin5.quantize5(m, twin5.calibrate5(m, self.tok, export5.cal_prompts()))
        self.st = twin5.QState5(self.q.cfg)
        self.said = []            # the twin's replies, newline stripped

    def twin(self, text):
        reply = golden5.chat_turn(self.q, self.tok, self.st, text, first=not self.said)
        self.said.append(reply.rstrip("\n"))
        return self.said[-1]

    def rom_reply(self):
        n = self.rom.read("wReiReplyLen")[0]
        return bytes(self.rom.read("wReiReply", n)).decode("ascii")


@pytest.fixture(scope="module")
def talk():
    t = Talk()
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
    assert ui.row_text(r, 11).strip() == "PRESS START"
    assert "v1.0.0" in ui.row_text(r, 15)
    assert r.read("wReady")[0] == 0
    r.pyboy.tick(120, False)
    assert ui.row_text(r, 11).strip() == "PRESS START", "the splash waits for START"
    ui.press(r, "start", after=30)
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
    assert ui.pane(r) == [" " * 12] * 7, "she has not spoken yet"
    assert ui.face_shown(r) in (0, 1)


def test_hello_lands_in_the_pane_only(talk):
    r = talk.rom
    want = talk.twin("hello")
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

    after = ui.tilemap(r)
    assert not changed(before, after) - PANE - FACE - MOOD - KEYS_IN - MARKER

    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    assert "rei" in want
    assert r.read("wReiMood")[0] == HAPPY          # "hello!"
    assert ui.face_shown(r) in (0, 1)
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hello", "the prompt row keeps what was sent"


def send_from_list(talk, page, row):
    r = talk.rom
    ui.press(r, "a")                                # leave the reply
    while r.read("wReiPage")[0]:                    # back to page 0, row 0
        ui.press(r, "left")
    while r.read("wReiPick")[0]:
        ui.press(r, "up")
    ui.pick(r, page, row)
    text = pool()[page * 3 + row]
    assert ui.row_text(r, 10, 1, 19).rstrip() == text
    want = talk.twin(text)
    ui.press(r, "start", after=0)
    ui.wait_ready(r)
    return want


def test_the_state_carries(talk):
    r = talk.rom
    want = send_from_list(talk, 0, 2)               # "my name is tom"
    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    want = send_from_list(talk, 1, 0)               # "what is my name"
    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    assert "tom" in want, "she forgot the name"


def test_history_pages(talk):
    r = talk.rom
    newest, before = talk.said[-1], talk.said[-2]
    assert ui.row_text(r, 8, 15, 18) == "3/8"
    ui.press(r, "up")
    assert ui.pane(r) == ui.layout(before)
    assert ui.row_text(r, 8, 15, 18) == "2/8"
    ui.press(r, "up")
    ui.press(r, "up")                               # there is nothing before the first
    assert ui.pane(r) == ui.layout(talk.said[0])
    assert ui.row_text(r, 8, 15, 18) == "1/8"
    ui.press(r, "down")
    ui.press(r, "down")
    assert ui.pane(r) == ui.layout(newest)
    assert ui.row_text(r, 8, 15, 18) == "3/8"


def test_select_opens_the_keyboard(talk):
    r = talk.rom
    ui.press(r, "b")                                # back to talking
    assert ui.pane(r) == ui.layout(talk.said[-1]), "the newest reply stays up"
    assert ui.row_text(r, 8, 13, 18) == "#" * 5, "the marker goes"
    ui.press(r, "select")
    assert r.read("wReiMode")[0] == 1
    assert ui.row_text(r, 13, 2, 19) == "a b c d e f g h i"
    ui.press(r, "start")
    assert r.read("wReady")[0] == 0 and r.read("wTypeOn")[0] == 0, "an empty message is not sent"
    ui.type_text(r, "hiz")
    ui.press(r, "b")                                # and B deletes
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hi_"
    want = talk.twin("hi")
    ui.press(r, "start", after=0)
    ui.wait_ready(r)
    assert talk.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hi"


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
    ui.press(r, "up")
    ui.press(r, "down")
    assert ui.pane(r) == ui.layout(long)
    m = ui.tilemap(r)
    assert m[0][6] == ART["T_FR_TL"] and m[8][6] == ART["T_FR_BL"], "the frame survived the scroll"
    assert all(m[y][6] == ART["T_FR_L"] and m[y][19] == ART["T_FR_R"] for y in range(1, 8))


def test_speed_is_on_record(talk):
    r = talk.rom
    n = r.read("wGenCount")[0]
    assert n and 300_000 < r.read_u32("wGenTotal") // n < 1_200_000
