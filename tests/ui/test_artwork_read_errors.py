"""Chooser I/O failures must not change accepted or pending editing state."""
from copy import deepcopy
from unittest.mock import MagicMock
import shutil

import pytest
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox
from audio_metadata_editor.metadata import Metadata, write_mp3_metadata
import audio_metadata_editor.ui.main_window as module
import audio_metadata_editor.artwork as artwork_policy

@pytest.mark.parametrize('multi', [False, True])
@pytest.mark.parametrize('intent', ['accepted', 'replacement', 'removal'])
@pytest.mark.parametrize('failure', ['missing', 'permission', 'read', 'cancel', 'svg.jpg', 'svg.png', 'invalid', 'oversized', 'symlink', 'directory', 'fifo'])
def test_chooser_failure_preserves_state(tmp_path, audio_fixture_dir, qtbot, monkeypatch, multi, intent, failure):
    cover = tmp_path / 'cover.png'
    image = QImage(2, 2, QImage.Format_RGB32)
    image.fill(Qt.red); image.save(str(cover))
    paths = [tmp_path / f'{i}.mp3' for i in range(2 if multi else 1)]
    for p in paths:
        shutil.copy2(audio_fixture_dir / 'silence.mp3', p)
        write_mp3_metadata(p, Metadata(title='Original'), artwork=cover.read_bytes(), artwork_mime='image/png')
    w = module.MainWindow()
    qtbot.addWidget(w, before_close_func=lambda w: w._clear_editing_context())
    w._directory_selected(tmp_path); w.file_list.select_files([str(p) for p in paths])
    w.show()
    if intent == 'replacement':
        replacement = tmp_path / 'replacement.png'
        image.fill(Qt.blue); image.save(str(replacement))
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(replacement), ''))
        w._choose_artwork()
    elif intent == 'removal': w._remove_artwork()
    w.title_edit.selectAll(); qtbot.keyClicks(w.title_edit, 'Pending title')
    def snapshot():
        pixmap = w.artwork_label.pixmap()
        return deepcopy((w.current_metadata, w._multi_field_baselines, w.pending_artwork,
                         w.pending_artwork_mime, w.artwork_edited, w.multi_edit_artwork,
                         w.multi_edit_fields, w._per_file_edits, w._unresolved_single_fields,
                         w._unresolved_multi_fields, w._unresolved_per_file_fields,
                         w._get_edited_metadata(), w._has_unsaved_changes(),
                         [w.file_list.item(r, 0).text() for r in range(w.file_list.rowCount())],
                         pixmap.cacheKey() if pixmap is not None else None))
    before = snapshot()
    disk = [p.read_bytes() for p in paths]
    messages = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: messages.append(a[1:]))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: messages.append(a[1:]))
    writers = []
    for name in ('write_metadata', 'write_mp3_metadata', 'write_m4b_metadata'):
        spy = MagicMock(side_effect=AssertionError('chooser must not write metadata'))
        monkeypatch.setattr(module, name, spy); writers.append(spy)
    selected = tmp_path / ('selected.jpg' if failure == 'svg.jpg' else 'selected.png')
    if failure.startswith('svg'):
        selected.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"/>')
    elif failure == 'invalid':
        selected.write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
    elif failure in ('permission', 'read'):
        selected.write_bytes(cover.read_bytes())
    elif failure == 'oversized':
        with selected.open('wb') as stream:
            stream.truncate(artwork_policy.MAX_ARTWORK_BYTES + 1)
    elif failure == 'symlink':
        selected.symlink_to(cover)
    elif failure == 'directory':
        selected.mkdir()
    elif failure == 'fifo':
        import os
        os.mkfifo(selected)
    def choose(*args):
        if failure == 'missing':
            selected.write_bytes(cover.read_bytes()); selected.unlink()
        return ('' if failure == 'cancel' else str(selected), '')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', choose)
    if failure == 'permission':
        monkeypatch.setattr(artwork_policy, 'open', MagicMock(side_effect=PermissionError('access denied')), raising=False)
    elif failure == 'read':
        stream = MagicMock()
        stream.__enter__.return_value.read.side_effect = OSError('input/output error')
        monkeypatch.setattr(artwork_policy, 'open', MagicMock(return_value=stream), raising=False)
    w._choose_artwork()
    assert snapshot() == before
    assert [p.read_bytes() for p in paths] == disk
    for spy in writers: spy.assert_not_called()
    if failure == 'cancel': assert messages == []
    else:
        assert len(messages) == 1
        assert str(selected) in messages[0][1]
    if failure == 'read': stream.__exit__.assert_called_once()
