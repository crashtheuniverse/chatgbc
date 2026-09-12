"""RmsNorm alone, on vectors chosen to reach every branch, against Q.rmsnorm.

The golden run exercises the norm on the model's own activations, which all
land at e in 14..20. This drives the lab ROM's LAB_GO_NORM op over the rest
of the input space: a sum of squares at and around powers of two (the byte
select's four length classes at every byte position), tiny vectors whose
first shift runs left, a spike that saturates the gain step, the zero
vector, and random vectors at every scale - each checked integer for
integer against the twin's line, with the exported gains and shifts.
"""
import numpy as np
import pytest

import quant as Q                 # noqa: E402
from conftest import APP, lab_rom

BLOBS = APP / "build" / "blobs"


def _dim():
    inc = (APP / "src" / "model.inc").read_text()
    return int(inc.split("DEF DIM EQU ")[1].split()[0])


def _final_shift():
    inc = (APP / "src" / "model.inc").read_text()
    return int(inc.split("DEF RMSFINAL_SHIFT EQU ")[1].split()[0])


DIM = _dim()


def norms():
    """(name, layer, gains, shift) for every norm the ROM runs."""
    att = np.frombuffer((BLOBS / "rms_att.bin").read_bytes(), np.int8)
    ffn = np.frombuffer((BLOBS / "rms_ffn.bin").read_bytes(), np.int8)
    fin = np.frombuffer((BLOBS / "rms_final.bin").read_bytes(), np.int8)
    satt = (BLOBS / "rmsatt_shift.bin").read_bytes()
    sffn = (BLOBS / "rmsffn_shift.bin").read_bytes()
    out = []
    for l in range(len(att) // DIM):
        out.append(("rms_att", l, att[l * DIM:(l + 1) * DIM], satt[l]))
    for l in range(len(ffn) // DIM):
        out.append(("rms_ffn", l, ffn[l * DIM:(l + 1) * DIM], sffn[l]))
    out.append(("rms_final", 0, fin, _final_shift()))
    return out


def twin(x, gains, shift):
    # Q.rmsnorm's closing shift is out_exp - (-11 + w_exp); with w_exp 0 the
    # exported shift byte is out_exp + 11.
    return Q.rmsnorm(np.asarray(x, np.int64), gains.astype(np.int64), 0, shift - 11)


class Norm:
    """The lab ROM parked in its idle loop, running one norm per request."""

    def __init__(self):
        self.r = lab_rom()
        self.r.pyboy.tick(400, False)
        d = self.r.defs
        self.idle, self.go, self.magic = d["LAB_IDLE"], d["LAB_GO_NORM"], d["READY_MAGIC"]

    def close(self):
        self.r.close()

    def run(self, x, name, layer, shift):
        r, m = self.r, self.r.pyboy.memory
        m[r.addr("wLabGo")] = 0
        r._tick_until(lambda: m[r.addr("wLabState")] == self.idle, 2000,
                      "lab ROM never reached its idle loop")
        x = np.asarray(x, np.int8)
        assert x.size == DIM
        base = r.addr("wX")
        m[base:base + DIM] = [int(v) & 0xFF for v in x]
        gain = r.addr(name) + layer * DIM
        m[r.addr("wRnGain")] = gain & 0xFF
        m[r.addr("wRnGain") + 1] = gain >> 8
        m[r.addr("wRnShift")] = int(shift)
        m[r.addr("wReady")] = 0
        m[r.addr("wLabGo")] = self.go
        r._tick_until(lambda: m[r.addr("wReady")] == self.magic, 20000,
                      "the norm op never finished")
        m[r.addr("wLabGo")] = 0
        return np.frombuffer(bytes(r.read("wXb", DIM)), np.int8).copy()


@pytest.fixture(scope="module")
def norm():
    n = Norm()
    yield n
    n.close()


def vectors(gains):
    """Named int8 vectors for one norm; each is run through it."""
    rng = np.random.default_rng(5)
    v = {}
    z = np.zeros(DIM, np.int64)

    # ss exactly at, one below and one above a power of two, at even and odd
    # bit lengths - the byte select's edges: 2^16 puts a 1 in the third byte,
    # 2^16 - 1 a 255 in the second; 2^15 a 128 there, 2^12 a 16, 2^12 - 1 a
    # 15, 2^10 a 4, 2^10 - 1 a 3, 2^8 a 1; 2^8 - 1 and below have only the
    # first byte, down to ss = 1 where e = 2 and the first shift is by 1.
    def with_ss(target):
        """A vector with sum of squares exactly `target`, greedy squares."""
        out, rest, i = z.copy(), target, 0
        while rest:
            s = min(127, int(np.sqrt(rest)))
            out[i] = s if i % 2 == 0 else -s
            rest -= s * s
            i += 1
            assert i < DIM, target
        return out
    for k in (16, 15, 12, 10, 8, 6, 4, 2):
        v[f"ss=2^{k}"] = with_ss(1 << k)
        v[f"ss=2^{k}-1"] = with_ss((1 << k) - 1)
        v[f"ss=2^{k}+1"] = with_ss((1 << k) + 1)
    v["ss=3"] = with_ss(3)
    v["ss=1"] = with_ss(1)
    v["ss=0"] = z.copy()

    # The largest sum: every element at the int8 limit (ss = 64 * 127^2,
    # e = 20, p = 10, top byte 15 at position 2).
    v["all -127"] = np.full(DIM, -127, np.int64)
    v["all 127"] = np.full(DIM, 127, np.int64)

    # One spike: x_hat reaches its extreme (~2^14 at Q11), and at the norm's
    # largest gain the gain step saturates - the witness for sat8's clamp.
    top = int(np.argmax(gains))
    v["spike +127"] = z.copy(); v["spike +127"][top] = 127
    v["spike -127"] = z.copy(); v["spike -127"][top] = -127
    v["spike at 0"] = z.copy(); v["spike at 0"][0] = 127
    v["two spikes"] = z.copy(); v["two spikes"][3] = 100; v["two spikes"][40] = -100

    # Random vectors at every scale, so e sweeps its range.
    for k in range(0, 8):
        r = rng.integers(-127, 128, DIM)
        v[f"random/2^{k}"] = np.clip(r // (1 << k), -127, 127)
    v["random signs"] = rng.choice([-1, 1], DIM) * rng.integers(0, 4, DIM)
    return v


def test_norm_matches_the_twin_on_every_vector(norm):
    bad = []
    for name, layer, gains, shift in norms():
        for label, x in vectors(gains).items():
            want = twin(x, gains, shift)
            got = norm.run(x, name, layer, shift)
            if not np.array_equal(got, want):
                i = int(np.nonzero(got != want)[0][0])
                bad.append(f"{name}[{layer}] {label}: element {i} rom {got[i]} twin {want[i]}")
    assert not bad, "\n".join(bad)


def test_saturation_and_the_left_shift_actually_happen():
    """The vectors above only prove something if they reach the paths they
    were built for: check on the twin that the spike saturates at every norm
    and that the tiny sums put the first shift below 8."""
    for name, layer, gains, shift in norms():
        v = vectors(gains)
        top = int(np.argmax(gains))
        assert twin(v["spike +127"], gains, shift)[top] == 127, (name, layer)
        assert twin(v["spike -127"], gains, shift)[top] == -127, (name, layer)
    v = vectors(norms()[0][2])
    for k in (2, 4, 6, 8, 10, 12):
        ss = int((v[f"ss=2^{k}"].astype(np.int64) ** 2).sum())
        assert ss == 1 << k
        e = ss.bit_length() + (ss.bit_length() & 1)
        assert e // 2 < 8
