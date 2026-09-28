"""Find the lines that make Rei muse: the world mode's hidden prompts.

    $env:CHATGBC_CHAT='1'; $env:PIP5=...rei.bin; $env:CHATGBC_TOKENIZER=...tok_rei1024.bin
    python py/rei_muse.py            every candidate, both states
    python py/rei_muse.py --pool     only the lines that pass, as an assembly table

In the world (src/app/rei_world.asm) she sometimes thinks aloud. Today's
checkpoint was never trained to describe a scene, so until the observation
corpus exists a thought is her answer to a hidden line from the distribution
she does know - chosen so that the answer reads as something she might say to
herself. This script does the choosing with the integer twin, the same
arithmetic the cartridge runs: each candidate is asked on a fresh state and on
the state a short conversation leaves, and it passes only if both answers

  * are in her own voice (not a player's line: no leading ">"),
  * end by themselves (the turn ends on a newline inside the token budget),
  * hold no name opcode and no echo (<SN>, <N>, <W>: src/name.asm),
  * are not addressed to anybody: no "you", no "your", no question, no name,
  * fit the thought box (4 rows of 18).

Nothing here is guessed: what the table in the ROM holds is what this printed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export5                    # noqa: E402
import golden5                    # noqa: E402
import twin5                      # noqa: E402
from model5 import Model5, Tokenizer   # noqa: E402
from rei_shots import wrap        # noqa: E402

CANDIDATES = [
    "do you dream", "what did you see", "tell me something", "what do you think",
    "are you happy", "what is the sea", "i am quiet", "what do you like",
    "what is your favourite colour", "what is your favourite food",
    "where do you live", "are you sad", "what do you see", "it is quiet",
    "what is the sun", "do you sleep", "are you alone", "what do you do",
    "tell me a story", "what is your favourite thing", "do you like the sea",
    "it is a nice day", "the sun is warm", "what do you want", "are you small",
    "what are you", "do you remember", "what makes you happy", "is it quiet",
    "do you like it here", "what is it like in there", "the sea is big",
    "i like the sea", "what is outside", "are you tired", "do you think",
    # Rei v1's world has three places, and her corpus talks about them
    "the garden", "the playroom", "where are you", "where are you now", "can you think",
    "what do you know", "who made you", "do you get bored", "is the beach nice",
    "the moon is out", "i see a rainbow", "i see the stars", "the sky is blue",
    "i like the sun", "is it night", "do you fly", "clocks", "starfish", "crabs",
]
WARMUP = ["hello", "my name is tom", "i like chess"]     # the "after a chat" state
BOX_W, BOX_H = 18, 4
ADDRESSED = ("you", "your", "tom", "tell", "hello", "hi", "bye", "hear", "too", "try")

# The pool the ROM carries (src/app/rei_world.asm): chosen by hand from the
# lines that pass, for answers that sound like a thought in her world - the beach,
# the garden, the playroom - and read right on their own. main()
# refuses to print the table if any of them stops passing.
POOL = [
    "do you fly", "where do you live", "the garden", "the playroom", "where are you now",
    "what do you know", "i like the sea", "i like the sun", "tell me a story",
]


def twin():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    return twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts())), tok


def ask(q, tok, line, warm):
    """Her answer to `line`, fresh or after the warm-up, and her token ids."""
    st = twin5.QState5(q.cfg)
    for w in (WARMUP if warm else []):
        golden5.chat_turn(q, tok, st, w, first=(w == WARMUP[0]))
    own = []
    return golden5.chat_turn(q, tok, st, line, first=not warm, record=own), own


def verdict(reply, own, tok):
    text = reply.rstrip("\n")
    if not reply.endswith("\n"):
        return "never ends"
    if text.lstrip().startswith(">") or not text.strip():
        return "not her voice"
    # A name opcode or the echo: <SN> would store the hidden line's last word as
    # the player's name (the world undoes it, but the thought read as a reply),
    # <N> says the player's name or "friend", <W> says the hidden line's word.
    ops = export5.name_ops(tok)
    if ops and set(own) & {*ops, export5.echo_op(tok)}:
        return "an opcode: a name or an echo"
    words = text.replace(".", " ").replace(",", " ").replace("!", " ").split()
    if "?" in text or any(w in ADDRESSED for w in words):
        return "talks to somebody"
    if len(wrap(text, BOX_W)) > BOX_H:
        return "too long for the box"
    return ""


def main():
    if not export5.CHAT:
        sys.exit("set the chat environment first (see the docstring)")
    q, tok = twin()
    pool = []
    for line in CANDIDATES:
        if 0 in tok.encode("> " + line + "\n"):
            print(f"  --  {line!r}: has an unknown piece")
            continue
        asked = [ask(q, tok, line, warm) for warm in (False, True)]
        replies = [r for r, _ in asked]
        why = [verdict(r, own, tok) for r, own in asked]
        ok = not any(why)
        if ok:
            pool.append((line, replies))
        if "--pool" not in sys.argv:
            print(f"{'KEEP' if ok else '  --'}  {line!r}")
            for r, w, state in zip(replies, why, ("fresh", "after a chat")):
                print(f"          {state:13} {r!r}" + (f"   <- {w}" if w else ""))
    passed = dict(pool)
    missing = [line for line in POOL if line not in passed]
    assert not missing, f"no longer musing: {missing}"
    print()
    print("; What she says to each (py/rei_muse.py: fresh state / after a chat):")
    for line in POOL:
        a, b = (r.rstrip(chr(10)) for r in passed[line])
        print(f';   "{line}"')
        print(f";       {a}" + (f"  /  {b}" if b != a else ""))
    for i, line in enumerate(POOL):
        print(f'.m{i}: db "{line}", 0')


if __name__ == "__main__":
    main()
