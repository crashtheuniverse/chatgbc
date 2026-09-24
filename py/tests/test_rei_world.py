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
LCDC_WORLD = 0x08 | 0x20 | 0x40 | 0x02 | 0x04    # BG and window on $9C00, 8 x 16 objects
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
    assert lcdc & LCDC_WORLD == LCDC_WORLD, hex(lcdc)
    assert r.pyboy.memory[0xFF4A] == 96 and r.pyboy.memory[0xFF42] == 160   # WY, SCY
    assert window_map(r)[0][2] == harness.load_defs(APP / "src" / "rei_art.inc")["T_THINK"]
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


SCENES = ["beach", "garden", "playroom"]
_objects = {}


def scene_objects(i):
    if i not in _objects:
        _objects[i] = gen_rei_world.SCENES[i]().objects
    return _objects[i]


def art_rows(label, count=None):
    """The db rows under `label` in src/rei_world_art.inc, as one list."""
    text = (APP / "src" / "rei_world_art.inc").read_text(encoding="utf-8")
    body = text.split(f"\n{label}:")[1].split("\n\n")[0]
    out = []
    for line in body.splitlines()[1:]:
        if not line.strip().startswith("db"):
            break
        out += [int(v) for v in line.split("db")[1].split(";")[0].split(",")]
    return out[:count] if count else out


def strip_now(r, bank):
    at = 0x9C00 + DEFS["WORLD_MAP_Y"] * 32
    return [r.pyboy.memory[bank, at + i] for i in range(12 * 32)]


def test_each_visit_is_the_next_scene(talk):
    """Beach, garden, playroom, beach...: each visit loads its scene behind the
    chat, and the map and attributes on screen are the generator's, cell for cell."""
    r = talk.rom
    r.pyboy.memory[r.addr("wWorldTurn")] = 0
    for turn in range(4):
        before = chat_screen(r)
        ui.to_world(r)
        scene = r.read("wWorldScene")[0]
        assert scene == turn % 3
        name = SCENES[scene].capitalize()
        moving = set()                              # cells the handler may have flipped since
        anim = r.read("wWorldAnim", 12)
        for g in range(2):
            at = (anim[6 * g] | anim[6 * g + 1] << 8) - 0x9C00 - DEFS["WORLD_MAP_Y"] * 32
            mask = int.from_bytes(anim[6 * g + 2:6 * g + 6], "little")
            moving |= {at + x for x in range(32) if mask >> x & 1}
        drop = [0 if i in moving else 1 for i in range(384)]          # frame A or B there
        now = [v & ~1 if not d else v for v, d in zip(strip_now(r, 0), drop)]
        want = [v & ~1 if not d else v for v, d in zip(art_rows(f"ReiMap{name}", 384), drop)]
        assert now == want, SCENES[scene]
        assert strip_now(r, 1) == art_rows(f"ReiAttr{name}", 384), SCENES[scene]
        ui.press(r, "b", after=10)
        assert chat_screen(r) == before, "loading a scene touched the chat"


@pytest.mark.parametrize("scene", [0, 1, 2])
def test_she_walks_and_the_camera_follows(talk, scene):
    r = talk.rom
    r.pyboy.memory[r.addr("wWorldTurn")] = scene
    ui.to_world(r)
    assert r.read("wWorldScene")[0] == scene
    ui.set_word(r, "wWorldThinkT", 60000)           # no thought for now: just the walk
    seen = {"x": set(), "scx": set(), "tile": set(), "cells": set(), "act": set(), "sx": set()}
    anim = r.read("wWorldAnim", 12)
    moving = []                                     # the map cells the scene moves
    for g in range(2):
        at = anim[6 * g] | anim[6 * g + 1] << 8
        mask = int.from_bytes(anim[6 * g + 2:6 * g + 6], "little")
        moving += [at + x for x in range(32) if mask >> x & 1]
    assert moving, "every scene moves somewhere"
    start = [r.pyboy.memory[0, a] for a in moving]
    for _ in range(1500):
        r.pyboy.tick(1, False)
        x, tile = sprite(r)
        seen["sx"].add(x - 8)
        seen["tile"].add(tile & ~3)
        seen["x"].add(r.read("wWorldX")[0])
        seen["scx"].add(r.pyboy.memory[0xFF43])
        seen["cells"].add(tuple(r.pyboy.memory[0, a] ^ s for a, s in zip(moving, start)))
        seen["act"].add(r.read("wWorldAct")[0])
    assert len(seen["x"]) > 100 and len(seen["scx"]) > 60
    assert seen["tile"] == {12, 16, 20}, "two walking frames and the looking one"
    assert seen["act"] == {0, 1}, "she walks, and she stops to look"
    assert {v for c in seen["cells"] for v in c} == {0, 1}, "only frame A and frame B"
    assert len(seen["cells"]) >= 3, "both rows move, each in turn"
    assert min(seen["sx"]) >= DEFS["CAM_LEFT"] - 1 and max(seen["sx"]) <= DEFS["CAM_RIGHT"] + 1
    assert ui.thought_box(r) == [" " * 18] * 4
    if scene < 2:
        ui.press(r, "b", after=10)                  # the last stays for the thought


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

    centres = [x for _, x, _ in scene_objects(r.read("wWorldScene")[0])]
    ring = [min((x_at + 8 - c) % 256, (c - x_at - 8) % 256) for c in centres]
    assert ring[r.read("wWorldNear")[0]] <= min(ring) + 1, "the nearest thing is on record"

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
