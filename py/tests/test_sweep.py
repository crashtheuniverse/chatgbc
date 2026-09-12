"""The output-major sweep (src/sweep.asm, src/matvec3.asm) against the twin.

Four views of the same contract. The stream view: every sweep blob decodes
back to the very {-1, 0, 1} matrix the twin multiplies by, with the twin's
own per-row shifts inline. The table view: the block tables the ROM built
for the selftest vector are the exact direct sums the codes name. The
kernel view: the lab ROM's w1 rows over that vector, at the model's shifts
and at synthetic ones (s = 1, rows that saturate both ways), and its router
choice, equal Q.matvec_blocks + Q.requant_rows and twin5.route. The layer
view: the golden prompt's layer-0 probes - xb to zl and ht, h to ao, xf to
the expert and h1 - reproduce twin5.mv on the ROM's own inputs, so a wrong
kernel is located by layer. The forward pass is covered by golden strict.
"""
import numpy as np
import pytest

import export5                    # noqa: E402
import twin5                      # noqa: E402
import quant as Q                 # noqa: E402
from model5 import Model5, Tokenizer   # noqa: E402
from conftest import APP, lab_rom

BLOBS = APP / "build" / "blobs"
TBL_BANK = 1                      # MV_TBL_BANK, src/chatgbc.inc
SLOT = export5.SWEEP_SLOT


@pytest.fixture(scope="module")
def q():
    m = Model5(export5.CKPT)
    sites = twin5.calibrate5(m, Tokenizer(), export5.cal_prompts())
    return twin5.quantize5(m, sites)


def _shifts(q, name, l, e=None):
    """The twin's per-row requant shift for a ternary tensor: mv() computes
    shr_round(acc, out_exp - (wexp + in_exp + acc_shift + rowexp))."""
    out_site = {"wz": "zl", "wh": "h", "wo": "x", "w1": "h1"}[name]
    in_site = {"wz": "xb_att", "wh": "xb_att", "wo": "h", "w1": "xb_ffn"}[name]
    to_exp = q.site("x") if out_site == "x" else q.site(out_site, l)
    rowexp = q.rowexp[name][l] if e is None else q.rowexp[name][l][e]
    return to_exp - q.wexp[name] - q.site(in_site, l) - twin5.TERNARY_ACC_SHIFT - rowexp


def _sweep_ref(t, x, shifts):
    """What the ROM's sweep must leave: the twin's exact block sums, then
    its round-half-up requant and sat8, row by row."""
    acc = Q.matvec_blocks(t, x, twin5.TERNARY_BLOCK, twin5.TERNARY_ACC_SHIFT)
    return Q.requant_rows(acc, 0, -np.asarray(shifts, dtype=np.int64), 0)


def test_block_codes_are_the_mixed_radix_digits():
    codes = export5.block_codes()
    assert len(codes) == 27
    for (c0, c1, c2), k in codes.items():
        d = {0: 0, -1: 1, 1: 2}
        assert k == d[c0] + 3 * d[c1] + 9 * d[c2]


def test_streams_decode_to_the_twin_matrices(q):
    dim = q.cfg.dim
    for l in range(q.cfg.layers):
        data = (BLOBS / f"wzh_l{l}.bin").read_bytes()
        t, sh, used = export5.decode_sweep_rows(data, dim)
        assert (t == q.indices["wz"][l]).all() and (sh == _shifts(q, "wz", l)).all()
        t, sh, more = export5.decode_sweep_rows(data[used:], dim)
        assert (t == q.indices["wh"][l]).all() and (sh == _shifts(q, "wh", l)).all()
        assert used + more == len(data)
        data = (BLOBS / f"wo_l{l}.bin").read_bytes()
        t, sh, used = export5.decode_sweep_rows(data, dim)
        assert (t == q.indices["wo"][l]).all() and (sh == _shifts(q, "wo", l)).all()
        assert used == len(data)
        for e in range(q.experts):
            data = (BLOBS / f"w1_l{l}_e{e}.bin").read_bytes()
            t, none, used = export5.decode_sweep_rows(data, dim, with_shift=False)
            assert none is None and (t == q.router_t[l]).all(), (l, e)
            t, sh, more = export5.decode_sweep_rows(data[used:], dim)
            assert (t == q.indices["w1"][l][e]).all(), (l, e)
            assert (sh == _shifts(q, "w1", l, e)).all(), (l, e)
            assert used + more == len(data)
            assert sh.min() >= 1, "the sweep's epilogue is written for s >= 1"


