"""The capture rule of the name opcode <SN>, on its own: what the engine
stores when she chooses to remember the player's name (golden5.capture_name,
which the twin uses and src/name.asm's Name_Store implements; the ROM is held
to it in test_rei_name.py). Pure Python, so it runs in every suite."""
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


def test_the_capture_rule():
    for line, want in CASES:
        assert golden5.capture_name(line) == want, line
        # what the cartridge stages around the line changes nothing
        assert golden5.capture_name("\n> " + line + "\n") == want, line
