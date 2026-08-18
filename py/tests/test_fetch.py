"""Is code faster out of HRAM?

On a GBA it would be - IWRAM has a 32-bit bus and no wait states where EWRAM is
16-bit with two, so hot routines get copied there. On a Game Boy every region
answers in one M-cycle and instruction fetch is no exception, so it should make
no difference whatsoever.

The ROM runs an identical position-independent loop from both places and times
each with its own cycle counter. These assertions are what keep the claim in
src/fetchtest.asm honest.
"""

from harness import Rom


def test_both_measurements_ran(rom):
    assert rom.read_u32("wRomCycles") > 0
    assert rom.read_u32("wHramCycles") > 0


def test_hram_execution_is_no_faster(rom):
    r, h = rom.read_u32("wRomCycles"), rom.read_u32("wHramCycles")
    tick = rom.defs["PROF_TICK_CYCLES"]
    assert abs(h - r) <= tick, (
        f"ROM {r} vs HRAM {h} differ by {abs(h - r)} cycles, more than the "
        f"{tick}-cycle resolution of the profiler. If this ever fires, code "
        f"really does execute at different speeds by region and the comment in "
        f"src/fetchtest.asm is wrong."
    )


def test_the_measurement_could_detect_a_difference(rom):
    """A test that cannot fail proves nothing.

    The loop has to be long enough that a per-fetch penalty would exceed one
    profiler tick. At 4000 iterations of 23 cycles, even a 1% difference would
    be ~920 cycles - fourteen ticks, far outside the tolerance above.
    """
    tick = rom.defs["PROF_TICK_CYCLES"]
    assert rom.read_u32("wRomCycles") > 100 * tick
