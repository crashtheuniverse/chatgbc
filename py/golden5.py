"""The token sequence the v0.5 ROM must reproduce exactly.

Runs the integer twin in precisely the configuration export5 ships - same
checkpoint, same calibration prompts, same no-repeat decode - and keeps
layer-0 intermediates from the first step so a wrong kernel is located by
layer, not by staring at text.
"""

import json
import re
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


def history(tokens, own):
    """What the no-repeat rule searches: the whole run in a story build (as
    ever), the model's own chosen tokens of the turn in a chat build."""
    return own if export5.CHAT else tokens


def capture_name(line):
    """The engine's capture rule for <SN> (Name_Store, src/name.asm): the last
    run of letters in the player's line, lowercased, its first NAME_MAX
    letters - or None if the line has no letter, and the slot keeps what it
    had. Anything that is not a letter separates words and is dropped, so
    "Vince!", "i'm vince" and "my name is vince." all give "vince", and
    "call me mary ann" gives "ann". It is the rule her training corpus was
    written to: <SN> follows a line only when this is the name. The turn marker and newlines the cartridge stages around the line are
    not letters, so the staged line and the typed one capture the same."""
    words = re.findall(r"[A-Za-z]+", line)
    return words[-1].lower()[:export5.NAME_MAX] if words else None


def speak(tok, st, token, prev, line):
    """What the cartridge prints for `token` - its piece, or for the name
    opcodes the engine's action: <SN> stores capture_name(line) in st.name and
    prints nothing, <N> prints st.name (nothing while it is empty)."""
    ops = export5.name_ops(tok) if export5.CHAT else None
    if ops and token == ops[0]:
        name = capture_name(line)
        if name is not None:
            st.name = name
        return ""
    if ops and token == ops[1]:
        return st.name
    return tok.decode(token, prev)


def chat_turn(q, tok, st, text, first, steps=48, force=(), record=None):
    """One exchange of a conversation on the twin, as the chat ROMs run it.

    `st` carries the recurrent state from turn to turn, and the name slot. The
    first turn is "> text(nl)" behind BOS; a later one is "(nl)> text(nl)" with
    no BOS and no dummy prefix (EncodeCont), its leading newline being the
    token the last reply stopped on. Returns the text of the model-chosen
    tokens only - what the Rei screen puts in her pane - the stop token's
    piece included, and a name opcode expanded as the engine does it (speak).

    The no-repeat rule sees her own tokens of this turn only (`own`), as the
    chat ROMs keep it (wOwnFrom, src/generate.asm): the player's forced line
    is not in it, so she can say their words back. The opcodes are her tokens
    like any other there.

    `force` replaces her first picks with these tokens, as the ROM's test
    hook does (wNameForce, src/name.asm): the model still runs every step, and
    a forced token is hers - history, turn end, what it prints. `record`, a
    list, receives her token ids.
    """
    if first:
        ids = tok.encode("> " + text + "\n")
    else:
        ids = tok.encode("\n> " + text + "\n", bos=False, prefix=False)
    token, own, said, prev = ids[0], [], "", None
    for pos in range(steps):
        logits = twin5.forward_q5(q, st, token)
        forced = pos + 1 < len(ids)
        if forced:
            nxt = ids[pos + 1]
        elif len(own) < len(force):
            nxt = int(force[len(own)])
        else:
            nxt = Q.pick_token(logits, own)
        if nxt == EOS:
            break
        if not forced:
            own.append(nxt)
            said += speak(tok, st, nxt, prev, text)
        prev = token = nxt
        if not forced and nxt <= tok.lookup[b"\n"]:
            break
    if record is not None:
        record.extend(own)
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
    own = []                      # a chat build's no-repeat history (chat_turn)
    for pos in range(STEPS):
        logits = twin5.forward_q5(q, st, token)
        if pos == 0:
            first = {
                "h0": [int(v) for v in st.h[0]],
                "argmax": int(logits.argmax()),
            }
        forced = pos + 1 < len(ids)
        nxt = ids[pos + 1] if forced else Q.pick_token(logits, history(tokens, own))
        if nxt == EOS:
            break
        tokens.append(nxt)
        if not forced:
            own.append(nxt)
        text += tok.decode(nxt, prev) if forced else speak(tok, st, nxt, prev, PROMPT)
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
