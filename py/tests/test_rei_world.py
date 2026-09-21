"""The world: she walks while the model thinks, and the chat never knows.

One ROM, in file order. The thought timer, the idle timer and the walk's random
seed are WRAM the harness sets (wWorldThinkT, wReiIdle, wWorldRng), so nothing
here waits twenty seconds for anything and every run is the same run.

The contract is the last test: after two thoughts, one of them cut short, the
chat answers exactly as the twin does for a conversation with no world in it.
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

import gen_rei_world              # noqa: E402
import golden5                    # noqa: E402
import harness                    # noqa: E402
import rei_muse                   # noqa: E402
import rei_shots as ui            # noqa: E402
from rei_talk import Talk, twin   # noqa: E402,F401  (twin is a fixture)

DEFS = harness.load_defs(APP / "src" / "chatgbc.inc", APP / "src" / "hardware.inc",
                         APP / "src" / "app" / "rei.inc")
LCDC_WORLD = 0x80 | 0x08 | 0x20 | 0x40 | 0x02 | 0x04 | 0x01   # BG and window on $9C00, 8 x 16 objects, LCDC.4 clear
BOX = {(x, y) for x in range(1, 19) for y in range(1, 5)}


def muses():
    text = (APP / "src" / "app" / "rei_world.asm").read_text(encoding="utf-8")
    return re.findall(r'^\.m\d: db "([^"]*)", 0', text, re.M)


def chat_screen(r):
    return ui.tilemap(r), bytes(r.pyboy.memory[1, 0x9800:0x9800 + 18 * 32])


def window_map(r):
    return [list(r.pyboy.memory[0x9C00 + y * 32: 0x9C00 + y * 32 + 20]) for y in range(6)]


def model_state(r):
    return bytes(r.read("wH", 192)), r.read("wAbsPos")[0], r.read("wChatStarted")[0]


def sprite(r):
    y, x, tile, _ = r.pyboy.memory[0xFE00:0xFE04]
    return x, tile


def strip_cells(r, bank):
    """The scene's twelve rows of the second map: tiles (bank 0) or attributes."""
    at = 0x9C00 + DEFS["WORLD_MAP_Y"] * 32
    return [r.pyboy.memory[bank, at + i] for i in range(12 * 32)]


def art_table(label):
    text = (APP / "src" / "rei_world_art.inc").read_text(encoding="utf-8")
    body = text.split(f"{label}::")[1].split("\n\n")[0]
    return [int(v) for line in body.splitlines() if line.strip().startswith("db")
            for v in line.split("db")[1].split(",")]


@pytest.fixture(scope="module")
def talk(twin):
    t = Talk(twin)
    r = t.rom
    r.pyboy.tick(150, False)
    r.pyboy.memory[r.addr("wWorldRng")] = 40        # the walk, the same every run
    ui.press(r, "start", after=60)
    t.send(0, 0)                                    # "hello"
    yield t
    r.close()


def test_the_pool_is_the_one_the_twin_chose():
    assert muses() == rei_muse.POOL


def test_left_alone_she_goes_and_any_button_brings_the_chat_back(talk):
    r = talk.rom
    assert r.read("wReiMode")[0] == 1               # a topic's sentences, as "hello" left it
    ui.press(r, "down")
    before = chat_screen(r)
    ui.press(r, "select")
    ui.press(r, "select")
    assert not ui.world_on(r), "there is no button for the world"
    ui.to_world(r)                                  # nobody there: she wanders off
    lcdc = r.pyboy.memory[0xFF40]
    assert lcdc == LCDC_WORLD, hex(lcdc)
    assert r.pyboy.memory[0xFF4A] == 96 and r.pyboy.memory[0xFF42] == 160   # WY, SCY
    assert window_map(r) == [[0] * 20] * 6, "a plain panel: no frame, nothing on it"
    assert not any(r.pyboy.memory[1, 0x9C00 + y * 32 + x] for y in range(6) for x in range(20))
    assert strip_cells(r, 0) == art_table("ReiWorldMap")
    assert strip_cells(r, 1) == art_table("ReiWorldAttr")
    assert ui.thought_box(r) == [" " * 18] * 4, "the box is empty most of the time"

    for button in ("b", "a", "start", "select"):    # any button comes back
        if not ui.world_on(r):
            ui.to_world(r)
        r.pyboy.tick(30, False)
        ui.press(r, button, after=10)
        assert not ui.world_on(r), button
        assert r.pyboy.memory[0xFF40] == 0x91 and r.pyboy.memory[0xFF43] == 0
        assert chat_screen(r) == before, f"the chat is not as it was left ({button})"
        assert r.read("wReiMode")[0] == 1 and r.read("wReiPick")[0] == 1 and not ui.log_open(r)
    ui.press(r, "b")
    topics = chat_screen(r)                         # and from the topics
    ui.to_world(r)
    ui.press(r, "a", after=10)
    assert chat_screen(r) == topics and r.read("wReiMode")[0] == 0


