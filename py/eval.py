"""Score a quantization choice, in seconds.

What makes this project's loop fast is not the emulator - it is that the oracle
is cheap and its answers are definite. Training a model is the moment that stops
being true, so the evaluation is built before the trainer.

    .venv\\Scripts\\python.exe py\\eval.py                 the shipped config
    .venv\\Scripts\\python.exe py\\eval.py --bits 3        a candidate
    .venv\\Scripts\\python.exe py\\eval.py --cls-bits 4    without the 8-bit head
    .venv\\Scripts\\python.exe py\\eval.py --corpus FILE   absolute quality too

Three numbers, because they answer different questions.

**top-1** is agreement with fp32's own argmax, teacher-forced. It answers "does
this pick the same word", which is what actually shows up on screen. It is
coarse: a choice that was nearly a tie counts the same as one that was not.

**KL** is the mean divergence from fp32's next-token distribution, in bits. It
sees damage top-1 cannot - a model can keep the argmax while losing everything
behind it - and it degrades smoothly, so it is the better signal when comparing
two schemes that both score well.

Both are *fidelity* measures: they ask how closely a quantized model tracks the
float model it came from. Neither can compare two different models, because
there is no shared reference to agree with. **Cross-entropy on held-out text**
can, which is why --corpus exists even though there is no corpus yet. It will
matter the moment we train our own.

Prompts are split. The dev set is what everything so far was tuned against; the
held-out set is scored separately and is the number to quote.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export as E
import quant as Q
import reference as ref

DEV = [
    "Once upon a time",
    "Lily and Tom went to the park",
    "The little dog was very happy because",
    "Tim was sad. His mom said",
    "One day, a girl named Sara found a red box",
]
HELD_OUT = [
    "The cat sat on the",
    "Anna wanted to help her friend, so she",
    "It was raining and the boy could not",
    "Ben opened the door and saw a big",
    "Every morning the old man would",
    "The bird did not want to fly, because",
]
# Long enough that every window under test is genuinely saturated. At 48 steps
# a 64-slot window never truncates anything, so it was being scored as if it had
# unlimited context - which flattered it against every narrower setting.
STEPS = 96
# The window the exporter actually ships. Hardcoding it here once meant this
# scored a 64-slot model while the ROM ran 32 - reporting a number for a
# configuration that was not being built.
SEQ = E.SEQ
# fp32 is the ideal being tracked, so it gets the whole context. Scoring it at
# the ROM's window would measure the quantized model against an equally
# handicapped reference and hide exactly the cost we want to see.
REF_SEQ = 256


def reference_paths(model, tok, prompts):
    """fp32's own greedy sequence, its argmax, and its full distribution."""
    paths = []
    for prompt in prompts:
        state = ref.State(model.cfg, REF_SEQ)
        toks = tok.encode(prompt)
        token, seq, picks, dists = toks[0], [toks[0]], [], []
        for pos in range(STEPS):
            logits = ref.forward(model, state, token, pos)
            picks.append(int(logits.argmax()))
            dists.append(softmax(logits.astype(np.float64)))
            nxt = toks[pos + 1] if pos + 1 < len(toks) else int(logits.argmax())
            if nxt == ref.EOS:
                break
            seq.append(nxt)
            token = nxt
        paths.append((seq, picks, dists))
    return paths


def logit_scale(q):
    """forward_q returns integers on a common exponent, not float logits.

    Softmaxing them raw gives a near one-hot distribution and a KL in the tens of
    bits, which is nonsense next to 80% top-1 agreement. The accumulator's unit
    is 2 ** (classifier exponent + input site + ACC_SHIFT + the smallest row
    shift), so undoing that puts them back in fp32's units.
    """
    rex = q.rex("wcls").astype(np.int64)
    return 2.0 ** (q.e("wcls") + q.site("xb_final", 0) + Q.ACC_SHIFT + int(rex.min()))


def softmax(v):
    e = np.exp(v - v.max())
    return e / e.sum()


def score(q, paths):
    """Replay fp32's sequences through the quantized model. Returns (top-1, KL)."""
    rtbl = Q.rope_table(REF_SEQ, q.cfg.head_size)
    scale = logit_scale(q)
    same = total = 0
    kl = 0.0
    for seq, picks, dists in paths:
        state = Q.QState(q.cfg, SEQ)
        for pos, token in enumerate(seq[: len(picks)]):
            logits = Q.forward_q(q, state, token, pos, rtbl)
            same += int(logits.argmax()) == picks[pos]
            p, r = dists[pos], softmax(logits.astype(np.float64) * scale)
            nz = p > 0
            kl += float(np.sum(p[nz] * np.log2(p[nz] / np.maximum(r[nz], 1e-12))))
            total += 1
    return 100.0 * same / total, kl / total


def cross_entropy(q, tok, text):
    """Bits per token on held-out text. The only one of the three that can
    compare two different models, because it needs no reference to agree with."""
    rtbl = Q.rope_table(256, q.cfg.head_size)
    scale = logit_scale(q)
    toks = tok.encode(text)
    state = Q.QState(q.cfg, SEQ)
    bits = 0.0
    for pos in range(len(toks) - 1):
        logits = Q.forward_q(q, state, toks[pos], pos, rtbl)
        p = softmax(logits.astype(np.float64) * scale)
        bits -= np.log2(max(float(p[toks[pos + 1]]), 1e-12))
    return bits / max(len(toks) - 1, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bits", type=int, default=E.WEIGHT_BITS,
                    help="weight width for everything but the classifier")
    ap.add_argument("--cls-bits", type=int, default=8, help="classifier width")
    ap.add_argument("--corpus", type=Path, help="held-out text for cross-entropy")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    model, tok = ref.Model(), ref.Tokenizer()
    sites = Q.calibrate(model, seq_len=SEQ)
    q = Q.quantize_model(model, sites, weight_bits=args.bits,
                         bits_override={"tok_emb": args.cls_bits})

    out = {"bits": args.bits, "cls_bits": args.cls_bits}
    for label, prompts in (("dev", DEV), ("held-out", HELD_OUT)):
        paths = reference_paths(model, tok, prompts)
        top1, kl = score(q, paths)
        out[label] = {"top1": round(top1, 1), "kl_bits": round(kl, 4),
                      "positions": sum(len(p) for _, p, _ in paths)}
    if args.corpus:
        out["cross_entropy_bits"] = round(
            cross_entropy(q, tok, args.corpus.read_text(encoding="utf-8")), 4)
    out["seconds"] = round(time.time() - t0, 1)

    if args.json:
        print(json.dumps(out, indent=1))
        return
    print(f"\n  weights {args.bits}-bit, classifier {args.cls_bits}-bit\n")
    print(f"  {'split':<10}{'top-1':>8}{'KL bits':>10}{'positions':>11}")
    for label in ("dev", "held-out"):
        r = out[label]
        print(f"  {label:<10}{r['top1']:>7.1f}%{r['kl_bits']:>10.4f}{r['positions']:>11}")
    if "cross_entropy_bits" in out:
        print(f"\n  held-out cross-entropy  {out['cross_entropy_bits']:.4f} bits/token")
    print(f"\n  {out['seconds']}s\n")


if __name__ == "__main__":
    main()
