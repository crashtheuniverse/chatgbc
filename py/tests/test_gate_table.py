"""The gate table (src/gate.asm) against the twin's gate line, exhaustively.

Three things are proven here, none of them by sampling:

  1. the identities the one-byte table rests on hold for every (zg, ht, h):
     h + ((zg*(ht-h) + 128) >> 8) is the twin's sat8(shr_round(s, 8)), it
     never leaves [min(h, ht), max(h, ht)], and a byte of it suffices;
  2. the exported rows and side pages, read exactly as the loop reads them
     (bank from the side page, high byte + the subtract's borrow, the byte
     sum with h ^ $80), give the twin's answer for every (zl, ht, h) of
     every layer - 3 x 256 x 255 x 255 inputs;
  3. the cartridge agrees: after a run, wH for every layer is the twin's
     state after the same tokens.
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


@pytest.fixture(scope="module")
def q():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    sites = twin5.calibrate5(m, tok, export5.cal_prompts())
    return twin5.quantize5(m, sites)


def twin_gate(zg, ht, h):
    """py/twin5.py forward_q5's gate line, verbatim."""
    s = zg * ht + (256 - zg) * h
    return Q.sat8(Q.shr_round(s, 8))


def test_identities_hold_for_every_input():
    ht, h = np.meshgrid(INT8, INT8, indexing="ij")
    for zg in range(256):
        want = twin_gate(zg, ht, h)
        t = (zg * (ht - h) + 128) >> 8
        assert (want == h + t).all(), zg
        assert (want >= np.minimum(h, ht)).all() and (want <= np.maximum(h, ht)).all(), zg
        # one byte of T is enough: the wrapped sum is the answer as int8
        byte = ((h + (t & 0xFF)) & 0xFF).astype(np.uint8).astype(np.int8)
        assert (byte == want).all(), zg


def test_exported_rows_are_the_formula(q):
    rows, parts, sides = export5.gate_tables(q.sig_tables)
    assert rows == sorted({int(v) for t in q.sig_tables for v in t})
    assert _const("GATE_ROWS") == len(rows) and _const("GATE_BANKS") == len(parts)
    table = b"".join((BLOBS / f"gate_rows_p{i}.bin").read_bytes() for i in range(len(parts)))
    assert table == b"".join(parts)
    u = np.arange(512, dtype=np.int64)
    for r, v in enumerate(rows):
        row = np.frombuffer(table[r * 512:(r + 1) * 512], np.uint8).astype(np.int64)
        assert (row == ((((v * (u - 256)) + 128) >> 8) + 128) & 0xFF).all(), v


def test_table_and_loop_bytes_equal_the_twin_for_every_input(q):
    bank0 = _const("GATE_BANK0")
    table = np.frombuffer(b"".join(
        (BLOBS / f"gate_rows_p{i}.bin").read_bytes()
        for i in range(_const("GATE_BANKS"))), np.uint8).astype(np.int64)
    ht, h = np.meshgrid(INT8, INT8, indexing="ij")
    e = (h + 128) & 0xFF                              # h ^ $80
    t = (ht + 128) & 0xFF                             # ht ^ $80
    lo = (t - e) & 0xFF                               # sub e: d mod 256
    upper = (t >= e).astype(np.int64)                 # ccf: carry iff d >= 0
    for l, sig in enumerate(q.sig_tables):
        side = np.frombuffer((BLOBS / f"gate_side_l{l}.bin").read_bytes(), np.uint8)
        assert len(side) == 512
        for zl_byte in range(256):
            zl = zl_byte - 256 if zl_byte >= 128 else zl_byte
            bank, hi = int(side[zl_byte]), int(side[256 + zl_byte])
            addr = ((hi + upper) << 8) | lo           # the loop's hl
            off = (bank - bank0) * 0x4000 + (addr - 0x4000)
            got = ((table[off] + e) & 0xFF).astype(np.uint8).astype(np.int8)
            want = twin_gate(int(sig[zl + 128]), ht, h)
            assert (got == want).all(), (l, zl)


def test_state_after_a_run_matches_the_twin_for_every_layer(q):
    steps = 8
    r = lab_rom()
    r.lab_run(steps=steps, prompt=export5.PROMPT)
    n = r.read("wGenCount")[0]
    out = r.read("wOutTokens", 2 * n)
    toks = [out[2 * i] | (out[2 * i + 1] << 8) for i in range(n)]
    dim, layers = _const("DIM"), _const("N_LAYERS")
    got = np.frombuffer(bytes(r.read("wH", layers * dim)), np.int8)
    r.close()

    tok = Tokenizer()
    ids = tok.encode(export5.PROMPT)
    st = twin5.QState5(q.cfg)
    token, twin_toks = ids[0], []
    for pos in range(steps):
        logits = twin5.forward_q5(q, st, token)
        forced = pos + 1 < len(ids)
        nxt = ids[pos + 1] if forced else Q.pick_token(logits, twin_toks)
        twin_toks.append(nxt)
        token = nxt
    assert toks == twin_toks
    want = np.concatenate([st.h[l] for l in range(layers)]).astype(np.int8)
    assert (got == want).all(), np.nonzero(got != want)[0][:8]
