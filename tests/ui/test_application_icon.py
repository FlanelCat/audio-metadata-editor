"""Installed-resource loading and application-wide icon inheritance."""
from importlib.resources import files

import pytest
from PySide6.QtWidgets import QDialog

from audio_metadata_editor import main
from audio_metadata_editor.ui import application_icon


def test_packaged_icon_loads_outside_repository(qapp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resource = files('audio_metadata_editor').joinpath('resources/application-icon.png')
    assert resource.is_file()
    assert resource.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    icon = application_icon.load_application_icon()
    assert not icon.isNull()
    assert not icon.pixmap(32, 32).isNull()


def test_startup_sets_icon_before_main_window(qapp, qtbot, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    previous_icon = qapp.windowIcon()
    real_window = main.MainWindow
    windows = []

    def create_window():
        assert not qapp.windowIcon().isNull()
        window = real_window()
        qtbot.addWidget(window)
        assert window.windowIcon().cacheKey() == qapp.windowIcon().cacheKey()
        assert not window.windowIcon().pixmap(32, 32).isNull()
        dialog = QDialog(window)
        assert dialog.windowIcon().cacheKey() == qapp.windowIcon().cacheKey()
        windows.append(window)
        return window

    monkeypatch.setattr(main, 'QApplication', lambda argv: qapp)
    monkeypatch.setattr(main, 'MainWindow', create_window)
    monkeypatch.setattr(qapp, 'exec', lambda: 0)
    try:
        with pytest.raises(SystemExit) as exit_info:
            main.main()
        assert exit_info.value.code == 0
        assert len(windows) == 1
    finally:
        qapp.setWindowIcon(previous_icon)


@pytest.mark.parametrize('failure', ['missing', 'invalid'])
def test_broken_resource_reports_error(qapp, tmp_path, monkeypatch, failure):
    (tmp_path / 'resources').mkdir()
    if failure == 'invalid':
        (tmp_path / 'resources/application-icon.png').write_bytes(b'not an image')
    monkeypatch.setattr(application_icon, 'files', lambda package: tmp_path)
    with pytest.raises(RuntimeError, match='packaged application icon'):
        application_icon.load_application_icon()
