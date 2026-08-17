"""Phase 2+: the ROM must generate the same tokens as the integer twin.

build/golden.json comes from py/golden.py running quant.py in exactly the
configuration export.py ships. Matching it token for token means every kernel -
rmsnorm, rope, softmax, swiglu, attention, the matvecs and the classifier -
agrees with the reference, because one wrong value anywhere changes an argmax
and the sequences diverge from there on.

The comparison reads the ROM's own record of what it emitted rather than
scraping the screen: once the console scrolls, the display is no longer a
faithful log of the run.
"""

import json
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parent.parent.parent / "build"


@pytest.fixture(autouse=True)
def _requires_generation(rom):
    if rom.defs.get("GEN_STEPS", 0) < 1:
        pytest.skip("generation disabled: set GEN_STEPS in src/main.asm")


@pytest.fixture(scope="module")
def golden():
    path = BUILD / "golden.json"
    if not path.exists():
        pytest.skip("run py/golden.py to produce build/golden.json")
    return json.loads(path.read_text(encoding="utf-8"))


def rom_tokens(rom):
    n = min(rom.read("wGenCount")[0], rom.defs["OUT_MAX"])
    raw = rom.read("wOutTokens", n * 2)
    return [int.from_bytes(raw[i * 2 : i * 2 + 2], "little") for i in range(n)]


def test_rom_generated_something(rom):
    assert rom.read("wGenCount")[0] > 0, "no tokens were emitted"


def test_matches_golden_tokens(rom, golden):
    got, want = rom_tokens(rom), golden["tokens"]
    n = min(len(got), len(want))
    assert n > 0
    bad = next((i for i in range(n) if got[i] != want[i]), None)
    assert bad is None, (
        f"diverged at token {bad} of {n}: rom={got[bad]} want={want[bad]}\n"
        f"  rom:  {got[:12]}\n  want: {want[:12]}"
    )


def test_generates_past_the_window(rom, golden):
    """The KV cache rings at SEQ_LEN, so matching beyond it proves the ring and
    the absolute-position RoPE are both right."""
    seq = rom.defs["SEQ_LEN"]
    if min(rom.read("wGenCount")[0], len(golden["tokens"])) <= seq:
        pytest.skip(f"run generates <= SEQ_LEN ({seq}) tokens")
    assert rom_tokens(rom)[: len(golden["tokens"])] == golden["tokens"][: len(rom_tokens(rom))]


def test_console_shows_the_output(rom):
    """Rendering still works even after the console has scrolled."""
    body = "".join("".join(rom.console_lines()).split())
    assert len(body) > 40


def test_cycles_per_token_recorded(rom):
    cycles = rom.read_u32("wTokCycles")
    assert cycles > 0
    secs = cycles / 2_097_152          # CGB double speed
    print(f"\n  {cycles:,} cycles/token = {secs:.2f} s/token "
          f"= {secs / 2.52:.2f} s/char at 2.52 chars/token")
