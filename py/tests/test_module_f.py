"""The small exact collapses of v0.9 module F against the twin.

  1. Embedding rows ship prescaled to the stream grid: every exported row is
     the twin's own Q.requant(tok_emb[t], wexp, S("x")), and the ROM's
     EmbedToken - now a copy - lands the densest row in wX byte for byte.
  2. The residual add in its page-layout register form (src/addsat.asm):
     the byte rule it uses (overflow from (s^x)&(s^y), -128 to -127) is
     Q.sat8(x + y) for every one of the 255 x 255 input pairs, and the loop
     itself reproduces the twin's add_requant on the exporter's vectors,
     edge cases first.
  3. The layer-0 snapshot probes assemble into the lab ROM only, and the
     ones that remain are right: after a run, each is the twin's own
     intermediate for the same token and the same state.
"""
import re

import numpy as np
import pytest

import export5                    # noqa: E402
import quant as Q                 # noqa: E402
import twin5                      # noqa: E402
from model5 import Model5, Tokenizer   # noqa: E402
from conftest import APP, lab_rom

BLOBS = APP / "build" / "blobs"
INT8 = np.arange(-127, 128, dtype=np.int64)          # every sat8 output


def _const(name):
    inc = (APP / "src" / "model.inc").read_text()
    return int(re.search(rf"DEF {name} EQU (-?\d+)", inc).group(1))


def _symbols(sym):
    return {line.split()[1] for line in (APP / "build" / sym).read_text().splitlines()
            if line and not line.startswith(";") and len(line.split()) == 2}


DIM = _const("DIM")


@pytest.fixture(scope="module")
def q():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    sites = twin5.calibrate5(m, tok, export5.cal_prompts())
    return twin5.quantize5(m, sites), tok


STEPS = 3     # forward passes the lab runs: the prompt's first three tokens


@pytest.fixture(scope="module")
def after_run():
    """STEPS forward passes on the lab ROM (the lab counts passes, so they
    are the prompt's first STEPS tokens, forced), then the probes and the
    selftest answers it left in WRAM bank 1 - one boot serves every check."""
    r = lab_rom()
    r.lab_run(steps=STEPS, prompt=export5.PROMPT)
    assert r.read("wGenCount")[0] == STEPS
    r.pyboy.memory[0xFF70] = 1
    names = ["wDbgEmb", "wDbgAdd", "wDbgXb", "wDbgZl", "wDbgHt", "wDbgAtt",
             "wDbgAccWo", "wDbgAo", "wDbgRes", "wDbgXf", "wDbgRoute",
             "wDbgH1", "wDbgHb", "wDbgFfn"]
    sizes = {"wDbgAdd": _const("TEST_ADD_ROWS") * DIM, "wDbgAccWo": DIM * 2,
             "wDbgRoute": _const("EXPERTS") * 2,
             "wDbgH1": _const("HID_EXP"), "wDbgHb": _const("HID_EXP")}
    got = {n: bytes(r.read(n, sizes.get(n, DIM))) for n in names}
    r.close()
    return got


# --- 1. the embedding ------------------------------------------------------

def test_embed_rows_are_the_twins_requant(q):
    q, _ = q
    want = Q.requant(q.weights["tok_emb"].astype(np.int64), q.wexp["tok_emb"],
                     q.site("x"))
    per = _const("EMB_PER_PART")
    rows = b"".join((BLOBS / f"emb_rows_p{i}.bin").read_bytes()
                    for i in range(_const("EMB_PARTS")))
    got = np.frombuffer(rows, np.int8).reshape(-1, DIM)[:q.cfg.vocab]
    assert per * _const("EMB_PARTS") >= q.cfg.vocab
    assert (got == want).all(), np.argwhere(got != want)[:4]
    # The prescale is the whole of the twin's first line: nothing is left
    # for the ROM to shift, and a row is one copy.
    assert "EMB_SHIFT" not in (APP / "src" / "model.inc").read_text()


def test_embed_copy_lands_the_row(after_run):
    want = np.frombuffer((BLOBS / "test_emb_out.bin").read_bytes(), np.int8)
    got = np.frombuffer(after_run["wDbgEmb"], np.int8)
    assert want.any(), "the densest row should not be all zero"
    assert (got == want).all(), np.nonzero(got != want)[0][:8]


# --- 2. the residual add ---------------------------------------------------

def _addsat_bytes(x, y):
    """src/addsat.asm's byte rule, vectorized: the wrapped sum, overflow from
    bit 7 of (s ^ x) & (s ^ y), 127 / -127 by the wrapped sign, -128 to -127."""
    xb, yb = x & 0xFF, y & 0xFF
    s = (xb + yb) & 0xFF
    over = ((s ^ xb) & (s ^ yb)) & 0x80 != 0
    plain = np.where(s == 0x80, -127, s.astype(np.uint8).astype(np.int8).astype(np.int64))
    sat = np.where(s & 0x80, 127, -127)
    return np.where(over, sat, plain)


