"""The capture rule of the name opcode <SN>, on its own: what the engine
stores when she chooses to remember the player's name (golden5.capture_name,
which the twin uses and src/name.asm's Name_Store implements; the ROM is held
to it in test_rei_name.py). The echo <W> says the same word
(golden5.last_word: one function, Name_LastWord in the ROM). Pure Python, so
it runs in every suite."""
import golden5                    # noqa: E402

# (the player's line, what <SN> stores; None = the slot keeps what it had)
CASES = [
    ("vince", "vince"),
    ("Vince!", "vince"),
    ("i'm vince", "vince"),
    ("my name is vince.", "vince"),
    ("call me mary ann", "ann"),
    ("it is VINCE?!", "vince"),
    ("'vince'", "vince"),
    ("vince, ok", "ok"),
    ("mary-ann", "ann"),
    ("a", "a"),
    ("abcdefghijkl", "abcdefghijkl"),                   # twelve: all of it
    ("abcdefghijklm", "abcdefghijkl"),                  # thirteen: cut to twelve
    ("my name is bartholomewxyz", "bartholomewx"),
    ("", None),
    ("   ", None),
    ("?!", None),
    (".,!?'-;:", None),
]


def test_no_line_of_the_tree_gives_a_name():
    """The player types their own name: the topic tree (and the candidate
    pool its lines are reviewed from) offers none, and "me" asks for it back
    instead - what the name opcode <N> answers."""
    import rei_topics
    import rei_topics_review
    rei_topics.check_shape()
    tree = [s for _, lines in rei_topics.TOPICS for s in lines]
    assert not [s for s in tree if rei_topics.gives_a_name(s)]
    for line in ("my name is tom", "call me ruby", "i am called bo", "i'm adele", "i am vince",
                 "they call me max", "my name's ann"):
        assert rei_topics.gives_a_name(line), line
    for line in ("what is my name", "i am tired", "i am so happy", "say my name"):
        assert not rei_topics.gives_a_name(line), line
    me = dict(rei_topics.TOPICS)["me"]
    assert {"what is my name", "who am i", "do you remember me", "say my name"} <= set(me)
    pool = rei_topics_review.read_pool()
    assert {t for t, _, _ in pool} == {name for name, _ in rei_topics.TOPICS}
    assert not [s for _, s, _ in pool if rei_topics.gives_a_name(s)]
    assert all(len(s) <= rei_topics.LINE_W and s == s.lower() and "?" not in s
               for _, s, _ in pool)


def test_the_capture_rule():
    assert golden5.capture_name is golden5.last_word, "<SN> and <W> share the rule"
    for line, want in CASES:
        assert golden5.capture_name(line) == want, line
        # what the cartridge stages around the line changes nothing
        assert golden5.capture_name("\n> " + line + "\n") == want, line
