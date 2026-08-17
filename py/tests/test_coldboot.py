"""The ROM must not depend on RAM being zero at power-on.

PyBoy starts WRAM at zero; real hardware and SameBoy start it with garbage. A
variable read before it is written therefore behaves one way in the headless
suite and another way on an emulator - which is precisely how a stale
accumulator flag passed every test here and produced nonsense on SameBoy.

This boots with WRAM deliberately scribbled over and demands the same output.
"""

import json
from pathlib import Path

import pytest

from harness import Rom

BUILD = Path(__file__).resolve().parent.parent.parent / "build"


@pytest.fixture(scope="module")
def dirty_rom():
    r = Rom(dirty_ram=True)
    if r.defs.get("GEN_STEPS", 0) < 1:
        r.close()
        pytest.skip("generation disabled: set GEN_STEPS in src/main.asm")
    r.run_until_ready(max_frames=400000)
    yield r
    r.close()


def test_generates_correctly_from_dirty_ram(dirty_rom):
    path = BUILD / "golden.json"
    if not path.exists():
        pytest.skip("run py/golden.py to produce build/golden.json")
    want = json.loads(path.read_text(encoding="utf-8"))["tokens"]
    n = min(dirty_rom.read("wGenCount")[0], dirty_rom.defs["OUT_MAX"])
    raw = dirty_rom.read("wOutTokens", n * 2)
    got = [int.from_bytes(raw[i * 2 : i * 2 + 2], "little") for i in range(n)]
    m = min(len(got), len(want))
    assert m > 0
    assert got[:m] == want[:m], (
        "output differs when RAM starts dirty, so something is read before it "
        f"is written\n  rom:  {got[:12]}\n  want: {want[:12]}"
    )


def test_double_speed_still_engages(dirty_rom):
    assert dirty_rom.read("wStatus")[0] & dirty_rom.defs["STATUS_DOUBLE"]
