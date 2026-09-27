"""The name opcodes: she decides when, the engine keeps the name.

When the model chooses <SN> the engine stores the last word of the player's
line in the name slot and prints nothing; when it chooses <N> the engine
prints the slot (src/name.asm). The capture rule is golden5.capture_name, one
function for the twin and for these tests; golden5.chat_turn expands the
opcodes as the ROM does and keeps the slot in the twin's state.

A model says <SN> and <N> when it wants to, so the ROM has a hook the suite
plants her next picks in (wNameForce; chat_turn's `force` on the twin): the
model still runs every step, the forced tokens are hers in every other way,
and whatever she says after them is the model's own - checked against the
twin as ever.

This needs a chat export whose tokenizer carries the two pieces
(models/tok_rei1024.bin); the story build and a 512-piece Rei assemble none of
it, and skip. The capture rule's own test (test_name_rule.py) runs everywhere.
"""
import copy
import random

import numpy as np
import pytest

import export5                    # noqa: E402
import golden5                    # noqa: E402
import harness                    # noqa: E402
from conftest import APP, lab_rom
from test_name_rule import CASES

DEFS = harness.load_defs(APP / "src" / "chatgbc.inc", APP / "src" / "model.inc")
if not (export5.CHAT and "NAME_OPS" in DEFS):
    pytest.skip("the name opcodes need a chat export whose tokenizer has <SN> and <N>",
                allow_module_level=True)

import quant as Q                 # noqa: E402
import rei_shots as ui            # noqa: E402
import twin5                      # noqa: E402
from model5 import Tokenizer      # noqa: E402
from rei_talk import NAME, Talk, force, slot, twin   # noqa: E402,F401  (twin is a fixture)

SN, N = DEFS["TOK_SN"], DEFS["TOK_N"]
NAME_MAX = DEFS["NAME_MAX"]
KEYBOARD = "abcdefghijklmnopqrstuvwxyz .,!?'-;:"         # rei_input.asm's keys


def test_the_opcodes_are_the_tokenizers():
    """The exporter took the ids from the tokenizer's pieces, the detokenizer
    holds nothing to print for them, and no line the cartridge can encode
    reaches them."""
    tok = Tokenizer()
    assert export5.name_ops(tok) == (SN, N)
    assert (tok.vocab[SN], tok.vocab[N]) == (b"<SN>", b"<N>")
    blob = (APP / "build" / "blobs" / "vocab_data.bin").read_bytes()
    for t in (SN, N):
        at = int.from_bytes(blob[2 * t:2 * t + 2], "little")
        assert blob[at] == 0, "an opcode's piece is empty in the ROM"
    rng = random.Random(7)
    lines = ["".join(rng.choice(KEYBOARD) for _ in range(rng.randint(1, 44)))
             for _ in range(3000)]
    import rei_topics
    lines += [s for _, ls in rei_topics.TOPICS for s in ls] + rei_topics.WARMUP
    for line in lines:
        for ids in (tok.encode("> " + line + "\n"),
                    tok.encode("\n> " + line + "\n", bos=False, prefix=False)):
            assert SN not in ids and N not in ids, line


# --- the lab ROM -------------------------------------------------------------

@pytest.fixture(scope="module")
def lab():
    r = lab_rom()
    yield r
    r.close()


def lab_capture(r, text, before):
    """<SN>'s capture alone (LAB_GO_NAME) on `text` in wPromptText, the slot
    holding `before`. Returns the slot after."""
    raw = text.encode("latin-1")
    assert len(raw) <= r.defs["PROMPT_MAX"]
    idle, state, go = r.defs["LAB_IDLE"], r.addr("wLabState"), r.addr("wLabGo")
    r.pyboy.memory[go] = 0
    r._tick_until(lambda: r.pyboy.memory[state] == idle, 2000, "lab idle")
    at = r.addr("wName")
    r.pyboy.memory[at:at + NAME_MAX] = list(before)
    base = r.addr("wPromptText")
    if raw:
        r.pyboy.memory[base:base + len(raw)] = list(raw)
    r.pyboy.memory[r.addr("wPromptLen")] = len(raw)
    ready = r.addr("wReady")
    r.pyboy.memory[ready] = 0
    r.pyboy.memory[go] = DEFS["LAB_GO_NAME"]
    r._tick_until(lambda: r.pyboy.memory[ready] == r.defs["READY_MAGIC"], 2000, "capture")
    r.pyboy.memory[go] = 0
    return r.read("wName", NAME_MAX)


