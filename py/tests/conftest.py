import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import Rom  # noqa: E402


@pytest.fixture(scope="session")
def rom():
    """One booted, finished ROM shared by the whole session."""
    r = Rom()
    r.run_until_ready(max_frames=400000)   # generation needs ~16k frames
    yield r
    r.close()
