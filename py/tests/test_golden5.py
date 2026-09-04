"""The contract: the cartridge emits the twin's exact token sequence."""
import json

import export5                    # noqa: E402
from conftest import APP, lab_rom


def test_matches_golden_tokens():
    g = json.loads((APP / "build" / "golden.json").read_text())
    r = lab_rom()
    r.lab_run(steps=48, prompt=export5.PROMPT)
    n = r.read("wGenCount")[0]
    out = r.read("wOutTokens", 2 * n)
    toks = [out[2 * i] | (out[2 * i + 1] << 8) for i in range(n)]
    r.close()
    want = g["tokens"]
    bad = next((i for i in range(min(len(toks), len(want)))
                if toks[i] != want[i]), None)
    assert bad is None, f"diverged at {bad}: rom {toks[bad]} twin {want[bad]}"
    assert len(toks) == len(want)


def test_state_survives_and_cost_is_flat():
    """No ring, no window: the last token costs what the first does, and the
    state is nonzero after a run - the being actually remembered something."""
    r = lab_rom()
    r.lab_run(steps=32, prompt=export5.PROMPT)
    tot, n = r.read_u32("wGenTotal"), r.read("wGenCount")[0]
    last = r.read_u32("wTokCycles")
    h = bytes(r.read("wH", 320))
    r.close()
    avg = tot // n
    assert abs(last - avg) < avg * 0.15, "cost should be flat without a ring"
    assert any(h), "a zero state after 32 tokens means the gate never wrote"
