"""Bits per character of what ships: the integer twin on held-out TinyStories.

The trainer grades the float model with its quantizers switched on; this
scores the exported integers - the same calibration, the same block sums,
the same requantization the cartridge performs - on the first stories of the
V2 validation file, teacher-forced from each story's start, up to 256 tokens.
That is the protocol v0.3 was scored under (1.412 bits/char as shipped,
1.261 for its fp32 checkpoint), so the two numbers compare.

The twin returns raw classifier sums; a logit is a sum times the tied
embedding's scale times the normalized stream's scale, both powers of two,
and the first positions are checked against the fp32 model to make sure the
exponent bookkeeping is right before any bit is counted.

    python py/score5.py                    the shipping checkpoint, 200 stories
    python py/score5.py --stories 50
"""

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export5                    # noqa: E402  (CKPT, tokenizer default, cal_prompts)
import twin5                      # noqa: E402
import model5                     # noqa: E402
from model5 import Model5, Tokenizer   # noqa: E402

ROOT = export5.ROOT
VALID = ROOT / "models" / "tinystories" / "ts_valid_v2.txt"


def softmax_bits(logits, target):
    v = logits - logits.max()
    p = np.exp(v)
    return -math.log2(max(float(p[target] / p.sum()), 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories", type=int, default=200)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--valid", type=Path, default=VALID)
    args = ap.parse_args()

    m = Model5(export5.CKPT)
    tok = Tokenizer()
    q = twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts()))
    scale = 2.0 ** (q.wexp["tok_emb"] + q.site("xb_final"))

    text = args.valid.read_text(encoding="utf-8")
    stories = [s for s in text.split("\n\n") if s.strip()][:args.stories]
    seqs = [tok.encode(s)[:args.max_tokens] for s in stories]
    ntok = sum(len(s) - 1 for s in seqs)
    chars = 0
    for ids in seqs:
        chars += len("".join(tok.decode(t, ids[i - 1])
                             for i, t in enumerate(ids) if i >= 1))
    print(f"{export5.CKPT.name}: {len(seqs)} stories, {ntok} predicted tokens, "
          f"{chars} chars -> {chars / ntok:.3f} chars/token", flush=True)

    # The exponent check: twin logits against fp32 on the first story.
    st_f, st_q = model5.State5(m.cfg), twin5.QState5(q.cfg)
    ratios = []
    for pos in range(min(8, len(seqs[0]) - 1)):
        lf = model5.forward5(m, st_f, seqs[0][pos])
        lq = twin5.forward_q5(q, st_q, seqs[0][pos]).astype(np.float64) * scale
        lf, lq = lf - lf.mean(), lq - lq.mean()
        ratios.append(float(np.dot(lf, lq) / max(np.dot(lq, lq), 1e-9)))
    print(f"fp32/twin logit ratio over the first 8 positions: "
          f"{np.mean(ratios):.3f} (1.0 means the exponents are right)", flush=True)

    bits_f = bits_q = 0.0
    t0 = time.time()
    for n, ids in enumerate(seqs, 1):
        st_f, st_q = model5.State5(m.cfg), twin5.QState5(q.cfg)
        for pos in range(len(ids) - 1):
            bits_f += softmax_bits(model5.forward5(m, st_f, ids[pos]), ids[pos + 1])
            lq = twin5.forward_q5(q, st_q, ids[pos]).astype(np.float64) * scale
            bits_q += softmax_bits(lq, ids[pos + 1])
        if n % 25 == 0:
            done = sum(len(s) - 1 for s in seqs[:n])
            print(f"  {n} stories: fp32 {bits_f / done:.4f}  twin {bits_q / done:.4f} "
                  f"bits/token  [{time.time() - t0:.0f}s]", flush=True)
    print(f"fp32 checkpoint: {bits_f / ntok:.4f} bits/token = {bits_f / chars:.4f} bits/char")
    print(f"twin (what ships): {bits_q / ntok:.4f} bits/token = {bits_q / chars:.4f} bits/char")
    print(f"v0.3 for comparison: 1.261 bits/char fp32, 1.412 as shipped")


if __name__ == "__main__":
    main()
