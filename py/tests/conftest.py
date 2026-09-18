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
