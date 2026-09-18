"""The token sequence the v0.5 ROM must reproduce exactly.

Runs the integer twin in precisely the configuration export5 ships - same
checkpoint, same calibration prompts, same no-repeat decode - and keeps
layer-0 intermediates from the first step so a wrong kernel is located by
layer, not by staring at text.
"""

import json
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import export5                    # noqa: E402  (CKPT + cal_prompts)
import twin5                      # noqa: E402
import quant as Q                 # noqa: E402  (pick_token - same decode rule)
from model5 import Model5, Tokenizer, EOS   # noqa: E402

OUT = APP / "build" / "golden.json"
STEPS = 48
PROMPT = export5.PROMPT


def chat_turn(q, tok, st, text, first, steps=48):
    """One exchange of a conversation on the twin, as the chat ROMs run it.

    `st` carries the recurrent state from turn to turn. The first turn is
    "> text(nl)" behind BOS; a later one is "(nl)> text(nl)" with no BOS and no
    dummy prefix (EncodeCont), its leading newline being the token the last
    reply stopped on. Returns the text of the model-chosen tokens only - what
    the Rei screen puts in her pane - the stop token's piece included.
    """
    if first:
        ids = tok.encode("> " + text + "\n")
    else:
        ids = tok.encode("\n> " + text + "\n", bos=False, prefix=False)
    token, tokens, said, prev = ids[0], [], "", None
    for pos in range(steps):
        logits = twin5.forward_q5(q, st, token)
        forced = pos + 1 < len(ids)
        nxt = ids[pos + 1] if forced else Q.pick_token(logits, tokens)
        if nxt == EOS:
            break
        tokens.append(nxt)
        piece = tok.decode(nxt, prev)
        if not forced:
            said += piece
        prev = token = nxt
        if not forced and nxt <= tok.lookup[b"\n"]:
            break
    return said


def main():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    sites = twin5.calibrate5(m, tok, export5.cal_prompts())
    q = twin5.quantize5(m, sites)

    st = twin5.QState5(q.cfg)
    ids = tok.encode(PROMPT)
    token, tokens, text, first = ids[0], [], "", None
    prev = None
    for pos in range(STEPS):
        logits = twin5.forward_q5(q, st, token)
        if pos == 0:
            first = {
                "h0": [int(v) for v in st.h[0]],
                "argmax": int(logits.argmax()),
            }
        forced = pos + 1 < len(ids)
        nxt = ids[pos + 1] if forced else Q.pick_token(logits, tokens)
        if nxt == EOS:
            break
        tokens.append(nxt)
        text += tok.decode(nxt, prev)
        prev = token = nxt
        # A chat ROM ends the turn on the first model-chosen id at or below
        # the newline - unk, BOS, EOS or newline, none ever part of a reply.
        # The golden obeys the same rule, so equality is strict, not a
        # prefix. A story ROM has no turns: it writes until the steps run out.
        if not forced and export5.CHAT and nxt <= tok.lookup[b"\n"]:
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"prompt": ids, "tokens": tokens, "text": text, "first": first},
        indent=1), encoding="utf-8")
    print(f"{len(tokens)} tokens -> {text!r}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
