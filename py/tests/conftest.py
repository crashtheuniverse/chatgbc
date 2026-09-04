"""v0.5 suite plumbing: the root harness, pointed at this app's ROMs."""
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
ROOT = APP
sys.path.insert(0, str(ROOT / "py"))
sys.path.insert(0, str(APP / "py"))

import pytest                    # noqa: E402
import harness                   # noqa: E402


def lab_rom():
    return harness.Rom(rom=APP / "build" / "chatgbc-lab.gbc",
                       sym=APP / "build" / "chatgbc-lab.sym", lab=True)


@pytest.fixture(scope="session")
def booted():
    r = lab_rom()
    r.pyboy.tick(400, False)
    yield r
    r.close()
