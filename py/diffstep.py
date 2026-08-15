"""Locate a wrong kernel by diffing the ROM's first forward pass against the twin.

Runs the ROM until it has produced its first token, then compares each activation
buffer with the same value from py/quant.py. The first buffer that differs names
the kernel to look at, which beats inferring it from wrong text.
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


def main():
    model, tok = ref.Model(), ref.Tokenizer()
    sites = Q.calibrate(model, seq_len=E.SEQ)
    q = Q.quantize_model(model, sites, weight_bits=E.WEIGHT_BITS)
    rtbl = Q.rope_table(E.SEQ, q.cfg.head_size)
    c = q.cfg

    prompt = tok.encode("Once upon a time")
    token, pos = prompt[0], 0

    # --- what the twin computes for step 0 ---
    ex = q.site("x", 0)
    x = Q.requant(q.w("tok_emb")[token].astype(np.int32),
                  q.e("tok_emb") + int(q.rex("tok_emb")[token]), ex)
    want = {"wX(embed)": x}

    exb = q.site("xb_att", 0)
    xb = Q.rmsnorm(x, q.w("rms_att", 0), q.e("rms_att"), exb)
    want["wXb(rmsnorm)"] = xb

    qv = Q.requant_rows(Q.matvec(q.w("wq", 0), xb), q.e("wq") + exb,
                        q.rex("wq", 0), q.site("q", 0))
    want["wQ(pre-rope)"] = qv
    want["wQ(post-rope)"] = Q.rope_q(qv, pos, rtbl)

    # --- what the ROM has after its first forward ---
    rom = Rom()
    for _ in range(200000):
        rom.pyboy.tick(1, False)
        if rom.read("wGenCount")[0] >= 1:
            break
    else:
        print("ROM never finished a token")
        return

    got = {
        "wX(embed)": None,          # overwritten by the residual; skipped below
        "wXb(rmsnorm)": signed(rom.read("wXb", c.dim)),
        "wQ(post-rope)": signed(rom.read("wQ", c.dim)),
    }

    for name, expect in want.items():
        actual = got.get(name)
        if actual is None:
            continue
        expect = np.asarray(expect, dtype=np.int64)
        bad = np.flatnonzero(expect != actual)
        if bad.size == 0:
            print(f"OK    {name}")
        else:
            i = int(bad[0])
            print(f"DIFF  {name}: {bad.size}/{expect.size} differ, "
                  f"first at {i}: rom={actual[i]} want={expect[i]}")
            print(f"      rom  {list(actual[:12])}")
            print(f"      want {list(expect[:12])}")

    print("\nROM text:", repr(rom.text()))
    rom.close()


if __name__ == "__main__":
    main()
