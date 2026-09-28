"""The topic tree: what the player can say to Rei without the keyboard.

    $env:CHATGBC_CHAT='1'; $env:PIP5=...rei.bin; $env:CHATGBC_TOKENIZER=...tok_rei.bin
    python py/rei_topics.py            every line asked of the twin, fresh and mid-chat
    python py/rei_topics.py --emit     src/rei_topics.inc, the table the ROM carries

Ten topics in a grid of two by five, up to ten sentences each, five to a page.
Every sentence is a line her corpus taught her to answer (lower case, no
question mark: that is how the corpus writes the player), fits the prompt row,
and encodes without an unknown piece. None gives a name (gives_a_name): the
player types their own on the keyboard, and "me" asks for it back instead
("what is my name", "who am i", ...), which is the name opcode's <N>. The twin answers each one here so the
list can be read before it is shipped - in the four conversations of the sense
review (py/rei_topics_review.py) - and --emit refuses a line that fails the
word check there: one that makes her store a name, say, or with REI_CORPUS
set to her training text, a reply holding a word she was never taught (a
garbled one). Sense is not a check a script can make: the lines were chosen
by reading her answers (docs/review/).
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

# Rei v1's tree (rei_v1c), from the sense review in docs/review/topics_rei_v1c.md:
# every line is one a reviewer read her four answers to (fresh, fresh with a
# name kept, mid-chat, mid-chat with a name) and found on topic, fluent and
# unbroken in all of them - which ruled out most "do you like X" lines (she
# echoes X, then a fact about something else: "cats! yes! a baby panda...")
# and kept the forms she answers well ("i like X" -> "X! good choice.").
TOPICS = [
    ("hello", ["hello", "hi there", "hey", "good morning", "good evening",
               "how are you", "are you ok", "how do you feel", "can you see me", "i am back"]),
    ("me", ["what is my name", "who am i", "what am i called", "do you remember me",
            "say my name", "i love chess", "i love gold", "i like balls", "i like starfish",
            "i like pizza"]),
    ("rei", ["where do you live", "who made you", "are you a person", "are you a robot",
             "can you think", "do you dream", "what do you know", "do you get bored",
             "can you hear me", "will you miss me"]),
    ("feeling", ["i am so happy", "i am excited", "i am proud", "i am fine", "i feel ok",
                 "i feel better now", "i feel good", "very happy", "i am bored",
                 "my day was bad"]),
    ("sky", ["it is sunny today", "is it sunny", "it is a nice day", "the sky is blue",
             "i like the sun", "i see a rainbow", "i see the stars", "the moon is out",
             "is it night", "where are you"]),
    ("play", ["can we play", "play with me", "let us play tag", "let us play chess",
              "let us play i spy", "tell me a story", "story time", "tell me a joke",
              "ask me a question", "talk to me"]),
    ("food", ["what do you eat", "what about soup", "what about cookies", "do you like peas",
              "i like apples", "i like bread", "i like cheese", "i like pears", "i like rice",
              "i like tea"]),
    ("animals", ["do you like horses", "what about crabs", "what about zebras", "i have a cat",
                 "i love cats", "i love bunnies", "i like birds", "i like ducks", "i like owls",
                 "i like penguins"]),
    ("things", ["do you have toys", "the playroom", "do you like books", "what about books",
                "do you like clocks", "what about clocks", "i like drums", "i like trains",
                "i love blue"]),
    ("kind", ["bye", "bye bye", "goodbye", "i have to go", "good night", "you are funny",
              "you are lovely", "you are my friend", "i like you a lot", "you are weird"]),
]
# A warm-up that gives her the name "tom". The player types a name on the
# keyboard: no line of the tree gives one (NAME_GIVING), so this one is typed.
WARMUP = ["hello", "my name is tom"]

# A line that tells her a name. The player's own name is theirs to type, and a
# tree line that gave one ("my name is tom") would name every player alike:
# the name opcode stores the last word of what was sent (src/name.asm).
# "i am X" with one word X is a name unless X is a state ("i am tired"): the
# corpus answers her name question with "i'm adele" as often as with a phrase.
NAME_GIVING = re.compile(r"\b(my name is|my name's|call me|i am called|i'm called|"
                         r"they call me|name is)\b")
I_AM = re.compile(r"^(?:i am|i'm|im) ([a-z]+)$")
STATES = {"back", "bored", "cold", "excited", "fine", "good", "great", "happy", "hot",
          "hungry", "lonely", "nervous", "ok", "proud", "sad", "scared", "sick", "sleepy",
          "sorry", "tired", "well", "worried"}


def gives_a_name(line):
    m = I_AM.match(line)
    return bool(NAME_GIVING.search(line)) or bool(m and m.group(1) not in STATES)


def check_shape():
    assert len(TOPICS) == 10
    for name, lines in TOPICS:
        assert len(name) <= TOPIC_W, name
        assert 1 <= len(lines) <= 2 * PAGE, name
        for s in lines:
            assert s == s.lower() and len(s) <= LINE_W and "?" not in s, s
            assert not gives_a_name(s), f"{s!r} gives a name: the player types their own"
    every = [s for _, lines in TOPICS for s in lines]
    assert len(every) == len(set(every)), "a line twice"


def ask_all():
    """Every line asked of the twin in the sense review's four conversations
    (py/rei_topics_review.py: fresh, fresh+name, chat, chat+name) with its word
    check - an unknown piece, a stored name, an empty or endless reply, the
    player's voice, an opcode; with REI_CORPUS (her training text, a file or a
    directory of them) a word she was never taught. Returns the failures."""
    import export5, twin5
    import rei_topics_review as review
    from model5 import Model5, Tokenizer
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    q = twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts()))
    known = review.corpus_words([os.environ["REI_CORPUS"]]) if os.environ.get("REI_CORPUS") else None
    start, _ = review.conversations(q, tok)
    bad = []
    for name, lines in TOPICS:
        print(f"== {name}")
        for s in lines:
            replies, fails = review.ask(q, tok, start, s, known)
            bad += [(s, why) for why in fails]
            for i, cond in enumerate(review.CONDITIONS):
                print(f"  {s if i == 0 else '':<{LINE_W}} | {cond:<10} | {replies[cond]}")
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
