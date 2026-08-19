import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import Rom  # noqa: E402


@pytest.fixture(scope="session")
def rom():
    """One booted lab ROM with a full-length run already done.

    The lab build has no keyboard and no frame, and takes its prompt and token
    count from here. That matters for more than tidiness: the suite used to boot
    two separate demo ROMs and generate 96 tokens twice, which was 22 of its 24
    seconds. Anything needing the presentation layer uses its own app-ROM
    fixture instead.
    """
    r = Rom(lab=True)
    r.lab_run(steps=r.defs["GEN_STEPS"])
    yield r
    r.close()
