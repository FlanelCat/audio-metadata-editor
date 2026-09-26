from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def audio_fixture_dir():
    """Immutable source audio; copy named samples to tmp_path before use."""
    return Path(__file__).parent / "fixtures" / "audio"