def test_typed_text_survives_a_visit(talk):
    r = talk.rom
    ui.press(r, "select")
    ui.type_text(r, "hi")
    ui.to_world(r)
    ui.press(r, "b", after=10)
    assert r.read("wReiMode")[0] == 2, "the keyboard is still up"
    assert ui.row_text(r, 10, 1, 19).rstrip() == "hi_"
    ui.press(r, "b")
    ui.press(r, "b")
    assert ui.row_text(r, 10, 1, 19).rstrip() == "_"


def test_a_button_keeps_her_in(talk):
    r = talk.rom
    ui.set_word(r, "wReiIdle", DEFS["REI_WANDERS"] - 20)
    ui.press(r, "left", hold=30, after=0)           # somebody is there
    assert not ui.world_on(r)
    assert r.read("wReiIdle")[0] < 10


def objects(r):
    """Her sprite as OAM has it: [(y, x, tile, flags)] for the objects on screen."""
    oam = r.pyboy.memory[0xFE00:0xFE00 + 9 * 4]
    return [tuple(oam[i:i + 4]) for i in range(0, 36, 4) if oam[i]]


def test_she_walks_and_the_camera_follows(talk):
    r = talk.rom
    ui.to_world(r)
    ui.set_word(r, "wWorldThinkT", 60000)           # no thought for now: just the walk
    first = art_table("ReiWorldFrames")
    seen = {"x": set(), "scx": set(), "pose": set(), "act": set()}
    for _ in range(1500):
        r.pyboy.tick(1, False)
        objs = objects(r)
        pose, act = r.read("wWorldPose")[0], r.read("wWorldAct")[0]
        seen["x"].add(r.read("wWorldX")[0])
        seen["scx"].add(r.pyboy.memory[0xFF43])
        seen["pose"].add(pose >> 1)
        seen["act"].add(act)
        assert all(0 <= x - 8 <= 160 - 8 and 43 + 16 <= y <= 43 + 48 for y, x, _, _ in objs), objs
        tiles = {t for _, _, t, _ in objs}
        if len(objs) == 6:                          # her back to us: a back view's tiles, unmirrored
            assert min(tiles) in first[:4] and not any(f & 0x20 for *_, f in objs)
        else:
            assert len(objs) == 9 and min(tiles) in first[4:]
        assert all(f & 0x08 for *_, f in objs), "her tiles are in VRAM bank 1"
    assert len(seen["x"]) > 100 and len(seen["scx"]) > 40
    assert seen["act"] == {0, 1}, "she walks, and she stops to look"
    assert seen["pose"] == set(range(8)), "four back views, four steps"
    assert max(seen["scx"]) <= DEFS["CAM_MAX"]
    assert ui.thought_box(r) == [" " * 18] * 4


def walk(r, x, to_the_right, frames):
    """Put her at x, walking that way for a long stretch; run; where is she?"""
    scx = min(max(x - 68, 0), DEFS["CAM_MAX"])
    for name, v in (("wWorldX", x), ("wWorldScx", scx), ("wWorldDir", to_the_right),
                    ("wWorldAct", 0), ("wWorldTimer", 250)):
        r.pyboy.memory[r.addr(name)] = v
    r.pyboy.tick(frames, False)
    return r.read("wWorldX")[0], r.read("wWorldDir")[0], r.pyboy.memory[0xFF43]


def test_the_picture_has_ends(talk):
    r = talk.rom
    x, right, scx = walk(r, DEFS["WORLD_MIN_X"] + 6, 0, 60)
    assert right == 1 and DEFS["WORLD_MIN_X"] <= x < DEFS["WORLD_MIN_X"] + 30, "she turns at the left end"
    assert scx == 0, "and the camera stops there"
    assert min(o[1] for o in objects(r)) - 8 >= DEFS["WORLD_MIN_X"]
    x, right, scx = walk(r, DEFS["WORLD_MAX_X"] - 6, 1, 60)
    assert right == 0 and DEFS["WORLD_MAX_X"] - 30 < x <= DEFS["WORLD_MAX_X"], "and at the right end"
    assert scx == DEFS["CAM_MAX"]
    assert max(o[1] for o in objects(r)) - 8 + 8 <= 160 - 8
    flags = {o[3] & 0x20 for o in objects(r)}
    assert flags == {0}, "walking left is how she is drawn; right is the mirror"
    walk(r, 120, 1, 8)
    assert {o[3] & 0x20 for o in objects(r)} == {0x20}
    xs = [o[1] for o in objects(r)]
    assert max(xs) - min(xs) == 16 and len(set(xs)) == 3, "three columns, side by side"


