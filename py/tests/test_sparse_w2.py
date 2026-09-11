"""The ReLU^2 pages and the sparse w2 kernel against the twin.

Three things the exact collapse rests on, each checked against py/twin5.py
and py/quant.py directly: the pages are the twin's activation line at every
byte; the column lists decode back to the very matrix the twin multiplies
by; and the lab ROM's sums over both guard paths equal Q.matvec_blocks of
the twin's u. The forward pass is covered by golden strict.
"""
import numpy as np
import pytest

import export5                    # noqa: E402
import twin5                      # noqa: E402
import quant as Q                 # noqa: E402
from model5 import Model5, Tokenizer   # noqa: E402
from conftest import APP, lab_rom

BLOBS = APP / "build" / "blobs"


@pytest.fixture(scope="module")
def q():
    m = Model5(export5.CKPT)
    sites = twin5.calibrate5(m, Tokenizer(), export5.cal_prompts())
    return twin5.quantize5(m, sites)


def _relu2(q, a, l):
    r = q.site("hb", l) - 2 * q.site("h1", l)
    return Q.sat8(twin5.shr_round_any(np.maximum(a.astype(np.int64), 0) ** 2, r))


def test_relu2_pages_are_the_twin_line_at_every_byte(q):
    tbl = np.frombuffer((BLOBS / "relu2_tbl.bin").read_bytes(), np.int8)
    a = np.arange(-128, 128, dtype=np.int64)
    for l in range(q.cfg.layers):
        page = tbl[l * 256:(l + 1) * 256]
        assert (page[a & 0xFF] == _relu2(q, a, l)).all()


def test_column_lists_decode_to_the_twin_w2(q):
    dim, hid = q.cfg.dim, q.cfg.hidden
    for l in range(q.cfg.layers):
        for e in range(q.experts):
            data = (BLOBS / f"w2s_l{l}_e{e}.bin").read_bytes()
            t = export5.decode_sparse_columns(data, dim, hid)
            assert (t == q.weights["w2"][l][e]).all(), (l, e)


def test_sparse_kernel_and_guard_match_matvec_blocks(q):
    dim, hid = q.cfg.dim, q.cfg.hidden
    r = lab_rom()
    r.lab_run(steps=1, prompt=export5.PROMPT)
    r.pyboy.memory[0xFF70] = 1                       # the results sit in bank 1
    limit = r.defs["W2_SPARSE_MAX"]
    got_acc = {tag: np.frombuffer(bytes(r.read(f"wDbgSpAcc{tag.upper()}", dim * 2)), "<i2")
               for tag in ("a", "b")}
    path = r.read("wDbgSpPath", 2)
    count = r.read("wDbgSpCount", 2)
    hb = np.frombuffer(bytes(r.read("wHb", hid)), np.int8)
    sp_list = bytes(r.read("wSpList", hid * 2 + 1))
    sp_count = r.read("wSpCount")[0]
    r.close()

    w2 = q.weights["w2"][0][0]
    for k, tag in enumerate(("a", "b")):
        a = np.frombuffer((BLOBS / f"test_sp_{tag}.bin").read_bytes(), np.int8)
        u = _relu2(q, a, 0)
        want = Q.matvec_blocks(w2, u, twin5.TERNARY_BLOCK, twin5.TERNARY_ACC_SHIFT)
        assert (got_acc[tag] == want).all(), f"{tag}: {np.nonzero(got_acc[tag] != want)[0][:8]}"
        exported = np.frombuffer((BLOBS / f"test_sp_acc_{tag}.bin").read_bytes(), "<i2")
        assert (want == exported).all()
        n = int((u != 0).sum())
        assert count[k] == n
        # the guard: few nonzeros take the sparse kernel, many the dense one
        assert path[k] == (0 if n <= limit else 1), (tag, n, limit, path[k])
    assert path[0] == 0 and path[1] == 1, "both paths must have run"

    # vector a ran last: the dense u and the list are its
    u = _relu2(q, np.frombuffer((BLOBS / "test_sp_a.bin").read_bytes(), np.int8), 0)
    assert (hb == u).all()
    nz = np.nonzero(u)[0]
    assert sp_count == len(nz)
    pairs = [(sp_list[2 * k], np.int8(sp_list[2 * k + 1])) for k in range(len(nz))]
    assert pairs == [(int(i), u[i]) for i in nz]
    assert sp_list[2 * len(nz)] == 0xFF
