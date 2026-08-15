"""Phase 2: the ROM must generate the same text as the integer twin.

build/golden.json is produced by py/golden.py running quant.py in exactly the
configuration export.py ships. Matching it token for token means every kernel -
rmsnorm, rope, softmax, swiglu, attention, the matvecs and the classifier -
agrees with the reference, because a single wrong value anywhere changes an
argmax and the sequences diverge from that point on.
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


def rom_text(rom):
    """Everything the ROM printed after the header block."""
    lines = rom.console_lines()
    body = lines[6:]
    return "".join(body).rstrip()


def test_rom_generated_something(rom):
    assert rom.read("wGenCount")[0] > 0, "no tokens were emitted"


def test_matches_golden_text(rom, golden):
    want = golden["text"].replace("\n", "")
    got = rom_text(rom)
    # The console wraps at 20 columns and drops newlines, so compare the
    # printable characters in order.
    want_flat = "".join(want.split())
    got_flat = "".join(got.split())
    n = min(len(want_flat), len(got_flat))
    assert n > 0
    assert got_flat[:n] == want_flat[:n], (
        f"diverged at char {next((i for i in range(n) if got_flat[i] != want_flat[i]), n)}\n"
        f"  rom:  {got_flat[:80]!r}\n"
        f"  want: {want_flat[:80]!r}"
    )


def test_cycles_per_token_recorded(rom):
    cycles = rom.read_u32("wTokCycles")
    assert cycles > 0
    secs = cycles / 2_097_152          # CGB double speed
    print(f"\n  {cycles:,} cycles/token = {secs:.2f} s/token "
          f"= {secs / 2.81:.2f} s/char at 2.81 chars/token")
