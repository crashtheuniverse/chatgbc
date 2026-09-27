"""The header: while the engine holds the player's name, every player turn
starts with <NK> (src/name.asm Name_Header; py/header.py is the rule).

Two halves. The tokenizer's (every suite): models/tok_rei1024.bin (v3: v2
with id 1016 named <W>, the echo) keeps ids 1016-1023 for the engine, nothing typable reaches them, and no piece joins
her reply's closing newline (or BOS) to the "> " of the next line, so the
header has a place between them and a turn encoded in one piece is the same
ids as its lines encoded apart, as a corpus packer does. The ROM's (a chat
export): the lab's LAB_GO_STAGE runs Chat_Stage, the encoder and the header on
a typed line and its tokens are golden5.staged_ids' - first turn and
continuation, slot empty and holding a name. With a tokenizer that has no
<NK> (v1.0.0's 512-piece Rei) the header is not assembled and the staged
turns are the ones before it.
"""
import random
import re
from pathlib import Path

import pytest

import export5                    # noqa: E402
import golden5                    # noqa: E402
import harness                    # noqa: E402
import header                     # noqa: E402
import reference as ref           # noqa: E402
from conftest import APP, lab_rom

REI1024 = APP / "models" / "tok_rei1024.bin"
REI512 = APP / "models" / "tok_rei.bin"
# v3 (2026-09-28): v2 with its <R0> renamed <W> - the echo opcode
# (src/name.asm Name_Echo); nothing else changed.
RESERVED = [b"<W>", b"<R1>", b"<R2>", b"<R3>", b"<R4>", b"<NK>", b"<SN>", b"<N>"]
# The six merges v2 gave up for them: tok_rei1024 v1's last six (ids
# 1016-1021), each used ~17,900 times on the friend5 mix (0.11% of its
# tokens together). Only two merges were cheaper to drop ("gs", ".."), and
# they sit mid-table, where dropping them would have renumbered 441 ids.
DROPPED = [b" windy", b"time", b" please", b"ows", b"anket", b" feet"]
REI_KEYS = "abcdefghijklmnopqrstuvwxyz .,!?'-;:"          # src/app/rei_input.asm


def tok1024():
    return ref.Tokenizer(REI1024)


def cartridge_lines():
    """Every line the cartridge sends by itself: the topic tree, the warm-up
    and the world's thoughts."""
    import rei_topics
    lines = [s for _, ls in rei_topics.TOPICS for s in ls] + list(rei_topics.WARMUP)
    world = (APP / "src" / "app" / "rei_world.asm").read_text(encoding="utf-8")
    return lines + re.findall(r'^\.m\d+:\s+db "([^"]*)"', world, flags=re.M)


# --- the tokenizer -----------------------------------------------------------

def test_v3_is_v1_with_the_engine_ids():
    """ids 0-1015 are v1's in order (0-511 tok_rei.bin's), 1016-1023 the
    engine's (v3's <W> at 1016); the dropped merges are gone and nothing else
    is."""
    tok, small = tok1024(), ref.Tokenizer(REI512)
    assert len(tok.vocab) == 1024
    assert tok.vocab[:512] == small.vocab and tok.scores[:512] == small.scores
    assert tok.vocab[1016:] == RESERVED
    assert not set(DROPPED) & set(tok.vocab)
    assert max(tok.scores[1016:]) < min(tok.scores[3:1016]), "below every merge"
    assert len(set(tok.vocab)) == 1024
    assert header.header_tokens(True, True, "hi", tok)[1] == 1021


def test_nothing_joins_the_newline_or_the_marker():
    """The only piece holding a newline is the newline, the only one holding
    ">" is ">", and no piece starts with "<" but the specials and the engine's
    - and "<" itself is no piece. So a merge can never span "(nl)" and ">",
    and the encoder, which only ever joins two pieces into their
    concatenation, can never reach an id that starts with "<"."""
    tok = tok1024()
    nl, gt = tok.lookup[b"\n"], tok.lookup[b">"]
    assert [i for i, p in enumerate(tok.vocab) if b"\n" in p] == [nl]
    assert [i for i, p in enumerate(tok.vocab) if b">" in p and i > 2] == [gt] + list(range(1016, 1024))
    assert b"<" not in tok.lookup
    starts = [i for i, p in enumerate(tok.vocab) if p.startswith(b"<")]
    assert starts == [0, 1, 2] + list(range(1016, 1024))
    assert tok.encode("\n>", bos=False, prefix=False) == [nl, gt]


def test_no_typed_line_reaches_the_engine_ids():
    """Fuzz: random lines over every printable character (the cartridge's keys
    and more: capitals, digits, "<", ">"), the cartridge's own lines, each
    staged as a first turn and as a continuation."""
    tok = tok1024()
    rng = random.Random(1016)
    printable = "".join(chr(c) for c in range(32, 127))
    lines = cartridge_lines()
    lines += ["".join(rng.choice(REI_KEYS) for _ in range(rng.randint(1, 44))) for _ in range(4000)]
    lines += ["".join(rng.choice(printable) for _ in range(rng.randint(1, 44))) for _ in range(2000)]
    lines += ["<NK>", "<SN> <N>", "<R0><R4>", "a<NK>b", "> <NK>", "<W>", "cats <W>"]
    for line in lines:
        for ids in (tok.encode("> " + line + "\n"),
                    tok.encode("\n> " + line + "\n", bos=False, prefix=False)):
            assert max(ids) < 1016, line


