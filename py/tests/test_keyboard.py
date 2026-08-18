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
    assert "ChatGBC v0.1" in body[0], "the title carries the version"
    assert any("a b c d" in l for l in body), "spaced grid missing"
    assert any("SELECT" in l for l in body), "case hint missing"


def test_screen_is_framed(entry):
    """The frame is drawn cell by cell, so a corner is easy to lose."""
    con = entry.read("wConsole", entry.defs["CON_SIZE"])
    w, last = entry.defs["CON_W"], entry.defs["CON_VIS_W"] - 1
    bottom = entry.defs["CON_H"] - 1
    tile = {n: entry.defs[n] - entry.defs["FONT_FIRST"]
            for n in ("CH_TL", "CH_TR", "CH_BL", "CH_BR", "CH_V", "CH_LT", "CH_RT")}
    assert con[0] == tile["CH_TL"]
    assert con[last] == tile["CH_TR"]
    assert con[bottom * w] == tile["CH_BL"]
    assert con[bottom * w + last] == tile["CH_BR"]
    # Separator rows cap with tees instead of plain wall, but every row is
    # closed on both sides - a gap would read as a hole in the frame.
    for row in range(1, bottom):
        assert con[row * w] in (tile["CH_V"], tile["CH_LT"]), f"left wall open on row {row}"
        assert con[row * w + last] in (tile["CH_V"], tile["CH_RT"]), f"right wall open on row {row}"
    seps = [r for r in range(1, bottom) if con[r * w] == tile["CH_LT"]]
    assert len(seps) == 2, f"expected a rule above and below the grid, got {seps}"


def test_space_is_typable(entry):
    """A keyboard with no space key can only ever type one word."""
    def prompt():
        n = entry.read("wPromptLen")[0]
        return entry.read("wPromptText", n).decode("latin-1")

    before = prompt()
    for button in ["down", "down"] + ["right"] * 8:   # to the cell after z
        entry.pyboy.button_press(button)
        entry.pyboy.tick(4, False)
        entry.pyboy.button_release(button)
        entry.pyboy.tick(8, False)
    entry.pyboy.button_press("a")
    entry.pyboy.tick(4, False)
    entry.pyboy.button_release("a")
    entry.pyboy.tick(8, False)
    assert prompt() == before + " ", "the space key did not insert a space"

    entry.pyboy.button_press("b")                     # leave the fixture as found
    entry.pyboy.tick(4, False)
    entry.pyboy.button_release("b")
    entry.pyboy.tick(8, False)
    for button in ["up", "up"] + ["left"] * 8:
        entry.pyboy.button_press(button)
        entry.pyboy.tick(4, False)
        entry.pyboy.button_release(button)
        entry.pyboy.tick(8, False)


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