def test_the_rom_captures_by_the_rule(lab):
    """The cases above, raw and staged as Chat_Stage stages them, then random
    lines of every byte the rule has an edge at (A-Z and a-z against @ [ ` {),
    against a slot that already holds something."""
    before = bytes(range(1, NAME_MAX + 1))          # no letter: a clear would show
    rng = random.Random(3)
    alphabet = KEYBOARD + "ABCXYZ@[`{0123456789\n>"
    lines = [line for line, _ in CASES]
    lines += ["\n> " + line + "\n" for line, _ in CASES]
    lines += ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 48)))
              for _ in range(300)]
    for text in lines:
        name = golden5.capture_name(text)
        want = before if name is None else slot(name)
        assert lab_capture(lab, text, before) == want, repr(text)


def console_rows(text):
    """The lab console's rows for `text` (Console_PutChar: 20 columns, a full
    row wraps at once, a newline starts the next)."""
    rows = [""]
    for ch in text:
        if ch == "\n":
            rows.append("")
            continue
        rows[-1] += ch
        if len(rows[-1]) == DEFS["CON_VIS_W"]:
            rows.append("")
    return [row.rstrip() for row in rows]


@pytest.mark.parametrize("line,forced,name", [
    ("my name is vince", ("SN", "N"), "vince"),
    ("Vince!", ("N", "SN", "N", "N"), "vince"),     # <N> before any <SN>: nothing
    ("?!", ("SN", "N"), ""),                        # no letter: nothing stored
    ("call me mary ann", ("SN", "N", "SN", "N", "SN", "N"), "ann"),
    ("my name is bartholomewxyz", ("SN", "N"), "bartholomewx"),
])
def test_forced_opcodes_on_the_lab(lab, twin, line, forced, name):
    """A fresh turn with her first picks forced: her tokens, what the console
    printed and the slot are the twin's. The repeated <SN> <N> of the fourth
    are her history like any tokens: the no-repeat rule then works on them."""
    q, tok = twin
    ids = [{"SN": SN, "N": N}[f] for f in forced]
    st, mine = twin5.QState5(q.cfg), []
    said = golden5.chat_turn(q, tok, st, line, first=True, force=ids, record=mine)
    assert st.name == name

    prompt = "> " + line + "\n"
    force(lab, ids)
    lab.lab_run(steps=golden5.STEPS, prompt=prompt)
    n = lab.read("wGenCount")[0]
    out = lab.read("wOutTokens", 2 * n)
    toks = [out[2 * i] | (out[2 * i + 1] << 8) for i in range(n)]
    pids = tok.encode(prompt)
    k = len(pids) - 1
    assert toks[:k] == pids[1:], "the prompt is forced as encoded"
    assert toks[k:] == mine, "her tokens are the twin's"
    assert toks[k:k + len(ids)] == ids
    assert lab.read("wNameForceN")[0] == 0, "the hook is used up"
    assert lab.read("wName", NAME_MAX) == slot(name)

    shown, prev = "", pids[0]
    for t in pids[1:]:
        shown += tok.decode(t, prev)
        prev = t
    rows = console_rows(shown + said)
    assert len(rows) < 18, "no scroll: the rows compare one to one"
    assert lab.console_lines()[:len(rows)] == rows
    assert "<" not in said and (name in said or not name)


