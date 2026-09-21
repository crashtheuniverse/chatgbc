"""What the Rei suites share: the twin, and a ROM in conversation with it."""
import pytest

import export5                    # noqa: E402
import golden5                    # noqa: E402
import rei_shots as ui            # noqa: E402
import rei_topics                 # noqa: E402
import twin5                      # noqa: E402
from conftest import APP
from model5 import Model5, Tokenizer   # noqa: E402


@pytest.fixture(scope="module")
def twin():
    m = Model5(export5.CKPT)
    tok = Tokenizer()
    return twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts())), tok


class Talk:
    """A ROM and the twin, in the same conversation."""

    def __init__(self, twin, sram=None):
        self.rom = ui.boot(sram)
        self.q, self.tok = twin
        self.st = twin5.QState5(self.q.cfg)
        self.said = []            # the twin's replies, newline stripped
        self.lines = []           # the whole conversation, for the log: (who, text)

    def expect(self, text):
        """The twin's reply to `text`, which the ROM is about to be sent."""
        reply = golden5.chat_turn(self.q, self.tok, self.st, text, first=not self.said)
        self.said.append(reply.rstrip("\n"))
        self.lines += [(1, text), (0, self.said[-1])]
        return self.said[-1]

    def rom_reply(self):
        n = self.rom.read("wReiReplyLen")[0]
        return bytes(self.rom.read("wReiReply", n)).decode("ascii")

    def send(self, topic, line):
        """Through the topic tree: sentence `line` of topic `topic`, sent with A
        and answered; the reply checked against the twin's."""
        r = self.rom
        ui.choose(r, topic, line)
        text = rei_topics.TOPICS[topic][1][line]
        assert ui.row_text(r, 10, 1, 19).rstrip() == text, "the prompt row shows what A sends"
        want = self.expect(text)
        ui.press(r, "a", after=0)
        ui.wait_ready(r)
        assert self.rom_reply() == want
        assert ui.pane(r) == ui.layout(want)
        return want
