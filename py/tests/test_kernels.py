"""The new kernels against the exporter's known answers."""
import numpy as np

import export5                    # noqa: E402
from conftest import APP


def _dim():
    inc = (APP / "src" / "model.inc").read_text()
    return int(inc.split("DEF DIM EQU ")[1].split()[0])


DIM = _dim()          # the model's width, from the export - not a number typed in


def test_gate_matches_the_twin_vectors(booted):
    want = np.frombuffer((APP / "build" / "blobs" / "test_gate_out.bin"
                          ).read_bytes(), np.int8)
    got = np.frombuffer(bytes(booted.read("wGateOut", DIM)), np.int8)
    assert (got == want).all(), np.nonzero(got != want)[0][:8]


def test_matvec_requant_bit_exact():
    # The selftest runs after a generation, so it cannot be read at boot.
    from conftest import lab_rom
    want = np.frombuffer((APP / "build" / "blobs" / "test_h1.bin"
                          ).read_bytes(), np.int8)
    r = lab_rom()
    r.lab_run(steps=1, prompt=export5.PROMPT)
    got = np.frombuffer(bytes(r.read("wH1", len(want))), np.int8)
    r.close()
    assert (got == want).all()