def test_the_no_repeat_rule_sees_the_opcodes(lab, twin):
    """Planted histories through the classifier and its retry (LAB_GO_PICK):
    4-grams made of the opcodes block like any others, and an opcode the
    model would pick again is refused like any token."""
    q, _ = twin
    w = q.weights["tok_emb"]
    rng = np.random.default_rng(4)

    def pick(xb, history):
        idle, state, go = lab.defs["LAB_IDLE"], lab.addr("wLabState"), lab.addr("wLabGo")
        lab.pyboy.memory[go] = 0
        lab._tick_until(lambda: lab.pyboy.memory[state] == idle, 2000, "lab idle")
        base = lab.addr("wXb")
        lab.pyboy.memory[base:base + len(xb)] = [int(v) & 0xFF for v in xb]
        raw = [b for t in history for b in (t & 0xFF, t >> 8)]
        out = lab.addr("wOutTokens")
        if raw:
            lab.pyboy.memory[out:out + len(raw)] = raw
        lab.pyboy.memory[lab.addr("wGenCount")] = len(history)
        ready = lab.addr("wReady")
        lab.pyboy.memory[ready] = 0
        lab.pyboy.memory[go] = lab.defs["LAB_GO_PICK"]
        lab._tick_until(lambda: lab.pyboy.memory[ready] == lab.defs["READY_MAGIC"], 4000, "pick")
        lab.pyboy.memory[go] = 0
        a = lab.read("wBestTok", 2)
        return a[0] | (a[1] << 8)

    # an opcode as the model's own first choice: xb along its row
    for op in (N, SN):
        xb = (w[op].astype(np.int64) * 127)
        order = np.argsort(-Q.matvec_blocks(w, xb, 4, 0), kind="stable")
        if int(order[0]) == op:
            break
    assert int(order[0]) == op, "no vector made an opcode the argmax"
    logits = Q.matvec_blocks(w, xb, 4, 0)
    for hist in ([], [SN, N, SN, op, SN, N, SN], [7, 8, 9, op, 7, 8, 9]):
        want = Q.pick_token(logits, hist)
        assert pick(xb, hist) == want
    assert Q.pick_token(logits, [7, 8, 9, op, 7, 8, 9]) != op, "a repeat is refused"

    # opcodes in the 4-grams that block ordinary candidates
    done = 0
    while done < 3:
        xb = rng.integers(-128, 128, 64)
        logits = Q.matvec_blocks(w, xb, 4, 0)
        order = np.argsort(-logits, kind="stable")
        if {SN, N} & {int(t) for t in order[:8]}:
            continue                                # the opcodes are the filler here
        done += 1
        filler = [SN, N, SN]
        for k in range(4):
            hist = []
            for c in order[:k]:
                hist += filler + [int(c)]
            hist += filler
            assert pick(xb, hist) == Q.pick_token(logits, hist) == int(order[k])


# --- the cartridge -----------------------------------------------------------

@pytest.fixture(scope="module")
def talk(twin):
    if not (APP / "build" / "rei.gbc").exists():
        pytest.skip("build/rei.gbc missing - run .\\build.ps1 -Rei")
    t = Talk(twin)
    t.rom.pyboy.tick(150, False)
    ui.press(t.rom, "start", after=60)
    yield t
    t.rom.close()


def name_in_rom(r):
    return r.read("wName", NAME_MAX)


def type_and_send(t, text, forced):
    """The keyboard: `text` typed and sent with OK, her first picks forced."""
    r = t.rom
    if r.read("wReiMode")[0] != 2:
        ui.press(r, "select")
    cell = ui.type_text(r, text, r.read("wReiKey")[0])     # from where the cursor was left
    want = t.expect(text, forced)
    force(r, forced)
    ui.type_text(r, ui.OK, cell)
    ui.wait_ready(r)
    assert t.rom_reply() == want
    assert ui.pane(r) == ui.layout(want)
    ui.press(r, "select")                           # back to the list
    return want


def test_she_stores_the_name_and_says_it(talk):
    r = talk.rom
    want = talk.send(1, 0, forced=(SN, N))          # "my name is tom"
    assert want.startswith("tom") and talk.st.name == "tom"
    assert name_in_rom(r) == slot("tom")
    assert r.read("wReiMood")[0] == ui.mood_of(want)


def test_she_says_it_a_turn_later(talk):
    want = talk.send(1, 2, forced=(N,))             # "what is my name"
    assert want.startswith("tom")
    assert name_in_rom(talk.rom) == slot("tom")


def test_a_line_without_letters_leaves_it(talk):
    want = type_and_send(talk, "?!", (SN, N))
    assert want.startswith("tom") and talk.st.name == "tom"
    assert name_in_rom(talk.rom) == slot("tom")


def test_the_log_has_the_name(talk):
    r = talk.rom
    rows = ui.log_rows(talk.lines)
    ui.press(r, "start", after=12)
    assert ui.log_open(r)
    if len(rows) >= ui.LOG_H:
        assert ui.log_screen(r) == rows[-ui.LOG_H:]
    else:
        assert ui.log_screen(r)[:len(rows)] == rows
    assert any("tom" in text for who, text in rows if not who)
    ui.press(r, "select", after=12)
    assert not ui.log_open(r)


