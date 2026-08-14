"""The matvec + requantization path must be bit-exact.

This checks the whole chain the layers are built on: build the product table,
accumulate int24, remove the bias, apply the per-output-row shift with
round-half-up, and saturate to int8. Every value is compared against the
integer twin. "Close" is a failure - an off-by-one here would surface as
mysteriously degraded text once ten kernels sit on top of it.
"""

from pathlib import Path

import pytest

BLOBS = Path(__file__).resolve().parent.parent.parent / "build" / "blobs"


def signed(b):
    return [v - 256 if v > 127 else v for v in b]


@pytest.fixture(scope="module")
def h1(rom):
    return signed(rom.read("wH1", rom.defs["HIDDEN"]))


def test_requantized_output_is_bit_exact(h1):
    want = signed((BLOBS / "test_h1.bin").read_bytes())
    assert len(h1) == len(want)
    bad = [(i, a, w) for i, (a, w) in enumerate(zip(h1, want)) if a != w]
    assert not bad, f"{len(bad)} of {len(want)} outputs differ; first: {bad[:5]}"


def test_output_is_not_trivial(h1):
    """Guards against a kernel that never ran; all-zero would otherwise pass
    only by luck of the expected values."""
    assert len(set(h1)) > 16


def test_cycles_per_mac_recorded(rom):
    cycles = rom.read_u32("wMvCycles")
    macs = rom.defs["DIM"] * rom.defs["HIDDEN"]
    per_mac = cycles / macs
    print(f"\n  matvec+requant: {cycles:,} cycles / {macs:,} MACs = {per_mac:.1f} cycles/MAC")
    assert cycles > 0
    # A regression guard, not a target. Tighten it whenever the kernel improves.
    assert per_mac < 70, f"{per_mac:.1f} cycles/MAC is a regression"
