"""The story ROM's encoder gives the Python tokenizer's tokens, every time.

Through the lab's encode-only entry (LAB_GO_ENC): the default prompt, the
keyboard's eight openers, the calibration stories' openings, and 300 lines cut
from the TinyStories validation text (py/tests/data/ts_valid_300.txt) - each as
long as the keyboard allows. Before v1.0 the ROM stopped at 7-byte pieces
(the story vocabulary has 41 longer ones) and scanned the whole vocabulary
for every pair: see the header of src/encoder.asm.

The chat build has its own: py/tests/test_encoder_rei.py.
"""
import random
from pathlib import Path
import re

import pytest

import export5                    # noqa: E402
from conftest import APP, lab_rom, lab_encode

if export5.CHAT:
    pytest.skip("the story encoder's test (the chat's is test_encoder_rei.py)", allow_module_level=True)

from model5 import Tokenizer      # noqa: E402

KEYS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .,!?'-;:\"")
VALID = APP / "models" / "tinystories" / "TinyStories-valid.txt"


def keyboard_prompts():
    text = (APP / "src" / "keyboard.asm").read_text(encoding="utf-8")
    return re.findall(r'^sP\d: db "([^"]*)", 0', text, re.M)


# The 300 sentences valid_lines() draws from the full validation file, kept in
# the repository so the test runs on a fresh clone; regenerate by pointing
# VALID at TinyStories-valid.txt and writing valid_lines() out, one a line.
SAMPLE = Path(__file__).resolve().parent / "data" / "ts_valid_300.txt"


def valid_lines(n=300):
    if not VALID.exists():
        if SAMPLE.exists():
            return SAMPLE.read_text(encoding="utf-8").splitlines()[:n]
        return []
    lines = set()
    with open(VALID, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i > 20000:
                break
            for sentence in re.split(r"(?<=[.!?])\s+", line.strip()):
                if 4 <= len(sentence) <= 47 and set(sentence) <= KEYS:
                    lines.add(sentence)
    return random.Random(7).sample(sorted(lines), min(n, len(lines)))


@pytest.fixture(scope="module")
def rom():
    r = lab_rom()
    r.pyboy.tick(400, False)
    yield r
    r.close()


def check(r, tok, text):
    got, cycles = lab_encode(r, text, cont=False)
    assert got == tok.encode(text), (text, got, tok.encode(text))
    return cycles


def test_the_prompts_the_rom_and_the_tests_use(rom):
    tok = Tokenizer()
    prompts = [export5.PROMPT] + keyboard_prompts()
    prompts += [p[:47].rsplit(" ", 1)[0] for p in export5.cal_prompts()]
    assert len(keyboard_prompts()) == 8
    for text in prompts:
        check(rom, tok, text)
    assert check(rom, tok, export5.PROMPT) < 100_000


def test_lines_from_the_validation_stories(rom):
    lines = valid_lines()
    if not lines:
        pytest.skip("the TinyStories validation text is not on this machine")
    tok = Tokenizer()
    long_ids = {i for i, p in enumerate(tok.vocab) if len(p) > 7}
    reached = set()
    worst = 0
    for text in lines:
        worst = max(worst, check(rom, tok, text))
        reached |= long_ids & set(tok.encode(text))
    assert reached, "the sample reaches pieces the old encoder could not"
    assert worst < 400_000, worst
