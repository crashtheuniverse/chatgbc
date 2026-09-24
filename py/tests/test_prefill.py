"""Fast prefill changes how long the wait is, not a single bit of what she says.

A chat ROM runs a forced prompt token's forward pass only as far as the last
layer's state update (src/forward.asm, wSkipTail): its argmax would be thrown
away. wPrefillFull, a byte the harness can set, puts the whole pass back, so
the two can be compared on one ROM: the recurrent state after the prompt, and
the reply after it, must be identical - and the prompt must be cheaper.
"""
import pytest

import export5                    # noqa: E402
from conftest import lab_rom

if not export5.CHAT:
    pytest.skip("only a chat ROM prefills", allow_module_level=True)

PROMPTS = [export5.PROMPT, "> let us play chess\n", "> my favourite colour is blue\n"]


def run(prompt, steps, full):
    r = lab_rom()
    r.pyboy.tick(400, False)
    r.pyboy.memory[r.addr("wPrefillFull")] = full
    r.lab_run(steps=steps, prompt=prompt)
    n = r.read("wGenCount")[0]
    out = {
        "h": bytes(r.read("wH", 3 * 64)),
        "tokens": bytes(r.read("wOutTokens", 2 * n)),
        "prompt": r.read("wTokCount")[0],
        "prefill": r.read_u32("wPrefillCycles"),
    }
    r.close()
    return out


@pytest.mark.parametrize("prompt", PROMPTS)
def test_the_state_after_the_prompt_is_the_same(prompt):
    n = run(prompt, 1, 0)["prompt"]                 # how many tokens the prompt is
    fast, full = run(prompt, n, 0), run(prompt, n, 1)
    assert fast["h"] == full["h"], "wH, all layers, after the prompt"
    assert fast["tokens"] == full["tokens"]
    k = n - 1                                       # passes whose argmax is thrown away
    assert fast["prefill"] < full["prefill"] * 0.75, (fast["prefill"], full["prefill"])
    assert full["prefill"] // k > 700_000 > 600_000 > fast["prefill"] // k


def test_the_reply_is_the_same():
    fast, full = run(PROMPTS[1], 40, 0), run(PROMPTS[1], 40, 1)
    assert fast["tokens"] == full["tokens"] and fast["h"] == full["h"]