def test_a_thought_is_the_models_and_leaves_no_trace(talk):
    r = talk.rom
    before = model_state(r)
    chat, sram = chat_screen(r), r.sram()
    counts = [r.read(n)[0] for n in ("wReiLogCount", "wReiHistCount", "wReiHistNext")]
    box = window_map(r)

    ui.think_now(r)
    x_at = r.read("wWorldX")[0]
    seen = {"stray": set(), "walk": set(), "pass": 0}

    def watch():
        now = window_map(r)
        seen["stray"].update((x, y) for y in range(6) for x in range(20)
                             if now[y][x] != box[y][x] and (x, y) not in BOX)
        if not r.read("wReiReplyLen")[0]:           # nothing said yet: the forward pass
            seen["pass"] += 1                       # is running on the hidden line
            seen["walk"].add((r.read("wWorldX")[0], sprite(r)))

    ui.thought_done(r, each_frame=watch)
    assert seen["pass"] > 100, "the prompt alone is seconds of forward pass"
    assert len(seen["walk"]) > seen["pass"] // 4, "she stood still while the model thought"
    assert not seen["stray"], f"the thought left its box: {sorted(seen['stray'])}"

    line = muses()[r.read("wWorldMuse")[0]]
    st = copy.deepcopy(talk.st)                     # the twin, from the same state
    want = golden5.chat_turn(talk.q, talk.tok, st, line, first=False).rstrip("\n")
    assert talk.rom_reply() == want
    rows = ui.wrap(want, ui.THINK_W)
    assert ui.thought_box(r) == rows + [" " * 18] * (4 - len(rows))

    far = [abs(x_at + 12 - x) for _, x, _ in gen_rei_world.OBJECTS]
    assert far[r.read("wWorldNear")[0]] <= min(far) + 1, "the nearest thing is on record"

    for _ in range(DEFS["THINK_STAYS"] + 60):       # it stays a while, then it goes
        r.pyboy.tick(1, False)
        if not r.read("wWorldThinking")[0]:
            break
    r.pyboy.tick(8, False)
    assert ui.thought_box(r) == [" " * 18] * 4
    assert model_state(r) == before, "the conversation is as it was before she thought"
    assert [r.read(n)[0] for n in ("wReiLogCount", "wReiHistCount", "wReiHistNext")] == counts
    assert r.sram() == sram, "a thought is not saved"
    assert chat_screen(r) == chat


def test_a_button_cuts_a_thought_short(talk):
    r = talk.rom
    before = model_state(r)
    assert ui.world_on(r)
    ui.think_now(r)
    for _ in range(40000):                          # a few letters in
        r.pyboy.tick(1, False)
        if r.read("wReiReplyLen")[0] >= 3:
            break
    assert model_state(r) != before, "the thought is running on the live state"
    r.pyboy.button_press("a")
    frames = 0
    while ui.world_on(r):
        r.pyboy.tick(1, False)
        frames += 1
        assert frames <= 40, "the chat did not come back in time"
    r.pyboy.button_release("a")
    r.pyboy.tick(10, False)
    assert model_state(r) == before
    assert not r.read("wWorldThinking")[0] and not r.read("wTypeOn")[0]
    assert r.pyboy.memory[0xFF40] == 0x91
    assert ui.pane(r) == ui.layout(talk.said[-1]), "her last reply is still in her pane"


def test_the_log_and_the_world_share_a_map(talk):
    """$9C00 is the log's screen and the world's. Each must come up whole after
    the other has been there."""
    r = talk.rom
    rows = ui.log_rows(talk.lines)
    ui.press(r, "start", after=12)
    assert ui.log_screen(r)[:len(rows)] == rows, "the log, after the world"
    ui.press(r, "select", after=12)
    ui.to_world(r)                                  # the world, after the log
    assert window_map(r) == [[0] * 20] * 6
    assert not any(r.pyboy.memory[1, 0x9C00 + y * 32 + x] for y in range(6) for x in range(20))
    assert strip_cells(r, 0) == art_table("ReiWorldMap")
    ui.press(r, "b", after=10)
    ui.press(r, "start", after=12)
    assert ui.log_screen(r)[:len(rows)] == rows
    ui.press(r, "select", after=12)


def test_the_chat_never_knew(talk):
    """Two thoughts later, one abandoned: the conversation goes on exactly as
    the twin's does - and the twin never went to the beach."""
    talk.send(1, 0)                                 # "my name is tom"
    want = talk.send(1, 2)                          # "what is my name"
    assert "tom" in want
    r = talk.rom
    ui.press(r, "start", after=12)                  # and the log has no thoughts in it
    rows = ui.log_rows(talk.lines)
    assert ui.log_screen(r)[:len(rows)] == rows
    assert ui.log_screen(r)[len(rows)] == (0, " " * 18)
    ui.press(r, "select", after=12)
