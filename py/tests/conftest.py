"""v0.5 suite plumbing: the root harness, pointed at this app's ROMs."""
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
ROOT = APP
sys.path.insert(0, str(ROOT / "py"))
sys.path.insert(0, str(APP / "py"))

import pytest                    # noqa: E402
import harness                   # noqa: E402


# test.ps1 points the Rei suite at build/rei-lab.gbc with CHATGBC_LAB=rei-lab.
LAB = os.environ.get("CHATGBC_LAB", "chatgbc-lab")


def lab_rom():
    return harness.Rom(rom=APP / "build" / f"{LAB}.gbc",
                       sym=APP / "build" / f"{LAB}.sym", lab=True)


@pytest.fixture(scope="session")
def booted():
    r = lab_rom()
    r.pyboy.tick(400, False)
    yield r
    r.close()


def lab_encode(r, text, cont):
    """The lab ROM's encode-only entry: `text` staged as the ROM stages it,
    encoded fresh (Encode) or as a continuation (EncodeCont). Returns the
    tokens and the cycles it took."""
    raw = text.encode("ascii")
    assert len(raw) <= r.defs["PROMPT_MAX"]
    idle, state, go = r.defs["LAB_IDLE"], r.addr("wLabState"), r.addr("wLabGo")
    r._tick_until(lambda: r.pyboy.memory[state] == idle, 2000, "lab idle")
    base = r.addr("wPromptText")
    r.pyboy.memory[base:base + len(raw)] = list(raw)
    r.pyboy.memory[r.addr("wPromptLen")] = len(raw)
    ready = r.addr("wReady")
    r.pyboy.memory[ready] = 0
    r.pyboy.memory[go] = 0xE3 if cont else 0xE2
    r._tick_until(lambda: r.pyboy.memory[ready] == r.defs["READY_MAGIC"], 3000, "encode")
    r.pyboy.memory[go] = 0
    n = r.read("wTokCount")[0]
    buf = r.read("wTokBuf", 2 * n)
    return [buf[2 * i] | (buf[2 * i + 1] << 8) for i in range(n)], r.read_u32("wEncCycles")
