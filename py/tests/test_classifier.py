"""The output-major ternary classifier (src/cls4.asm) against the twin.

Three views of the same contract. The generation view: after the golden
prompt's forced steps, the tables the ROM built in its WRAM bank and the
argmax it picked equal what the twin computes from the same activations.
The probe view: the lab ROM classifies any vector the harness plants (the
twin's xb_final of the first steps, then vectors built to tie), and its top
two must be the twin's stable argsort - ties to the lowest index. The retry
path is covered by golden strict, whose run has no-repeat retries in it.
"""
import json

import numpy as np
import pytest

import export5                    # noqa: E402
import twin5                      # noqa: E402
import quant as Q                 # noqa: E402
from model5 import Model5, Tokenizer   # noqa: E402
from conftest import APP, lab_rom

CLS_BANK = 7
PAGES = 16
POW3 = np.array([1, 3, 9, 27])


@pytest.fixture(scope="module")
def twin():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    sites = twin5.calibrate5(m, tok, export5.cal_prompts())
    q = twin5.quantize5(m, sites)
    assert q.ternary_cls, "this test is for the ternary classifier"
    return q, tok


def _forward_steps(q, ids):
    """(xb_final, logits) for each prompt step, xb caught on its way into
    the classifier: forward_q5's last rmsnorm call is rms_final."""
    seen = []
    orig = Q.rmsnorm

    def catch(*a, **k):
        y = orig(*a, **k)
        seen.append(y)
        return y

    st = twin5.QState5(q.cfg)
    out = []
    Q.rmsnorm = catch
    try:
        for t in ids:
            logits = twin5.forward_q5(q, st, t)
            out.append((np.asarray(seen[-1], dtype=np.int64), logits))
    finally:
        Q.rmsnorm = orig
    return out


def _top2(logits):
    order = np.argsort(-np.asarray(logits), kind="stable")
    return int(order[0]), int(order[1])


def _read_tables(r):
    r.pyboy.memory[0xFF70] = CLS_BANK          # rSVBK, as census5 reads its bank
    raw = bytes(r.pyboy.memory[0xD000:0xE000])
    pages = np.frombuffer(raw, dtype="<i2").reshape(PAGES, 128)
    return pages[:, :81]                      # entry code -> block sum


def _check_tables(tables, xb):
    """Every entry is the direct sum the code names, from the twin's xb."""
    digits = np.array([[(c // p) % 3 for p in POW3] for c in range(81)]) - 1
    for k in range(PAGES):
        want = digits @ xb[4 * k:4 * k + 4]
        assert (tables[k] == want).all(), f"block {k}: {np.nonzero(tables[k] != want)[0][:8]}"


def _probe(r, xb):
    """Plant xb, run the lab's classifier-only entry, read the top two."""
    idle, go = r.defs["LAB_IDLE"], r.defs["LAB_GO_CLS"]
    state, goflag = r.addr("wLabState"), r.addr("wLabGo")
    r.pyboy.memory[goflag] = 0
    r._tick_until(lambda: r.pyboy.memory[state] == idle, 2000,
                  "lab ROM never reached its idle loop")
    base = r.addr("wXb")
    r.pyboy.memory[base:base + len(xb)] = [int(v) & 0xFF for v in xb]
    ready, magic = r.addr("wReady"), r.defs["READY_MAGIC"]
    r.pyboy.memory[ready] = 0
    r.pyboy.memory[goflag] = go
    r._tick_until(lambda: r.pyboy.memory[ready] == magic, 4000, "probe never finished")
    r.pyboy.memory[goflag] = 0
    a = r.read("wClsArg", 2)
    b = r.read("wClsArg2", 2)
    return a[0] | (a[1] << 8), b[0] | (b[1] << 8)


def test_tables_and_argmax_after_the_golden_prompt(twin):
    q, tok = twin
    ids = tok.encode(export5.PROMPT)
    steps = _forward_steps(q, ids)
    xb, logits = steps[-1]                    # the pass that picks the first free token
    r = lab_rom()
    r.lab_run(steps=len(ids), prompt=export5.PROMPT)
    tables = _read_tables(r)
    arg = r.read("wClsArg", 2)
    arg2 = r.read("wClsArg2", 2)
    n = r.read("wGenCount")[0]
    out = r.read("wOutTokens", 2 * n)
    r.close()
    _check_tables(tables, xb)
    # the single-coefficient entries are the activations themselves
    got_xb = np.array([tables[k][40 + p] for k in range(PAGES) for p in POW3])
    assert (got_xb == xb).all()
    want = _top2(logits)
    assert (arg[0] | (arg[1] << 8), arg2[0] | (arg2[1] << 8)) == want
    assert want[0] == int(np.argmax(Q.matvec_blocks(
        q.weights["tok_emb"], xb, twin5.TERNARY_CLS_BLOCK, twin5.TERNARY_ACC_SHIFT)))
    toks = [out[2 * i] | (out[2 * i + 1] << 8) for i in range(n)]
    g = json.loads((APP / "build" / "golden.json").read_text())
    assert toks == g["tokens"][:len(ids)]
    assert toks[-1] == Q.pick_token(logits, toks[:-1])


def test_probe_matches_the_twin_on_the_first_steps(twin):
    q, tok = twin
    ids = tok.encode(export5.PROMPT)
    r = lab_rom()
    try:
        for xb, logits in _forward_steps(q, ids):
            assert _probe(r, xb) == _top2(logits)
    finally:
        r.close()


def test_probe_ties_go_to_the_lowest_index(twin):
    q, _ = twin
    w = q.weights["tok_emb"]
    r = lab_rom()
    try:
        ties = 0
        vectors = [np.zeros(64, dtype=np.int64)]              # every logit 0
        one = np.zeros(64, dtype=np.int64)
        one[0] = 1                                             # logits in {-1, 0, 1}
        vectors.append(one)
        rng = np.random.default_rng(9)
        vectors += [rng.integers(-1, 2, 64) for _ in range(3)]  # small logits, many ties
        vectors += [rng.integers(-128, 128, 64) for _ in range(3)]  # full-range int8
        for xb in vectors:
            logits = Q.matvec_blocks(w, xb, 4, 0)
            order = np.argsort(-logits, kind="stable")
            ties += int(logits[order[0]] == logits[order[1]])
            assert _probe(r, xb) == (int(order[0]), int(order[1]))
        assert ties >= 2, "the vectors were meant to tie at the top"
    finally:
        r.close()
