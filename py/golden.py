"""Produce the golden token sequence the ROM must reproduce exactly.

Runs the integer twin in precisely the configuration export.py ships, and dumps
per-step intermediates so a failing kernel can be located by layer rather than
by staring at wrong text.
"""

import json
import sys
from pathlib import Path

import numpy as np

import export as E
import harness
import quant as Q
import reference as ref

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "golden.json"


def build():
    model, tok = ref.Model(), ref.Tokenizer()
    sites = Q.calibrate(model, seq_len=E.SEQ)
    q = E.quantize(model, sites)      # the exporter decides; see export.quantize
    return model, tok, q


def default_steps():
    """However many tokens the ROM actually generates.

    Hardcoding a smaller number here silently weakens the suite: the test that
    proves the ring cache wraps skips itself when the golden is shorter than the
    attention window, so a regeneration can drop coverage without failing.
    """
    defs = harness.load_defs(ROOT / "src" / "chatgbc.inc")
    return defs["GEN_STEPS"]


def main():
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else default_steps()
    model, tok, q = build()
    rtbl = Q.rope_table(E.MAX_POS, q.cfg.head_size)
    state = Q.QState(q.cfg, E.SEQ)

    prompt = tok.encode("Once upon a time")
    token, tokens, text = prompt[0], [], ""
    first = None

    for pos in range(steps):
        logits = Q.forward_q(q, state, token, pos, rtbl)
        if pos == 0:
            first = {
                "x": [int(v) for v in Q.requant(
                    q.w("tok_emb")[token].astype(np.int32),
                    q.e("tok_emb") + int(q.rex("tok_emb")[token]), q.site("x", 0))],
                "argmax": int(logits.argmax()),
            }
        nxt = prompt[pos + 1] if pos + 1 < len(prompt) else int(logits.argmax())
        if nxt == ref.EOS:
            break
        tokens.append(nxt)
        text += tok.decode(nxt, token)
        token = nxt

    OUT.write_text(json.dumps({
        "prompt": prompt, "tokens": tokens, "text": text, "first": first,
    }, indent=1), encoding="utf-8")
    print(f"{len(tokens)} tokens -> {text!r}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
