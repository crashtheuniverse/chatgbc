"""The ROM's BPE encoder must agree with the tokenizer the model was trained on.

Byte-level fallback alone would be valid tokens but the wrong ones: the model
saw merged pieces during training, so "Once" must encode as one token, not four.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reference as ref  # noqa: E402


def rom_tokens(rom):
    n = rom.read("wTokCount")[0]
    raw = rom.read("wTokBuf", n * 2)
    return [int.from_bytes(raw[i * 2 : i * 2 + 2], "little") for i in range(n)]


def test_encodes_like_the_reference(rom):
    want = ref.Tokenizer().encode("Once upon a time")
    assert rom_tokens(rom) == want


def test_merges_actually_happened(rom):
    """Guards the merge loop specifically: without it the encoder would emit one
    token per character and still look plausible."""
    assert len(rom_tokens(rom)) < len("Once upon a time")
