"""Compare weight quantization schemes on generation quality.

The ROM's matvec builds a per-input product table indexed by the weight, so the
table has 2**weight_bits entries. At 8 bits it costs ~4096 cycles to build and is
amortized over only 64-172 outputs; at 4 bits, ~200. This script asks what 4 bits
costs in quality.

Quality is measured teacher-forced: both models are fed the *same* fp32-generated
token sequence and we count how often they pick the same next token. Free-running
text can't measure this - one different argmax early on makes everything after it
disagree for reasons that have nothing to do with quantization.
"""

import numpy as np

import quant as Q
import reference as ref

PROMPTS = [
    "Once upon a time",
    "Lily and Tom went to the park",
    "The little dog was very happy because",
    "Tim was sad. His mom said",
    "One day, a girl named Sara found a red box",
]
STEPS, SEQ = 48, 64


def effective_weights(q, name, layer=None):
    """Reconstruct the float weights the ROM will actually multiply by."""
    w = q.weights[name] if layer is None else q.weights[name][layer]
    rex = q.rowexp[name] if layer is None else q.rowexp[name][layer]
    return w.astype(np.float64) * 2.0 ** (q.wexp[name] + rex[..., None].astype(np.float64))


def weight_error(model, q):
    errs = []
    for name in Q.MATMULS:
        ref_w = getattr(model, name).astype(np.float64)
        if name == "wq":
            ref_w = ref_w / np.sqrt(model.cfg.head_size)
        if ref_w.ndim == 3:
            got = np.stack([effective_weights(q, name, l) for l in range(ref_w.shape[0])])
        else:
            got = effective_weights(q, name)
        errs.append(np.sqrt(((ref_w - got) ** 2).mean()) / ref_w.std())
    return float(np.mean(errs))


def reference_paths(model, tok):
    """fp32's own greedy token sequences, plus its argmax at every position."""
    paths = []
    for prompt in PROMPTS:
        state = ref.State(model.cfg, SEQ)
        toks = tok.encode(prompt)
        token, seq, picks = toks[0], [toks[0]], []
        for pos in range(STEPS):
            logits = forward = ref.forward(model, state, token, pos)
            picks.append(int(forward.argmax()))
            nxt = toks[pos + 1] if pos + 1 < len(toks) else int(logits.argmax())
            if nxt == ref.EOS:
                break
            seq.append(nxt)
            token = nxt
        paths.append((seq, picks))
    return paths


def top1_agreement(q, paths):
    """Replay the fp32 sequences through the quantized model, comparing argmax."""
    rtbl = Q.rope_table(SEQ, q.cfg.head_size)
    same = total = 0
    for seq, picks in paths:
        state = Q.QState(q.cfg, SEQ)
        for pos, token in enumerate(seq[: len(picks)]):
            logits = Q.forward_q(q, state, token, pos, rtbl)
            same += int(logits.argmax()) == picks[pos]
            total += 1
    return 100.0 * same / total


def main():
    model, tok = ref.Model(), ref.Tokenizer()
    print("calibrating...", flush=True)
    sites = Q.calibrate(model)
    paths = reference_paths(model, tok)

    configs = [
        ("all 8-bit", 8, None),
        ("all 4-bit", 4, None),
        ("4-bit layers, 8-bit classifier", 4, {"tok_emb": 8}),
    ]
    for label, bits, override in configs:
        q = Q.quantize_model(model, sites, weight_bits=bits, bits_override=override)
        rom = sum(q.weights[n].size * q.bits[n] // 8 for n in Q.MATMULS)
        print(f"\n=== {label} ===")
        print(f"  matmul weight RMSE / sigma  : {weight_error(model, q):.4f}")
        print(f"  teacher-forced top-1 vs fp32: {top1_agreement(q, paths):.1f}%")
        print(f"  matmul bytes in ROM         : {rom:,}")
        out = "".join(t for _, t in Q.generate_q(q, tok, PROMPTS[0], 40, SEQ))
        print(f"  sample: {out!r}")


if __name__ == "__main__":
    main()
