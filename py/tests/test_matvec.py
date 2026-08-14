"""Phase 1: the matvec kernel must be bit-exact, and its cost must be known.

The accumulators are compared against py/export.py's arithmetic element by
element. "Close" is a failure - every later kernel is built on this one, and an
off-by-one here would surface as mysteriously degraded text ten kernels later.
"""

import struct
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parent.parent.parent / "build"


def expected_accumulators():
    blob = (BUILD / "mv_expected.bin").read_bytes()
    return [int.from_bytes(blob[i : i + 3], "little") for i in range(0, len(blob), 3)]


@pytest.fixture(scope="module")
def acc(rom):
    m = rom.defs["MV_M"]
    raw = rom.read("wAcc", m * 3)
    return [int.from_bytes(raw[i * 3 : i * 3 + 3], "little") for i in range(m)]


def test_accumulators_are_bit_exact(acc):
    want = expected_accumulators()
    assert len(acc) == len(want)
    bad = [(i, a, w) for i, (a, w) in enumerate(zip(acc, want)) if a != w]
    assert not bad, f"{len(bad)} of {len(want)} accumulators differ; first: {bad[:3]}"


def test_accumulators_are_not_trivial(acc):
    """Guards against a kernel that never ran: all-zero would otherwise only be
    caught if the expected values happened to be nonzero."""
    assert len(set(acc)) > len(acc) // 2


def test_cycles_per_mac_recorded(rom):
    cycles = rom.read_u32("wMvCycles")
    macs = rom.defs["MV_MACS"]
    per_mac = cycles / macs
    print(f"\n  matvec: {cycles:,} cycles / {macs:,} MACs = {per_mac:.1f} cycles/MAC")
    assert cycles > 0
    # A regression guard, not a target. Tighten it whenever the kernel improves.
    assert per_mac < 60, f"{per_mac:.1f} cycles/MAC is a regression"
