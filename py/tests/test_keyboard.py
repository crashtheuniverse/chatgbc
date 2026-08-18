"""The entry screen, and the one bug it shipped with.

The cursor is a CGB background attribute, so exactly one cell in VRAM bank 1
carries palette 1 at any time. Anything that leaves the screen has to clear it -
otherwise an inverted cell is stranded in VRAM and shows up as a black block
over whatever the generation screen draws there.
"""

import pytest

from harness import Rom


@pytest.fixture(scope="module")
def entry():
    r = Rom()
    r.pyboy.tick(400, False)          # boot through to the entry screen
    yield r
    r.close()


def lines(rom):
    return [l for l in rom.console_lines() if l]


def test_entry_screen_drawn(entry):
    body = lines(entry)
    assert "CHATGBC" in body[0]
    assert any("a b c d" in l for l in body), "spaced grid missing"
    assert any("SELECT" in l for l in body), "case hint missing"


def test_default_prompt_is_editable(entry):
    assert any("Once upon a time" in l for l in lines(entry))


def test_cursor_highlights_exactly_one_cell(entry):
    attrs = bytes(entry.pyboy.memory[1, 0x9800:0x9800 + 32 * 18])
    assert sum(1 for a in attrs if a) == 1, "the cursor must own exactly one cell"


def test_select_flips_case(entry):
    entry.pyboy.button_press("select")
    entry.pyboy.tick(4, False)
    entry.pyboy.button_release("select")
    entry.pyboy.tick(8, False)
    assert any("A B C D" in l for l in lines(entry)), "SELECT did not switch case"
    entry.pyboy.button_press("select")
    entry.pyboy.tick(4, False)
    entry.pyboy.button_release("select")
    entry.pyboy.tick(8, False)


def test_no_attribute_stranded_after_leaving(rom):
    """rom has already run START -> generate. Nothing should still be inverted."""
    attrs = bytes(rom.pyboy.memory[1, 0x9800:0x9800 + 32 * 18])
    assert not any(attrs), (
        "an inverted cell survived into the generation screen, which draws as a "
        "black block over the text"
    )
