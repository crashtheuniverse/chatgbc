"""The tokens a Rei cartridge feeds for one player turn - the one definition
the ROM, the twin and a corpus packer must agree on.

    import sys; sys.path.insert(0, "C:/crashcode/chatgbc/py")
    from header import header_tokens
    header_tokens(prev_reply_ended=True, name_known=True, player_line="what is my name")
    # -> [3, 1021, 16, 4, ...]   newline, <NK>, ">", " ", the line, newline

A turn is staged by Chat_Stage (src/stage.asm) and encoded by src/encoder.asm,
then Name_Header (src/name.asm) puts the header in:

  first turn     BOS  [<NK>]  " > line"  newline
                 (Encode: BOS, llama2.c's dummy space, the staged "> line\\n")
  continuation   newline  [<NK>]  "> line"  newline
                 (EncodeCont on "\\n> line\\n": the newline is the token her
                 previous reply stopped on, fed as this run's first token)

<NK> (id 1021 of models/tok_rei1024.bin) is there exactly when the engine's
name slot holds a name - after BOS or after that newline, before everything
the line encodes to (on a first turn, before the dummy space too). Nothing
merges across it: no piece of the tokenizer joins BOS or the newline to
anything, so the ids are the same as encoding the line apart, which is how a
packer encodes lines (pack4: BOS, each line encoded alone, the first with the
dummy space, joined by the newline token). So a conversation's stream is

    header_tokens(False, k0, p0) + reply0 + header_tokens(True, k1, p1) + reply1 + ...

where reply_i is her line's ids WITHOUT its closing newline (that newline is
the first id of the next header_tokens) and k_i says whether the slot held a
name when turn i was staged.

`player_line` is what the player typed: no "> " (the stage adds it) and no
newline. Nothing typable reaches ids 1016-1023 (py/tests/test_rei_header.py
fuzzes it).
"""

import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference as ref          # noqa: E402  (Tokenizer, BOS)

TOKENIZER = Path(__file__).resolve().parents[1] / "models" / "tok_rei1024.bin"
HEADER_PIECE = b"<NK>"


@lru_cache(maxsize=None)
def _tok(path):
    return ref.Tokenizer(Path(path))


def header_tokens(prev_reply_ended, name_known, player_line, tok=None):
    """The exact ids the ROM feeds for one player turn (see the module text).

    prev_reply_ended: False on the conversation's first turn (BOS and the
    dummy space), True on every later one (the newline her reply ended on
    comes first). name_known: the engine's name slot is not empty. tok: a
    reference.Tokenizer, default models/tok_rei1024.bin."""
    tok = tok or _tok(str(TOKENIZER))
    if player_line.startswith(">") or "\n" in player_line:
        raise ValueError(f"the typed line, without the turn marker or a newline: {player_line!r}")
    if prev_reply_ended:
        ids = tok.encode("\n> " + player_line + "\n", bos=False, prefix=False)
    else:
        ids = tok.encode("> " + player_line + "\n")
    if name_known:
        nk = tok.lookup.get(HEADER_PIECE)
        if nk is None:
            raise ValueError("this tokenizer has no <NK>: no header")
        ids.insert(1, nk)
    return ids
