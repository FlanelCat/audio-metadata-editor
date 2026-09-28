from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def audio_fixture_dir():
    """Immutable source audio; copy named samples to tmp_path before use."""
    return Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Every test uses its own INI store, never developer/user settings."""
    from PySide6.QtCore import QSettings
    from audio_metadata_editor import settings
    filename = str(tmp_path / 'application-settings.ini')
    monkeypatch.setattr(settings, 'create_settings',
                        lambda: QSettings(filename, QSettings.IniFormat))
