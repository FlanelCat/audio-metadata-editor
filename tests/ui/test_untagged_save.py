import shutil
import pytest
from mutagen.id3 import delete, ID3
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox, QFileDialog, QLineEdit
from audio_metadata_editor.metadata import read_metadata, MetadataReadError
import audio_metadata_editor.ui.main_window as module

@pytest.fixture
def setup(tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    p = tmp_path / 'untagged.mp3'
    shutil.copy2(audio_fixture_dir / 'silence.mp3', p)
    delete(p)
    before = p.read_bytes()
    w = module.MainWindow()
    qtbot.addWidget(w, before_close_func=lambda w: w._clear_editing_context())
    w._directory_selected(tmp_path)
    w.file_list.select_files([str(p)])
    w.show()
    assert w.title_edit.text() == ''
    assert not w._has_unsaved_changes()
    assert p.read_bytes() == before
    messages = []
    for kind in ('information', 'critical', 'warning'):
        monkeypatch.setattr(QMessageBox, kind, lambda *a: messages.append(a[1:]))
    return w, p, messages

@pytest.mark.parametrize('action', ['panel', 'enter', 'artwork', 'generated', 'date'])
def test_explicit_save_creates_tag(setup, qtbot, monkeypatch, tmp_path, action):
    w, p, messages = setup
    if action == 'enter':
        table = w.file_list
        table.setCurrentCell(0, 2)
        table.editItem(table.item(0, 2))
        editor = table.focusWidget()
        assert isinstance(editor, QLineEdit)
        editor.setText('Title')
        qtbot.keyClick(editor, Qt.Key_Return)
    else:
        if action == 'panel': qtbot.keyClicks(w.title_edit, 'Title')
        elif action == 'generated': w._apply_generated('title', {p: 'Title'})
        elif action == 'date': qtbot.keyClicks(w.date_edit, '2024-02')
        else:
            image_path = tmp_path / 'cover.png'
            image = QImage(2, 2, QImage.Format_RGB32); image.fill(Qt.red); image.save(str(image_path))
            monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(image_path), ''))
            w._choose_artwork()
        w._save_changes()
    saved = read_metadata(p)
    assert ID3(p).version == (2, 4, 0)
    if action == 'date': assert saved.date == '2024-02'
    elif action == 'artwork': assert saved.artwork == image_path.read_bytes()
    else: assert saved.title == 'Title'
    assert not w._has_unsaved_changes()


def test_invalid_date_keeps_untagged_pending(setup, qtbot):
    w, p, messages = setup
    before = p.read_bytes()
    qtbot.keyClicks(w.date_edit, 'not a date')
    w._save_changes()
    assert p.read_bytes() == before
    assert w._has_unsaved_changes() and w.date_edit.text() == 'not a date'
    assert not any(title == 'Saved' for title, _ in messages)

@pytest.mark.parametrize('failure', ['after_write', 'readback'])
def test_creation_failure_keeps_retry_intent(setup, qtbot, monkeypatch, failure):
    w, p, messages = setup
    qtbot.keyClicks(w.title_edit, 'Title')
    writer = module.write_mp3_metadata
    def fail_writer(*a, **k):
        writer(*a, **k)
        raise OSError('after tag creation')
    def fail_read(path): raise MetadataReadError(path, 'readback unavailable')
    with monkeypatch.context() as patch:
        if failure == 'after_write': patch.setattr(module, 'write_mp3_metadata', fail_writer)
        else: patch.setattr(w, '_read_after_write', fail_read)
        w._save_changes()
    assert read_metadata(p).title == 'Title'
    assert w._has_unsaved_changes() and 'title' in w._unresolved_single_fields
    assert not any(title == 'Saved' for title, _ in messages)
    w._save_changes()
    assert not w._has_unsaved_changes()
