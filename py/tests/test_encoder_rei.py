"""The chat ROM's encoder gives the Python tokenizer's tokens, every time.

The lab ROM has an encode-only entry (LAB_GO_ENC, LAB_GO_ENCC): the harness
writes a staged line into wPromptText and reads wTokBuf back. Every sentence in
the topic tree is checked in both of the forms the ROM sends - the first turn
("> line\\n" behind BOS and the dummy prefix, Encode) and a later one
("\\n> line\\n", EncodeCont) - and so is a sample of typed lines: some written to
reach the long pieces the old encoder could not ("favourite", "cartridge."), and,
when her corpus is on this machine (REI_CORPUS, or chatgbc_x's build/friend3.txt),
a few hundred of the player's lines from it.

Only for the chat export (the story ROM's encoder is left as it was: see the
header of src/encoder.asm).
"""
import os
import random
from pathlib import Path

import pytest

import export5                    # noqa: E402
from conftest import APP, lab_rom, lab_encode as rom_encode

if not export5.CHAT:
    pytest.skip("the chat encoder is the chat export's", allow_module_level=True)

import rei_topics                 # noqa: E402
from model5 import Tokenizer      # noqa: E402

KEYBOARD = set("abcdefghijklmnopqrstuvwxyz .,!?'-;:\"")
TYPED = [
    "my favourite colour is blue", "i remember something", "goodbye!",
    "you live in the cartridge.", "the weather is nice", "i am excited",
    "we are friends already!", "that was quick, quickly.", "you are willing.",
    "thank you for your company.", "i am a little bit sad", "what things.",
    "hmm... ok", "a\"b'c-d;e:f", "zzzz zzzz zzzz zzzz", "i like you!!!",
]


def corpus_lines(n=300):
    path = os.environ.get("REI_CORPUS") or "C:/crashcode/chatgbc_x/build/friend3.txt"
    if not Path(path).exists():
        return []
    lines = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("> "):
                text = line[2:].rstrip("\n").lower()
                if text and len(text) <= 44 and set(text) <= KEYBOARD:
                    lines.add(text)
    return random.Random(5).sample(sorted(lines), min(n, len(lines)))


@pytest.fixture(scope="module")
def rom():
    r = lab_rom()
    r.pyboy.tick(400, False)
    yield r
    r.close()


def python_encode(tok, text, cont):
    if cont:
        return tok.encode(text, bos=False, prefix=False)
    return tok.encode(text)


def check(r, tok, line):
    worst = 0
    for cont, staged in ((False, "> " + line + "\n"), (True, "\n> " + line + "\n")):
        got, cycles = rom_encode(r, staged, cont)
        assert got == python_encode(tok, staged, cont), (staged, got)
        worst = max(worst, cycles)
    return worst


def test_the_longest_piece_is_the_exporters():
    tok = Tokenizer()
    defs = __import__("harness").load_defs(APP / "src" / "model.inc")
    assert defs["ENC_PIECE_MAX"] == max(len(p) for p in tok.vocab) > 7


def test_every_topic_sentence(rom):
    tok = Tokenizer()
    for _, lines in rei_topics.TOPICS:
        for line in lines:
            check(rom, tok, line)


def test_typed_lines_and_the_long_pieces(rom):
    tok = Tokenizer()
    long_ids = {i for i, p in enumerate(tok.vocab) if len(p) > 7}
    reached = set()
    for line in TYPED:
        check(rom, tok, line)
        reached |= long_ids & set(tok.encode("> " + line + "\n"))
    assert len(reached) >= 5, "the sample reaches pieces the old encoder could not"


def test_lines_from_her_corpus(rom):
    lines = corpus_lines()
    if not lines:
        pytest.skip("her corpus is not on this machine")
    tok = Tokenizer()
    worst = max(check(rom, tok, line) for line in lines)
    assert worst < 400_000, f"an encode took {worst:,} cycles"


def test_a_long_line_is_quick(rom):
    """44 characters, the most the keyboard takes: well under a tenth of a second."""
    line = "i remember something about the weather today"[:44]
    assert len(line) == 44
    cycles = check(rom, Tokenizer(), line)
    assert cycles < 250_000, cycles
