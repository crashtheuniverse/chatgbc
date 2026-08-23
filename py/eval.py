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


def free_run(forward, state_new, tok, prompt, n=96):
    """Generate freely and return the token sequence. No teacher forcing.

    This is what is actually on the screen. Teacher-forced top-1 asks "given
    fp32's own history, do you pick the same next token" - a model that has
    stopped being able to finish a sentence still scores well on that, because
    it is handed a good history at every step. Letting it run on its own output
    is the only way to see a model fall into a loop.
    """
    ids = tok.encode(prompt)
    st = state_new()
    token, out = ids[0], []
    for pos in range(n):
        lg = forward(st, token, pos)
        nxt = ids[pos + 1] if pos + 1 < len(ids) else int(lg.argmax())
        if nxt == 3:                      # EOS
            break
        out.append(nxt)
        token = nxt
    return out


def prefix_match(a, b, skip=0):
    """Leading tokens that agree, counted from `skip` - past the forced prompt.

    Measured from zero this mostly scores the prompt, which every configuration
    reproduces because it is fed to them. The held-out prompts are ten tokens
    long, so a 16-token window was 60% prompt and separated nothing.
    """
    n = 0
    for x, y in zip(a[skip:], b[skip:]):
        if x != y:
            break
        n += 1
    return n


def repetition(seq, n=96):
    """Distinct bigrams over the run, which is what catches a loop.

    Distinct *tokens* does not: "a big box with a big box" reuses tokens that
    also appear in healthy text, and scores fine. Repeated pairs are the
    signature - lower is more repetitive.
    """
    s = seq[:n]
    pairs = list(zip(s, s[1:]))
    return len(set(pairs)) / max(len(pairs), 1)


def fp32_continuations(model, tok, prompts, n=STEPS):
    """Let fp32 finish each prompt, and keep what it wrote.

    This is the held-out set we never had. Asking "how surprised is the
    quantized model by text the float model would produce" needs no corpus,
    and unlike top-1 it reads the whole distribution rather than the argmax -
    so a model that keeps the right winner while flattening everything behind
    it is no longer scored as undamaged.
    """
    rtbl = None
    seqs = []
    for prompt in prompts:
        ids = tok.encode(prompt)
        st = ref.State(model.cfg, REF_SEQ)
        token, seq = ids[0], [ids[0]]
        for pos in range(n):
            logits = ref.forward(model, st, token, pos)
            nxt = ids[pos + 1] if pos + 1 < len(ids) else int(logits.argmax())
            if nxt == ref.EOS:
                break
            seq.append(nxt)
            token = nxt
        seqs.append(seq)
    return seqs


def cross_entropy(q, seqs, seq_len=None):
    """Bits per token over token sequences. The only metric here that can
    compare two different models, because it needs no reference to agree with -
    and the only one that ranks the attention window and the weight width on
    the same scale."""
    rtbl = Q.rope_table(REF_SEQ, q.cfg.head_size)
    scale = logit_scale(q)
    bits, n = 0.0, 0
    for seq in seqs:
        state = Q.QState(q.cfg, seq_len or SEQ)
        for pos in range(len(seq) - 1):
            logits = Q.forward_q(q, state, seq[pos], pos, rtbl)
            p = softmax(logits.astype(np.float64) * scale)
            bits -= np.log2(max(float(p[seq[pos + 1]]), 1e-12))
            n += 1
    return bits / max(n, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bits", type=int, default=E.WEIGHT_BITS,
                    help="weight width for everything but the classifier")
    ap.add_argument("--cls-bits", type=int, default=8, help="classifier width")
    ap.add_argument("--window", type=int, default=SEQ,
                    help="attention window to score (default: the ROM's)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    model, tok = ref.Model(), ref.Tokenizer()
    sites = Q.calibrate(model, seq_len=min(args.window, REF_SEQ))
    # Mirrors export.quantize, so this scores the model that ships rather than
    # a nearby one. E.WIDE names the tensors kept at 8 bits with row scales.
    q = Q.quantize_model(model, sites, weight_bits=args.bits,
                         bits_override={"tok_emb": args.cls_bits,
                                        **{n: 8 for n in E.WIDE}},
                         rowscale_8bit=E.WIDE)

    out = {"bits": args.bits, "cls_bits": args.cls_bits, "window": args.window}
    for label, prompts in (("dev", DEV), ("held-out", HELD_OUT)):
        paths = reference_paths(model, tok, prompts)
        top1, kl = score(q, paths)
        out[label] = {"top1": round(top1, 1), "kl_bits": round(kl, 4),
                      "positions": sum(len(p) for _, p, _ in paths)}
    seqs = fp32_continuations(model, tok, HELD_OUT)
    out["cross_entropy_bits"] = round(cross_entropy(q, seqs, args.window), 4)
    out["cross_entropy_tokens"] = sum(len(s) - 1 for s in seqs)
    out["seconds"] = round(time.time() - t0, 1)

    if args.json:
        print(json.dumps(out, indent=1))
        return
    print(f"\n  weights {args.bits}-bit, "
          f"classifier {args.cls_bits}-bit, window {args.window}\n")
    print(f"  {'split':<10}{'top-1':>8}{'KL bits':>10}{'positions':>11}")
    for label in ("dev", "held-out"):
        r = out[label]
        print(f"  {label:<10}{r['top1']:>7.1f}%{r['kl_bits']:>10.4f}{r['positions']:>11}")
    print(f"\n  cross-entropy on fp32's own continuations  "
          f"{out['cross_entropy_bits']:.4f} bits/token "
          f"({out['cross_entropy_tokens']} tokens)")
    print(f"\n  {out['seconds']}s\n")


if __name__ == "__main__":
    main()
