"""What the Rei suites share: the twin, and a ROM in conversation with it."""
import hashlib

import pytest

import export5                    # noqa: E402
import golden5                    # noqa: E402
import harness                    # noqa: E402
import rei_shots as ui            # noqa: E402
import rei_topics                 # noqa: E402
import twin5                      # noqa: E402
from conftest import APP
from model5 import Model5, Tokenizer   # noqa: E402

# What a model SAYS - that she greets as "rei", that she names "tom" back,
# that she echoes "ducks" - is a statement about one checkpoint, measured on
# it: models/rei.bin as of v1.0.0. For any other checkpoint the suites still
# hold the ROM to the twin word for word, the contract, and leave those
# statements out until they are measured on it.
MEASURED = {"ab88a858d0a61619742dc4567ca0fb030287eef4201ee9df7ddca60248298388"}


def measured():
    """True if the exported checkpoint is one the suites' words were measured on."""
    return hashlib.sha256(export5.CKPT.read_bytes()).hexdigest() in MEASURED


NAME = harness.load_defs(APP / "src" / "model.inc", APP / "src" / "name.asm")


@pytest.fixture(scope="module")
def twin():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    return twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts())), tok


def force(r, tokens):
    """The ROM's test hook (wNameForce, src/name.asm): her next picks are
    `tokens`, whatever the classifier says - golden5.chat_turn's `force`."""
    tokens = list(tokens)
    assert len(tokens) <= NAME["NAME_FORCE_MAX"]
    raw = [b for t in tokens for b in (t & 0xFF, t >> 8)]
    if raw:
        at = r.addr("wNameForceBuf")
        r.pyboy.memory[at:at + len(raw)] = raw
    r.pyboy.memory[r.addr("wNameForceI")] = 0
    r.pyboy.memory[r.addr("wNameForceN")] = len(tokens)


def slot(name):
    """The bytes wName holds for `name`: its letters, zero-padded."""
    return name.encode("ascii").ljust(NAME["NAME_MAX"], b"\0")


class Talk:
    """A ROM and the twin, in the same conversation."""

    def __init__(self, twin, sram=None):
        self.rom = ui.boot(sram)
        self.q, self.tok = twin
        self.st = twin5.QState5(self.q.cfg)
        self.said = []            # the twin's replies, newline stripped
        self.lines = []           # the whole conversation, for the log: (who, text)

    def expect(self, text, forced=()):
        """The twin's reply to `text`, which the ROM is about to be sent; with
        `forced`, her first picks (the ROM's hook has to be given the same)."""
        reply = golden5.chat_turn(self.q, self.tok, self.st, text, first=not self.said,
                                  force=forced)
        self.said.append(reply.rstrip("\n"))
        self.lines += [(1, text), (0, self.said[-1])]
        return self.said[-1]

    def rom_reply(self):
        n = self.rom.read("wReiReplyLen")[0]
        return bytes(self.rom.read("wReiReply", n)).decode("ascii") if n else ""

    def send(self, topic, line, forced=()):
        """Through the topic tree: sentence `line` of topic `topic`, sent with A
        and answered; the reply checked against the twin's."""
        r = self.rom
        ui.choose(r, topic, line)
        text = rei_topics.TOPICS[topic][1][line]
        assert ui.row_text(r, 10, 1, 19).rstrip() == text, "the prompt row shows what A sends"
        want = self.expect(text, forced)
        if forced:
            force(r, forced)
        ui.press(r, "a", after=0)
        ui.wait_ready(r)
        assert self.rom_reply() == want
        assert ui.pane(r) == ui.layout(want)
        return want