def test_addsat_rule_is_sat8_for_every_pair():
    x, y = np.meshgrid(INT8, INT8, indexing="ij")
    got = _addsat_bytes(x, y)
    want = Q.sat8(x + y).astype(np.int64)
    assert (got == want).all(), np.argwhere(got != want)[:4]
    assert got.min() == -127 and got.max() == 127       # never -128


def test_addsat_loop_matches_the_twin(after_run):
    rows = _const("TEST_ADD_ROWS")
    x = np.frombuffer((BLOBS / "test_add_x.bin").read_bytes(), np.int8).astype(np.int64)
    y = np.frombuffer((BLOBS / "test_add_y.bin").read_bytes(), np.int8).astype(np.int64)
    want = np.frombuffer((BLOBS / "test_add_out.bin").read_bytes(), np.int8)
    assert (want == Q.sat8(x + y)).all()                # the exporter's own line
    got = np.frombuffer(after_run["wDbgAdd"], np.int8)
    assert got.shape == want.shape == (rows * DIM,)
    assert (got == want).all(), np.nonzero(got != want)[0][:8]
    # The vectors reach the corners the rule has: both saturations, the
    # unwrapped -128, and sums that wrap.
    s = x + y
    assert (s > 127).any() and (s < -128).any() and (s == -128).any()
    assert (s == 127).any() and (s == -127).any()


# --- 3. the probes ---------------------------------------------------------

def test_probes_assemble_into_the_lab_only():
    lab, app = _symbols("chatgbc-lab.sym"), _symbols("chatgbc.sym")
    for name in ("wDbgAtt", "wDbgAccWo", "wDbgFfn", "wDbgEmb", "wDbgAdd"):
        assert name in lab, name
        assert name not in app, name
    assert "wH" in app and "AddSat_Stream" in app     # the model itself stays


def test_layer0_probes_are_the_twins_intermediates(q, after_run):
    """The lab ROM's last forward pass is prompt token STEPS-1, run on the
    state the earlier tokens left; the twin's layer 0 on that token, step by
    step (twin5.forward_q5's lines), is what each probe holds."""
    q, tok = q
    ids = tok.encode(export5.PROMPT)
    st = twin5.QState5(q.cfg)
    for t in ids[:STEPS - 1]:
        twin5.forward_q5(q, st, t)
    token, h_prev = ids[STEPS - 1], st.h[0].copy()
    assert h_prev.any(), "a zero state would not exercise the gate's blend"
    assert q.ternary.get("wo") and q.ternary.get("wz"), "the ROM runs the block kernels"

    ex = q.site("x")
    x = Q.requant(q.weights["tok_emb"][token].astype(np.int64), q.wexp["tok_emb"], ex)
    exb = q.site("xb_att", 0)
    xb = Q.rmsnorm(x, q.weights["rms_att"][0], q.wexp["rms_att"], exb)
    ezl, eh = q.site("zl", 0), q.site("h", 0)
    zl = twin5.mv(q, "wz", 0, xb, exb, ezl)
    zg = q.sig_tables[0][zl.astype(np.int64) + 128]
    ht = twin5.mv(q, "wh", 0, xb, exb, eh)
    h = Q.sat8(Q.shr_round(zg * ht.astype(np.int64) + (256 - zg) * h_prev, 8))
    acc_wo = Q.matvec_blocks(q.weights["wo"][0], h, twin5.TERNARY_BLOCK,
                             twin5.TERNARY_ACC_SHIFT)
    ao = twin5.mv(q, "wo", 0, h, eh, ex)
    res = Q.add_requant(x, ex, ao, ex, ex)
    exf = q.site("xb_ffn", 0)
    xf = Q.rmsnorm(res, q.weights["rms_ffn"][0], q.wexp["rms_ffn"], exf)
    route = Q.matvec_blocks(q.router_t[0], xf, twin5.TERNARY_BLOCK, 0)
    e = int(np.argmax(route))
    e1, ehb = q.site("h1", 0), q.site("hb", 0)
    a = twin5.mv(q, "w1", 0, xf, exf, e1, e=e)
    u = Q.sat8(twin5.shr_round_any(np.maximum(a.astype(np.int64), 0) ** 2, ehb - 2 * e1))
    ffn = twin5.mv(q, "w2", 0, u, ehb, ex, e=e)

    want = {"wDbgXb": xb, "wDbgZl": zl, "wDbgHt": ht, "wDbgAtt": h, "wDbgAo": ao,
            "wDbgRes": res, "wDbgXf": xf, "wDbgH1": a, "wDbgHb": u, "wDbgFfn": ffn}
    for name, vec in want.items():
        got = np.frombuffer(after_run[name], np.int8).astype(np.int64)
        assert (got == np.asarray(vec, dtype=np.int64)).all(), \
            (name, np.nonzero(got != vec)[0][:8])
    got_acc = np.frombuffer(after_run["wDbgAccWo"], "<i2").astype(np.int64)
    assert (got_acc == acc_wo).all(), np.nonzero(got_acc != acc_wo)[0][:8]
    got_route = np.frombuffer(after_run["wDbgRoute"], "<i2").astype(np.int64)
    assert (got_route == route).all(), (got_route, route)
