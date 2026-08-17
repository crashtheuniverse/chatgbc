"""Measure the true dynamic range of every matvec accumulator.

The kernel currently uses int24 accumulators, which cost 6 cycles per MAC for
the third byte. int16 would be cheaper, but only if accumulators genuinely fit -
a wrapped accumulator is far worse than a saturated one, because it flips sign
instead of clamping. So measure, don't assume.

Reports both the biased sum the ROM actually accumulates and the unbiased one,
since the bias is what forces 24 bits today.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export as E  # noqa: E402
import quant as Q  # noqa: E402
import reference as ref  # noqa: E402

PROMPTS = ["Once upon a time", "Lily and Tom went to the park",
           "The little dog was very happy because", "Tim was sad. His mom said"]


def main():
    model, tok = ref.Model(), ref.Tokenizer()
    sites = Q.calibrate(model, seq_len=E.SEQ)
    q = Q.quantize_model(model, sites, weight_bits=E.WEIGHT_BITS)
    rtbl = Q.rope_table(E.SEQ, q.cfg.head_size)
    c = q.cfg

    worst = {}

    def note(name, acc, n_in):
        a = np.abs(np.asarray(acc, dtype=np.int64)).max()
        biased = a + n_in * E.BIAS
        prev = worst.get(name, (0, 0))
        worst[name] = (max(prev[0], int(a)), max(prev[1], int(biased)))

    orig = Q.matvec

    for prompt in PROMPTS:
        state = Q.QState(c, E.SEQ)
        toks = tok.encode(prompt)
        token = toks[0]
        for pos in range(24):
            # Instrument by recomputing each matvec the twin performs.
            ex = q.site("x", 0)
            x = Q.requant(q.w("tok_emb")[token].astype(np.int32),
                          q.e("tok_emb") + int(q.rex("tok_emb")[token]), ex)
            for l in range(c.n_layers):
                exb = q.site("xb_att", l)
                xb = Q.rmsnorm(x, q.w("rms_att", l), q.e("rms_att"), exb)
                for nm, dst in (("wq", "q"), ("wk", "k"), ("wv", "v")):
                    note(nm, orig(q.w(nm, l), xb), c.dim)
                qv = Q.requant_rows(orig(q.w("wq", l), xb), q.e("wq") + exb, q.rex("wq", l), q.site("q", l))
                kv = Q.requant_rows(orig(q.w("wk", l), xb), q.e("wk") + exb, q.rex("wk", l), q.site("k", l))
                vv = Q.requant_rows(orig(q.w("wv", l), xb), q.e("wv") + exb, q.rex("wv", l), q.site("v", l))
                qv, kv = Q.rope_q(qv, pos, rtbl), Q.rope_q(kv, pos, rtbl)
                state.k[l, pos], state.v[l, pos] = kv, vv

                hs, kvm = c.head_size, c.kv_mul
                eout = q.site("att_out", l)
                xb2 = np.zeros(c.dim, dtype=np.int8)
                for h in range(c.n_heads):
                    qh = qv[h * hs:(h + 1) * hs].astype(np.int32)
                    base = (h // kvm) * hs
                    keys = state.k[l, :pos + 1, base:base + hs].astype(np.int32)
                    att = Q.softmax_weights(keys @ qh, q.site("q", l) + q.site("k", l))
                    vals = state.v[l, :pos + 1, base:base + hs].astype(np.int64)
                    acc = (att[:, None] * vals).sum(axis=0)
                    xb2[h * hs:(h + 1) * hs] = Q.sat8(Q.rescale(acc, q.site("v", l) - Q.EXP_BITS, eout))
                note("wo", orig(q.w("wo", l), xb2), c.dim)
                wo = Q.requant_rows(orig(q.w("wo", l), xb2), q.e("wo") + eout, q.rex("wo", l), ex)
                x = Q.add_requant(x, ex, wo, ex, ex)

                exf = q.site("xb_ffn", l)
                xbf = Q.rmsnorm(x, q.w("rms_ffn", l), q.e("rms_ffn"), exf)
                note("w1", orig(q.w("w1", l), xbf), c.dim)
                note("w3", orig(q.w("w3", l), xbf), c.dim)
                e1, e3, eh = q.site("h1", l), q.site("h3", l), q.site("hb", l)
                h1 = Q.requant_rows(orig(q.w("w1", l), xbf), q.e("w1") + exf, q.rex("w1", l), e1)
                h3 = Q.requant_rows(orig(q.w("w3", l), xbf), q.e("w3") + exf, q.rex("w3", l), e3)
                hb = Q.silu_mul(h1, e1, h3, e3, eh)
                note("w2", orig(q.w("w2", l), hb), c.hidden_dim)
                w2 = Q.requant_rows(orig(q.w("w2", l), hb), q.e("w2") + eh, q.rex("w2", l), ex)
                x = Q.add_requant(x, ex, w2, ex, ex)

            xf = Q.rmsnorm(x, q.w("rms_final"), q.e("rms_final"), q.site("xb_final", 0))
            acc_cls = orig(q.w("wcls"), xf, acc_check=False)
            note("wcls", acc_cls, c.dim)

            # Follow the model's own trajectory, so the activations stay realistic.
            rex = q.rex("wcls").astype(np.int64)
            logits = np.array([int(a) << int(r) for a, r in zip(acc_cls, rex - rex.min())],
                              dtype=np.int64)
            token = toks[pos + 1] if pos + 1 < len(toks) else int(logits.argmax())

    print(f"{'matrix':<8} {'max |unbiased|':>15} {'max biased':>12}  int16?  int24?")
    for name, (a, b) in sorted(worst.items()):
        print(f"{name:<8} {a:>15,} {b:>12,}  "
              f"{'yes' if a < 32768 else 'NO ':>5}  {'yes' if b < (1 << 23) else 'NO'}")
    print("\nint16 needs the *unbiased* column under 32,768.")
    print(f"headroom factor: {32768 / max(a for a, _ in worst.values()):.1f}x")


if __name__ == "__main__":
    main()
