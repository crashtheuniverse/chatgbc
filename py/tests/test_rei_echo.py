"""Rei can say the player's words back.

The no-repeat rule refuses a token that completes a 4-gram already on record.
In a chat build the record it searches is her own words of the turn only
(wOwnFrom, src/generate.asm; golden5.history / chat_turn on the twin): when it
held the player's forced line too, every echo was a repeat and she was pushed
off the word mid-word - "i do like duucks", "it is sainy", "druts", "hors".
The first lines below are the ones that did it; the rest are Rei v1's echo
lines in the topic tree, where the echo is mostly <W> (the engine prints the
player's last word, src/name.asm) and the rule must still let her spell it
again after that. Fresh on the chat lab ROM, and mid-chat on build/rei.gbc
through the topic tree, each against the twin; that the word is there at all
is checked on the checkpoint it was measured on (rei_talk.MEASURED).

Only meaningful for the chat export; skipped otherwise.
"""
import re

import pytest
from types import SimpleNamespace

import export5                    # noqa: E402
from conftest import APP, lab_rom

if not export5.CHAT:
    pytest.skip("the echo test needs the chat export", allow_module_level=True)

import golden5                    # noqa: E402
import rei_shots as ui            # noqa: E402
import rei_topics                 # noqa: E402
import twin5                      # noqa: E402
from rei_talk import Talk, measured, twin   # noqa: E402,F401  (twin is a fixture)

# (the player's line, the word her reply must hold)
LINES = [
    ("do you like ducks", "ducks"),       # each of these four was garbled before
    ("do you like books", "books"),
    ("it is sunny today", "sunny"),
    ("do you like horses", "horses"),
    ("i like drums", "drums"),            # v1's tree
    ("i love bunnies", "bunnies"),
    ("what about zebras", "zebras"),
    ("i like owls", "owls"),
]


def words(text):
    return re.findall(r"[a-z]+", text)


@pytest.fixture(scope="module")
def lab():
    r = lab_rom()
    yield r
    r.close()


def lab_reply(r, tok, prompt):
    """One fresh turn on the lab ROM: her tokens after the forced prompt, as
    text, the stop token's piece included (what chat_turn returns)."""
    r.lab_run(steps=golden5.STEPS, prompt=prompt)
    ids = tok.encode(prompt)
    n = r.read("wGenCount")[0]
    out = r.read("wOutTokens", 2 * n)
    toks = [out[2 * i] | (out[2 * i + 1] << 8) for i in range(n)]
    forced = len(ids) - 1
    assert toks[:forced] == ids[1:], "the prompt is forced as encoded"
    assert r.read("wOwnFrom")[0] == forced, "her history starts after the player's line"
    said, prev = "", toks[forced - 1]
    st = SimpleNamespace(name=None)   # a fresh turn: no name in the slot
    line = prompt[2:].rstrip("\n")   # the player's line, as the engine captures it
    for t in toks[forced:]:
        said += golden5.speak(tok, st, t, prev, line)   # what the cartridge prints, opcodes too
        prev = t
    return said


@pytest.mark.parametrize("line,word", LINES)
def test_a_fresh_turn_says_the_word(lab, twin, line, word):
    q, tok = twin
    want = golden5.chat_turn(q, tok, twin5.QState5(q.cfg), line, first=True)
    assert lab_reply(lab, tok, "> " + line + "\n") == want
    assert want.endswith("\n")
    if measured():                  # the words are v1's (rei_talk.MEASURED)
        assert word in words(want), want


def test_mid_conversation_on_the_cartridge(twin):
    """The topic check's warm-up, then every echo line the topic tree holds,
    in one conversation on build/rei.gbc; Talk.send checks each reply against
    the twin's, pane included."""
    if not (APP / "build" / "rei.gbc").exists():
        pytest.skip("build/rei.gbc missing - run .\\build.ps1 -Rei")
    where = {s: (t, i) for t, (_, lines) in enumerate(rei_topics.TOPICS)
             for i, s in enumerate(lines)}
    echo = [(s, w) for s, w in LINES if s in where]
    assert len(echo) >= 5, "the topic tree holds the echo lines again"
    t = Talk(twin)
    try:
        t.rom.pyboy.tick(150, False)
        ui.press(t.rom, "start", after=60)
        for s in rei_topics.WARMUP:             # the name is typed: no tree line gives one
            if s in where:
                t.send(*where[s])
            else:
                t.type(s)
        for s, word in echo:
            reply = t.send(*where[s])
            if measured():
                assert word in words(reply), (s, reply)
    finally:
        t.rom.close()
