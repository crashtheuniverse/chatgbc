"""The topic tree: what the player can say to Rei without the keyboard.

    $env:CHATGBC_CHAT='1'; $env:PIP5=...rei.bin; $env:CHATGBC_TOKENIZER=...tok_rei.bin
    python py/rei_topics.py            every line asked of the twin, fresh and mid-chat
    python py/rei_topics.py --emit     src/rei_topics.inc, the table the ROM carries

Ten topics in a grid of two by five, up to ten sentences each, five to a page.
Every sentence is a line her corpus taught her to answer (lower case, no
question mark: that is how the corpus writes the player), fits the prompt row,
and encodes without an unknown piece. The twin answers each one here so the
list can be read before it is shipped; --emit refuses a line that fails. With
REI_CORPUS set to her training text, a reply holding a word she was never
taught (a garbled one) fails too.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "src" / "rei_topics.inc"
TOPIC_W = 8                       # a topic's name, in the grid
LINE_W = 18                       # the prompt row
PAGE = 5

TOPICS = [
    ("hello", ["hello", "hi there", "good morning", "hey", "how are you",
               "are you ok", "how do you feel", "can you see me"]),
    ("me", ["my name is tom", "call me ruby", "what is my name", "who am i",
            "i love chess", "i like tag best", "i love gold", "what do i like"]),
    ("rei", ["what is your name", "who are you", "where do you live", "where are you",
             "who made you", "are you real", "are you a robot", "are you alive",
             "do you dream", "can you think"]),
    ("feeling", ["i am so happy", "i am proud", "i feel excited", "i am a bit sad",
                 "i feel lonely", "i am scared", "i am tired", "i feel cold",
                 "i feel better now", "i am ok now"]),
    ("sky", ["how is the weather", "the day is sunny", "the day is rainy",
             "the day is windy", "it is cold today", "the day is warm",
             "is it dark outside", "is it night", "what can you see", "do you sleep"]),
    ("play", ["can we play", "let us play chess", "let us play tag", "let us play cards",
              "let us play catch", "can you run", "can you sing", "tell me a story",
              "say something nice", "can you help me"]),
    ("food", ["do you like cake", "do you like pie", "what about honey", "what about soup",
              "what about jam", "what about rice", "what about bread", "what about peach",
              "what about plum", "what about milk"]),
    ("animals", ["do you like cats", "what about dogs", "what about birds", "what about frogs",
                 "do you like bears", "what about owls", "do you like fishes", "what about pigs"]),
    ("things", ["what about books", "what about boats", "what about kites", "what about bells",
                "what about balls", "what about hats", "do you like rocks",
                "what about cups", "do you like keys", "what about socks"]),
    ("kind", ["thank you", "that is kind", "sorry", "i am sorry", "i did not mean it",
              "i have to go", "see you", "goodbye", "bye"]),
]
WARMUP = ["hello", "my name is tom"]


def check_shape():
    assert len(TOPICS) == 10
    for name, lines in TOPICS:
        assert len(name) <= TOPIC_W, name
        assert 1 <= len(lines) <= 2 * PAGE, name
        for s in lines:
            assert s == s.lower() and len(s) <= LINE_W and "?" not in s, s


def ask_all():
    import export5, golden5, twin5
    from model5 import Model5, Tokenizer
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    q = twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts()))
    bad = []
    known = None
    if os.environ.get("REI_CORPUS"):             # her own lines: every word she says must be one of theirs
        known = {"rei"}                          # the corpus calls her by her lab name
        for l in open(os.environ["REI_CORPUS"], encoding="utf-8"):
            if not l.startswith(">"):
                known.update(re.findall(r"[a-z]+", l))
    for name, lines in TOPICS:
        print(f"== {name}")
        for s in lines:
            if 0 in tok.encode("> " + s + "\n"):
                bad.append((s, "unknown piece"))
            out = []
            for warm in (False, True):
                st = twin5.QState5(q.cfg)
                for w in (WARMUP if warm else []):
                    golden5.chat_turn(q, tok, st, w, first=(w == WARMUP[0]))
                r = golden5.chat_turn(q, tok, st, s, first=not warm)
                if not r.endswith("\n") or r.lstrip().startswith(">") or not r.strip():
                    bad.append((s, repr(r)))
                elif known and not set(re.findall(r"[a-z]+", r)) <= known:
                    bad.append((s, "not her words: " + r.strip()))
                out.append(r.rstrip("\n"))
            print(f"  {s:<{LINE_W}} | {out[0]}\n  {'':<{LINE_W}} | {out[1]}")
    return bad


def emit():
    o = ["; Generated by py/rei_topics.py - do not edit.",
         "; The topic tree: ReiTopicNames is TOPIC_COUNT names of TOPIC_W bytes, space",
         "; padded; ReiTopicLists is a pointer per topic to its sentences, each ending",
         "; in 0, the list ending in a second 0; ReiTopicCounts is how many there are.",
         "",
         f"DEF TOPIC_COUNT EQU {len(TOPICS)}",
         f"DEF TOPIC_W EQU {TOPIC_W}",
         f"DEF TOPIC_PAGE EQU {PAGE}",
         "",
         "ReiTopicNames::"]
    for name, _ in TOPICS:
        o.append(f'    db "{name:<{TOPIC_W}}"')
    o += ["", "ReiTopicCounts::", "    db " + ",".join(str(len(l)) for _, l in TOPICS), "",
          "ReiTopicLists::"]
    for i in range(len(TOPICS)):
        o.append(f"    dw .t{i}")
    for i, (name, lines) in enumerate(TOPICS):
        o.append(f".t{i} ; {name}")
        for s in lines:
            o.append(f'    db "{s}", 0')
        o.append("    db 0")
    o.append("")
    DST.write_text("\n".join(o), encoding="utf-8", newline="\n")
    print("wrote", DST)


if __name__ == "__main__":
    check_shape()
    if "--emit" in sys.argv:
        bad = ask_all() if "--unchecked" not in sys.argv else []
        assert not bad, bad
        emit()
    else:
        for s, why in ask_all():
            print("FAILS:", s, why)