@pytest.fixture(scope="module")
def after_run(q):
    """One golden step on the lab ROM: the layer-0 probes of the forward
    pass, then the selftest's tables, sweeps and route, all from bank 1."""
    r = lab_rom()
    r.lab_run(steps=1, prompt=export5.PROMPT)
    r.pyboy.memory[0xFF70] = TBL_BANK
    dim, hid = q.cfg.dim, q.cfg.hidden
    tbl = bytes(r.pyboy.memory[r.addr("wMvTbl"):r.addr("wMvTbl") + 22 * SLOT])
    got = {
        "h1": np.frombuffer(bytes(r.read("wH1", hid)), np.int8),
        "sw": np.frombuffer(bytes(r.read("wDbgSwOut", hid)), np.int8),
        "sw_expert": r.read("wDbgSwExpert")[0],
        "tables": np.frombuffer(tbl, "<i2").reshape(22, SLOT // 2)[:, :27],
        "xb": np.frombuffer(bytes(r.read("wDbgXb", dim)), np.int8).astype(np.int64),
        "zl": np.frombuffer(bytes(r.read("wDbgZl", dim)), np.int8),
        "ht": np.frombuffer(bytes(r.read("wDbgHt", dim)), np.int8),
        "h": np.frombuffer(bytes(r.read("wDbgAtt", dim)), np.int8).astype(np.int64),
        "ao": np.frombuffer(bytes(r.read("wDbgAo", dim)), np.int8),
        "xf": np.frombuffer(bytes(r.read("wDbgXf", dim)), np.int8).astype(np.int64),
        "expert": r.read("wDbgExpert")[0],
        "dbg_h1": np.frombuffer(bytes(r.read("wDbgH1", hid)), np.int8),
    }
    r.close()
    return got


def test_tables_are_the_direct_sums_of_the_selftest_vector(q, after_run):
    x = np.frombuffer((BLOBS / "test_x.bin").read_bytes(), np.int8).astype(np.int64)
    xp = np.concatenate([x, np.zeros(2, dtype=np.int64)])      # the pad block's two
    inv = {v: k for k, v in export5.block_codes().items()}
    for k in range(22):
        want = np.array([np.dot(inv[c], xp[3 * k:3 * k + 3]) for c in range(27)])
        got = after_run["tables"][k]
        if k == 21:                       # the pad block: only digit-0 pads are built
            reach = [c for c in range(27) if inv[c][1] == 0 and inv[c][2] == 0]
            assert (got[reach] == want[reach]).all(), k
        else:
            assert (got == want).all(), f"block {k}: {np.nonzero(got != want)[0][:8]}"


def test_w1_sweep_matches_the_twin_at_the_model_shifts(q, after_run):
    want = np.frombuffer((BLOBS / "test_h1.bin").read_bytes(), np.int8)
    assert (after_run["h1"] == want).all(), np.nonzero(after_run["h1"] != want)[0][:8]


def test_sweep_epilogue_at_s1_and_saturating_rows(q, after_run):
    x = np.frombuffer((BLOBS / "test_x.bin").read_bytes(), np.int8)
    t, sh, _ = export5.decode_sweep_rows((BLOBS / "test_sw.bin").read_bytes(), q.cfg.dim)
    assert (sh == 1).sum() >= q.cfg.hidden // 3 and sh.min() == 1
    want = _sweep_ref(t, x, sh)
    exported = np.frombuffer((BLOBS / "test_sw_out.bin").read_bytes(), np.int8)
    assert (want == exported).all()
    assert (want == 127).any() and (want == -127).any()
    got = after_run["sw"]
    assert (got == want).all(), np.nonzero(got != want)[0][:8]


def test_router_sweep_matches_the_twin_route(q, after_run):
    x = np.frombuffer((BLOBS / "test_x.bin").read_bytes(), np.int8)
    assert after_run["sw_expert"] == twin5.route(q, 0, x)
    assert after_run["sw_expert"] == (BLOBS / "test_sw_expert.bin").read_bytes()[0]


def test_layer0_probes_reproduce_twin_mv_on_the_rom_inputs(q, after_run):
    """Each layer-0 matvec on the ROM's own probed input: locates a wrong
    kernel by stage even when golden strict only says which token."""
    g = after_run
    exb, ezl, eh = q.site("xb_att", 0), q.site("zl", 0), q.site("h", 0)
    assert (g["zl"] == twin5.mv(q, "wz", 0, g["xb"], exb, ezl)).all(), "wz"
    assert (g["ht"] == twin5.mv(q, "wh", 0, g["xb"], exb, eh)).all(), "wh"
    assert (g["ao"] == twin5.mv(q, "wo", 0, g["h"], eh, q.site("x"))).all(), "wo"
    e = twin5.route(q, 0, g["xf"])
    assert g["expert"] == e, "router"
    exf, eh1 = q.site("xb_ffn", 0), q.site("h1", 0)
    assert (g["dbg_h1"] == twin5.mv(q, "w1", 0, g["xf"], exf, eh1, e=e)).all(), "w1"
