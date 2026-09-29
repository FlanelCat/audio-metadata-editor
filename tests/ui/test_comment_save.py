import shutil
import pytest
from mutagen.id3 import ID3, COMM
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from audio_metadata_editor.metadata import read_metadata, MetadataReadError
from audio_metadata_editor.ui.main_window import MainWindow

@pytest.fixture
def setup(tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{i}.mp3' for i in range(2)]
    for p in paths:
        shutil.copy2(audio_fixture_dir / 'silence.mp3', p)
        tags = ID3(p)
        for desc, lang, value in [('', 'eng', 'Original'), ('', 'swe', 'Swedish'), ('Description', 'eng', 'Keep'), ('ID3v1 Comment', 'eng', 'Separate')]:
            tags.add(COMM(encoding=1, desc=desc, lang=lang, text=[value]))
        tags.save(p)
    w = MainWindow(); qtbot.addWidget(w, before_close_func=lambda w: w._clear_editing_context())
    w._directory_selected(tmp_path); w.file_list.select_files([str(paths[0])]); w.show()
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: messages.append(a[1]))
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: messages.append(a[1]))
    return w, paths, messages

@pytest.mark.parametrize('multi', [False, True])
@pytest.mark.parametrize('field,value', [('comment', 'Changed'), ('comment', ''), ('id3v1_comment', 'Changed separate'), ('id3v1_comment', '')])
def test_panel_save(setup, qtbot, multi, field, value):
    w, paths, messages = setup
    if multi: w.file_list.select_files([str(p) for p in paths])
    editor = getattr(w, field + '_edit')
    editor.selectAll(); qtbot.keyClick(editor, Qt.Key_Backspace)
    if value: qtbot.keyClicks(editor, value)
    assert w._has_unsaved_changes()
    w._save_changes()
    assert not w._has_unsaved_changes() and 'Saved' in messages
    for p in paths if multi else paths[:1]:
        metadata = read_metadata(p)
        assert getattr(metadata, field) == value
        assert getattr(metadata, 'id3v1_comment' if field == 'comment' else 'comment') == ('Separate' if field == 'comment' else 'Original')
        tags = ID3(p)
        assert tags['COMM::swe'].text == ['Swedish']
        assert tags['COMM:Description:eng'].text == ['Keep']


def test_readback_failure_keeps_comment_pending(setup, qtbot, monkeypatch):
    w, paths, messages = setup
    w.comment_edit.selectAll(); qtbot.keyClicks(w.comment_edit, 'Changed')
    def fail(path): raise MetadataReadError(path, 'unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(w, '_read_after_write', fail)
        w._save_changes()
    assert 'Saved' not in messages
    assert w._has_unsaved_changes() and w.comment_edit.text() == 'Changed'
    w._save_changes()
    assert not w._has_unsaved_changes()
