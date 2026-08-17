"""Phase 0: the ROM boots CGB-only in double speed, draws text, and its
self-measured cycle count agrees with arithmetic done on paper.

The last test is the important one. Everything this project claims about speed
comes out of the ROM's TIMA profiler, so the profiler has to be shown correct
against a block of work whose cost can be counted by hand.
"""


def test_reports_cgb_and_double_speed(rom):
    status = rom.read("wStatus")[0]
    assert status & rom.defs["STATUS_CGB"], "ROM did not detect a CGB boot"
    assert status & rom.defs["STATUS_DOUBLE"], "double-speed switch did not take"


def test_text_rendering_works(rom):
    """The banner scrolls away once generation is long enough, so assert that
    the console holds rendered text rather than one specific line."""
    body = "".join("".join(rom.console_lines()).split())
    assert len(body) > 20


def test_vram_matches_shadow(rom):
    """Guards the GDMA path: without it the screen would stay blank on hardware
    even though every text assertion above still passed."""
    assert rom.vram_lines() == rom.console_lines()


def test_cycles_are_ticks_times_divider(rom):
    """wProfTicks/wProfCycles hold the most recent measurement, which is the
    matvec; the calibration result is copied aside into wCalCycles."""
    ticks = rom.read_u32("wProfTicks")
    cycles = rom.read_u32("wProfCycles")
    assert ticks > 0
    assert cycles == ticks * rom.defs["PROF_TICK_CYCLES"]


def test_profiler_matches_hand_counted_cycles(rom):
    # Mirrors src/main.asm Measure: `ld bc, N` costs 3 M-cycles, then each
    # iteration is nop 1 + nop 1 + dec bc 2 + ld a,b 1 + or c 1 + jr 3 = 9,
    # with the final untaken jr costing 2 instead of 3.
    iters = rom.defs["CAL_ITERS"]
    expected = 3 + 9 * iters - 1

    measured = rom.read_u32("wCalCycles")
    tick = rom.defs["PROF_TICK_CYCLES"]

    # The measured span also covers Prof_Start's tail, the call to Prof_Stop and
    # ~5 timer interrupts, so it must land just above the hand count, never below
    # it beyond one tick of quantisation.
    assert measured >= expected - tick, f"{measured} is below the {expected} floor"
    assert measured <= expected * 1.01, (
        f"{measured} exceeds {expected} by more than 1% "
        f"({measured - expected} cycles of unexplained overhead)"
    )
