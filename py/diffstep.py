"""Localize a wrong kernel by diffing the ROM's first forward pass against the twin.

Each layer writes its K and V for the current position into its own WRAM bank,
and those survive the whole pass. Comparing them per layer says exactly where
the two implementations first disagree, which beats inferring it from wrong text.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export as E  # noqa: E402
import quant as Q  # noqa: E402
import reference as ref  # noqa: E402
from harness import Rom  # noqa: E402


def signed(b):
    return np.array([v - 256 if v > 127 else v for v in b], dtype=np.int64)


def show(name, got, want, limit=10):
    got, want = np.asarray(got, np.int64), np.asarray(want, np.int64)
    bad = np.flatnonzero(got != want)
    if bad.size == 0:
        print(f"  OK    {name}")
        return True
    i = int(bad[0])
    print(f"  DIFF  {name}: {bad.size}/{want.size} differ, first at {i}: "
          f"rom={got[i]} want={want[i]}")
    print(f"        rom  {list(got[:limit])}")
    print(f"        want {list(want[:limit])}")
    return False


def main():
    model, tok = ref.Model(), ref.Tokenizer()
    sites = Q.calibrate(model, seq_len=E.SEQ)
    q = Q.quantize_model(model, sites, weight_bits=E.WEIGHT_BITS)
    rtbl = Q.rope_table(E.SEQ, q.cfg.head_size)
    c = q.cfg
    pos = 0

    # --- twin, step 0 ---
    state = Q.QState(c, E.SEQ)
    token = tok.encode("Once upon a time")[0]
    ex = q.site("x", 0)
    x = Q.requant(q.w("tok_emb")[token].astype(np.int32),
                  q.e("tok_emb") + int(q.rex("tok_emb")[token]), ex)
    want_k, want_v, want_xb = [], [], None

    for l in range(c.n_layers):
        exb = q.site("xb_att", l)
        xb = Q.rmsnorm(x, q.w("rms_att", l), q.e("rms_att"), exb)
        if l == 0:
            want_xb0 = xb
        eq_, ek_, ev_ = q.site("q", l), q.site("k", l), q.site("v", l)
        qv = Q.requant_rows(Q.matvec(q.w("wq", l), xb), q.e("wq") + exb, q.rex("wq", l), eq_)
        kv = Q.requant_rows(Q.matvec(q.w("wk", l), xb), q.e("wk") + exb, q.rex("wk", l), ek_)
        vv = Q.requant_rows(Q.matvec(q.w("wv", l), xb), q.e("wv") + exb, q.rex("wv", l), ev_)
        qv = Q.rope_q(qv, pos, rtbl)
        kv = Q.rope_q(kv, pos, rtbl)
        state.k[l, pos], state.v[l, pos] = kv, vv
        want_k.append(kv.astype(np.int64))
        want_v.append(vv.astype(np.int64))

        hs, kvm = c.head_size, c.kv_mul
        eout = q.site("att_out", l)
        xb2 = np.zeros(c.dim, dtype=np.int8)
        for h in range(c.n_heads):
            qh = qv[h * hs:(h + 1) * hs].astype(np.int32)
            base = (h // kvm) * hs
            keys = state.k[l, :pos + 1, base:base + hs].astype(np.int32)
            att = Q.softmax_weights(keys @ qh, eq_ + ek_)
            vals = state.v[l, :pos + 1, base:base + hs].astype(np.int64)
            acc = (att[:, None] * vals).sum(axis=0)
            xb2[h * hs:(h + 1) * hs] = Q.sat8(Q.rescale(acc, ev_ - Q.EXP_BITS, eout))
        if l == 0:
            want_xb2 = xb2.astype(np.int64)
        wo = Q.requant_rows(Q.matvec(q.w("wo", l), xb2), q.e("wo") + eout, q.rex("wo", l), ex)
        x = Q.add_requant(x, ex, wo, ex, ex)
        if l == 0:
            want_res = x.astype(np.int64)
            want_h1 = None

        exf = q.site("xb_ffn", l)
        xbf = Q.rmsnorm(x, q.w("rms_ffn", l), q.e("rms_ffn"), exf)
        e1, e3, eh = q.site("h1", l), q.site("h3", l), q.site("hb", l)
        h1 = Q.requant_rows(Q.matvec(q.w("w1", l), xbf), q.e("w1") + exf, q.rex("w1", l), e1)
        h3 = Q.requant_rows(Q.matvec(q.w("w3", l), xbf), q.e("w3") + exf, q.rex("w3", l), e3)
        hb = Q.silu_mul(h1, e1, h3, e3, eh)
        w2 = Q.requant_rows(Q.matvec(q.w("w2", l), hb), q.e("w2") + eh, q.rex("w2", l), ex)
        if l == 0:
            want_ffn0 = w2.astype(np.int64)
        x = Q.add_requant(x, ex, w2, ex, ex)

    want_xb = Q.rmsnorm(x, q.w("rms_final"), q.e("rms_final"), q.site("xb_final", 0))

    # --- ROM ---
    rom = Rom()
    for _ in range(400000):
        rom.pyboy.tick(1, False)
        if rom.read("wGenCount")[0] >= 1:
            break
    else:
        print("ROM produced no token")
        return

    print(f"token {token}, pos {pos}\n")
    ok = True
    for l in range(c.n_layers):
        bank = E.__dict__.get("KV_BANK_BASE", 2) + l
        k = signed(bytes(rom.pyboy.memory[bank, 0xD000:0xD000 + c.kv_dim]))
        v = signed(bytes(rom.pyboy.memory[bank, 0xD800:0xD800 + c.kv_dim]))
        ok &= show(f"layer {l} K", k, want_k[l])
        ok &= show(f"layer {l} V", v, want_v[l])
        if not ok:
            break

    print()
    show("layer 0 attention out (wXb2)", signed(rom.read("wDbgAtt", c.dim)), want_xb2)
    show("layer 0 x after attn residual", signed(rom.read("wDbgRes", c.dim)), want_res)
    show("layer 0 ffn out (pre-residual)", signed(rom.read("wDbgFfn", c.dim)), want_ffn0)

    if ok:
        show("final rmsnorm (wXb)", signed(rom.read("wXb", c.dim)), want_xb)
        got_tok = int.from_bytes(rom.read("wBestTok", 2), "little")
        print(f"  argmax rom={got_tok}")

    rom.close()


if __name__ == "__main__":
    main()