def test_header_tokens_is_the_packers_stream():
    """header_tokens = the turn's lines encoded apart, the header between: BOS
    (or the newline her reply ended on), <NK> if the name is known, the line
    (with llama2.c's dummy space on a first turn), the newline."""
    tok = tok1024()
    nl, nk = tok.lookup[b"\n"], tok.lookup[b"<NK>"]
    rng = random.Random(21)
    lines = cartridge_lines() + ["".join(rng.choice(REI_KEYS) for _ in range(rng.randint(1, 44)))
                                 for _ in range(500)]
    for line in lines:
        for known in (False, True):
            h = [nk] if known else []
            first = [ref.BOS] + h + tok.encode("> " + line, bos=False, prefix=True) + [nl]
            cont = [nl] + h + tok.encode("> " + line, bos=False, prefix=False) + [nl]
            assert header.header_tokens(False, known, line, tok) == first, line
            assert header.header_tokens(True, known, line, tok) == cont, line


def test_header_tokens_examples():
    tok = tok1024()
    ids = lambda s: [tok.lookup[p.encode()] for p in s]              # noqa: E731
    assert header.header_tokens(True, True, "hi", tok) == ids(["\n", "<NK>", ">", " hi", "\n"])
    assert header.header_tokens(True, False, "hi", tok) == ids(["\n", ">", " hi", "\n"])
    assert header.header_tokens(False, True, "hi", tok) == [ref.BOS] + ids(["<NK>", " ", ">", " hi", "\n"])
    assert header.header_tokens(False, False, "hi", tok) == [ref.BOS] + ids([" ", ">", " hi", "\n"])
    for bad in ("> hi", "hi\n"):
        with pytest.raises(ValueError):
            header.header_tokens(True, True, bad, tok)
    with pytest.raises(ValueError):
        header.header_tokens(True, True, "hi", ref.Tokenizer(REI512))


# --- the ROM -----------------------------------------------------------------

DEFS = harness.load_defs(APP / "src" / "chatgbc.inc", APP / "src" / "model.inc")
chat = pytest.mark.skipif(not export5.CHAT, reason="the staged turn is a chat build's")


@pytest.fixture(scope="module")
def lab():
    r = lab_rom()
    yield r
    r.close()


def lab_stage(r, text, started, name):
    """LAB_GO_STAGE: `text` typed, wChatStarted = started, the slot holding
    `name` (a build with the name opcodes). Returns wTokBuf's tokens."""
    raw = text.encode("ascii")
    idle, state, go = r.defs["LAB_IDLE"], r.addr("wLabState"), r.addr("wLabGo")
    r.pyboy.memory[go] = 0
    r._tick_until(lambda: r.pyboy.memory[state] == idle, 2000, "lab idle")
    base = r.addr("wPromptText")
    if raw:
        r.pyboy.memory[base:base + len(raw)] = list(raw)
    r.pyboy.memory[r.addr("wPromptLen")] = len(raw)
    r.pyboy.memory[r.addr("wChatStarted")] = started
    if "NAME_OPS" in DEFS:
        at, n = r.addr("wName"), DEFS["NAME_MAX"]
        r.pyboy.memory[at:at + n] = list(name.encode("ascii").ljust(n, b"\0"))
    else:
        assert not name
    ready = r.addr("wReady")
    r.pyboy.memory[ready] = 0
    r.pyboy.memory[go] = DEFS["LAB_GO_STAGE"]
    r._tick_until(lambda: r.pyboy.memory[ready] == r.defs["READY_MAGIC"], 3000, "stage")
    r.pyboy.memory[go] = 0
    n = r.read("wTokCount")[0]
    buf = r.read("wTokBuf", 2 * n)
    return [buf[2 * i] | (buf[2 * i + 1] << 8) for i in range(n)]


@chat
def test_the_rom_stages_the_twins_turns(lab):
    """First turn and continuation, slot empty and holding a name: the ROM's
    tokens are golden5.staged_ids'. The longest line the keyboard allows
    (PROMPT_MAX - 4) is among them, so the header's slot always fits."""
    from model5 import Tokenizer
    tok = Tokenizer()
    names = [""] + (["tom", "bartholomewx"] if "NAME_OPS" in DEFS else [])
    rng = random.Random(5)
    longest = DEFS["PROMPT_MAX"] - 4
    lines = ["my name is tom", "what is my name", "hi", "x" * longest, "a " * (longest // 2)]
    lines += rng.sample(cartridge_lines(), 12)
    lines += ["".join(rng.choice(REI_KEYS) for _ in range(rng.randint(1, longest))) for _ in range(12)]
    with_header = 0
    for line in lines:
        for started in (0, 1):
            for name in names:
                want = golden5.staged_ids(tok, line, not started, name)
                assert lab_stage(lab, line, started, name) == want, (line, started, name)
                with_header += export5.header_op(tok) in want
    if export5.header_op(tok) is not None and "NAME_OPS" in DEFS:
        assert "TOK_NK" in DEFS and DEFS["TOK_NK"] == export5.header_op(tok)
        assert with_header == len(lines) * 2 * (len(names) - 1)
    else:
        assert "TOK_NK" not in DEFS and with_header == 0


@chat
def test_the_header_prints_nothing():
    """A model that picks <NK> or a register says nothing with it: its piece
    is empty in the ROM's detokenizer, as golden5.speak has it."""
    from model5 import Tokenizer
    tok = Tokenizer()
    if export5.header_op(tok) is None:
        pytest.skip("this tokenizer has no header")
    blob = (APP / "build" / "blobs" / "vocab_data.bin").read_bytes()
    for t in export5.silent_ids(tok):
        at = int.from_bytes(blob[2 * t:2 * t + 2], "little")
        assert blob[at] == 0, t
    assert sorted(export5.silent_ids(tok)) == list(range(1016, 1024))
