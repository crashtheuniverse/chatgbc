"""ShiftRound24 against Q.shr_round at every count 0..24.

The routine grew a byte peel (src/regmath.asm) that only runs for counts
above 8. On this model nothing reaches it any more - the norm has its own
16-bit shift and gru's relu2 shifts are 6 and 7 - so the golden run cannot
witness it. The lab ROM's LAB_GO_SHIFT op runs the routine on values the
test chooses: every count, signed values across the whole 24-bit range, and
the half-way points where round-half-up decides.
"""
import numpy as np
import pytest

import quant as Q                 # noqa: E402
from conftest import lab_rom


class Shifter:
    def __init__(self):
        self.r = lab_rom()
        self.r.pyboy.tick(400, False)
        d = self.r.defs
        self.idle, self.go, self.magic = d["LAB_IDLE"], d["LAB_GO_SHIFT"], d["READY_MAGIC"]

    def close(self):
        self.r.close()

    def run(self, value, count):
        r, m = self.r, self.r.pyboy.memory
        m[r.addr("wLabGo")] = 0
        r._tick_until(lambda: m[r.addr("wLabState")] == self.idle, 2000,
                      "lab ROM never reached its idle loop")
        v = int(value) & 0xFFFFFF
        base = r.addr("wX")
        m[base:base + 4] = [v & 0xFF, (v >> 8) & 0xFF, v >> 16, int(count)]
        m[r.addr("wReady")] = 0
        m[r.addr("wLabGo")] = self.go
        r._tick_until(lambda: m[r.addr("wReady")] == self.magic, 2000,
                      "the shift op never finished")
        m[r.addr("wLabGo")] = 0
        out = r.read("wXb", 3)
        got = out[0] | (out[1] << 8) | (out[2] << 16)
        return got - (1 << 24) if got & 0x800000 else got


@pytest.fixture(scope="module")
def shifter():
    s = Shifter()
    yield s
    s.close()


def test_shiftround24_every_count(shifter):
    rng = np.random.default_rng(24)
    lim = 1 << 23
    bad = []
    for b in range(0, 25):
        values = list(rng.integers(-lim, lim, 12))
        # The rounding boundary: exactly half, one below and one above, at a
        # few magnitudes of either sign - where floor and round-half-up part.
        if b > 0:
            half = 1 << (b - 1)
            for k in (0, 1, 5, 300, -1, -6, -301):
                for d in (-1, 0, 1):
                    values.append(k * (1 << b) + half + d)
        values += [lim - 1, -lim, 0, -1, 1]
        for v in values:
            v = int(np.clip(v, -lim, lim - 1))
            want = int(Q.shr_round(np.int64(v), b))
            got = shifter.run(v, b)
            if got != want:
                bad.append(f"b={b} v={v}: rom {got} twin {want}")
    assert not bad, "\n".join(bad[:20])
