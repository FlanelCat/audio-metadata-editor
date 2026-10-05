"""Panel saves preserve raw trailers and retain intent on preservation failure."""
import shutil

import pytest
from mutagen.id3 import ID3
from PySide6.QtWidgets import QMessageBox

from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow
import audio_metadata_editor.metadata.mp3 as mp3


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('multi', [False, True])
@pytest.mark.parametrize('fail_restore', [False, True])
def test_panel_save(tmp_path, audio_fixture_dir, qtbot, monkeypatch, version, multi, fail_restore):
    paths = [tmp_path / f'{i}.mp3' for i in range(2 if multi else 1)]
    trailer = b'TAG' + b'raw title'.ljust(30, b' ') + b'raw artist'.ljust(30, b' ')
    trailer += b'raw album'.ljust(30, b' ') + b'1987' + b'raw comment'.ljust(30, b' ') + b'\x11'
    for path in paths:
        shutil.copy2(audio_fixture_dir / 'silence.mp3', path)
        ID3(path).save(path, v2_version=version, v1=0)
        with path.open('ab') as stream:
            stream.write(trailer)
    window = MainWindow()
    qtbot.addWidget(window, before_close_func=lambda w: w._clear_editing_context())
    window._directory_selected(tmp_path)
    window.file_list.select_files([str(p) for p in paths])
    for editor, value in [(window.title_edit, 'New title'), (window.artist_edit, 'New artist'),
                          (window.comment_edit, 'Comment'), (window.id3v1_comment_edit, 'Logical'),
                          (window.date_edit, '2025'), (window.track_edit, '2'),
                          (window.series_edit, 'Series')]:
        editor.selectAll()
        qtbot.keyClicks(editor, value)
    errors, successes = [], []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: successes.append(a))
    if fail_restore:
        def fail(*args):
            raise OSError('Raw ID3v1 restoration failed')
        monkeypatch.setattr(mp3, '_restore_raw_id3v1', fail)
    window._save_changes()
    if fail_restore:
        assert errors and 'restoration failed' in errors[0][2]
        assert not successes
        assert window._has_unsaved_changes()
        if multi:
            assert read_metadata(paths[1]).title == 'Original'
            assert paths[1].read_bytes()[-128:] == trailer
    else:
        assert not errors
        assert not window._has_unsaved_changes()
        for path in paths:
            assert path.read_bytes()[-128:] == trailer
            assert read_metadata(path).title == 'New title'
            assert read_metadata(path).id3v1_comment == 'Logical'
            assert ID3(path, load_v1=False).version == (2, version, 0)