def test_a_thought_puts_the_name_back(talk):
    """In the world a thought runs on the conversation and is then undone
    (src/app/rei_world.asm): a name it stores is undone with it."""
    import re
    r = talk.rom
    ui.to_world(r)
    ui.set_word(r, "wWorldThinkT", 60000)
    force(r, (SN, N))
    ui.think_now(r)
    ui.thought_done(r)
    text = (APP / "src" / "app" / "rei_world.asm").read_text(encoding="utf-8")
    line = re.findall(r'^\.m\d: db "([^"]*)", 0', text, re.M)[r.read("wWorldMuse")[0]]
    st = copy.deepcopy(talk.st)
    want = golden5.chat_turn(talk.q, talk.tok, st, line, first=False,
                             force=(SN, N)).rstrip("\n")
    assert talk.rom_reply() == want
    assert want.startswith(golden5.capture_name(line))
    assert name_in_rom(r) == slot(st.name), "the thought's own name, while it is up"
    for _ in range(6 * 60 + 60):                # THINK_STAYS and then some
        r.pyboy.tick(1, False)
        if not r.read("wWorldThinking")[0]:
            break
    r.pyboy.tick(8, False)
    assert name_in_rom(r) == slot("tom"), "and the chat's afterwards"
    ui.press(r, "b", after=10)
    assert not ui.world_on(r)


def test_the_mood_sees_the_name(talk):
    """<N> goes through the teletype like any piece: a name that is a sad
    word makes a sad reply."""
    want = type_and_send(talk, "i am sad", (SN, N))
    assert want.startswith("sad") and talk.st.name == "sad"
    assert talk.rom.read("wReiMood")[0] == ui.mood_of(want) == ui.MOOD_SAD


# --- the battery save --------------------------------------------------------

BODY_V1 = 11 + 192 + 8 * 97 + 64 * 19            # src/app/rei_save.asm
BODY = BODY_V1 + NAME_MAX


def checksum(body):
    return ((0x5A17 + sum(body)) & 0xFFFF).to_bytes(2, "little")


@pytest.fixture(scope="module")
def saved(talk):
    """The cartridge RAM the conversation above left, and its twin."""
    return talk.rom.sram(), talk


def test_the_name_is_saved(saved):
    sram, _ = saved
    assert sram[:4] == b"REI\x02"
    assert sram[4:6] == checksum(sram[6:6 + BODY])
    assert sram[6 + BODY_V1:6 + BODY] == slot("sad")
    assert not any(sram[6 + BODY:])


def resume(twin, before, sram):
    t = Talk(twin, sram)
    t.st, t.said, t.lines = copy.deepcopy(before.st), list(before.said), list(before.lines)
    t.rom.pyboy.tick(150, False)
    assert ui.row_text(t.rom, 9).strip() == "# continue"
    ui.press(t.rom, "a", after=60)                  # continue
    return t


def test_continue_keeps_the_name(saved, twin):
    sram, before = saved
    t = resume(twin, before, sram)
    try:
        assert name_in_rom(t.rom) == slot("sad")
        want = t.send(1, 2, forced=(N,))            # "what is my name"
        assert want.startswith("sad")
    finally:
        t.rom.close()


def test_an_old_save_continues_with_no_name(saved, twin):
    """A version 1 save - the same body without the slot - still loads, and
    the conversation goes on with an empty slot; the next save is version 2."""
    sram, before = saved
    old = bytearray(sram)
    old[3] = 1
    old[6 + BODY_V1:6 + BODY] = bytes(NAME_MAX)
    old[4:6] = checksum(old[6:6 + BODY_V1])
    t = resume(twin, before, bytes(old))
    try:
        r = t.rom
        assert name_in_rom(r) == bytes(NAME_MAX)
        assert r.read("wChatStarted")[0] == 1
        assert ui.pane(r) == ui.layout(t.said[-1]), "her last reply is back"
        t.st.name = ""
        t.send(1, 2, forced=(N,))                   # <N> with nothing in the slot
        again = r.sram()
        assert again[:4] == b"REI\x02" and again[4:6] == checksum(again[6:6 + BODY])
        assert again[6 + BODY_V1:6 + BODY] == bytes(NAME_MAX)
    finally:
        t.rom.close()


def test_new_friend_forgets_the_name(saved):
    r = ui.boot(saved[0])
    try:
        r.pyboy.tick(150, False)
        ui.press(r, "down")
        ui.press(r, "a")
        ui.press(r, "a", after=60)                  # "forget everything?" yes
        assert r.read("wChatStarted")[0] == 0
        assert name_in_rom(r) == bytes(NAME_MAX)
    finally:
        r.close()
