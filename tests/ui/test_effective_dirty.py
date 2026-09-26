"""Effective pending edits on temporary media, including raw invalid numbers."""
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QMessageBox

from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata, write_m4b_metadata
from audio_metadata_editor.ui.main_window import MainWindow
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def make_window(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    def make(values):
        paths = []
        for i, metadata in enumerate(values):
            path = tmp_path / f'{i}.{request.param}'
            shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
            writer = write_mp3_metadata if request.param == "mp3" else write_m4b_metadata
            writer(path, metadata, artwork=metadata.artwork,
                           artwork_mime=metadata.artwork_mime)
            paths.append(path)
        win = MainWindow()
        qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
        win.root_path = tmp_path
        win._populate_root()
        win.file_list.setSortingEnabled(False)
        win.file_list.select_files([str(p) for p in paths])
        win.show()
        assert not win._has_unsaved_changes()
        monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
        monkeypatch.setattr(QMessageBox, 'critical', lambda *args: pytest.fail(str(args)))
        return win, paths
    return make


def edit(qtbot, widget, text):
    widget.setFocus()
    widget.selectAll()
    if text:
        qtbot.keyClicks(widget, text)
    else:
        qtbot.keyClick(widget, Qt.Key_Backspace)


@pytest.mark.parametrize('field,editor,original,changed', [
    ('artist', 'artist_edit', 'Original', 'Changed'),
    ('track_number', 'track_edit', 3, '8'),
    ('series_number', 'series_number_edit', '01.5', '2.0'),
])
def test_common_restore(make_window, qtbot, monkeypatch, field, editor, original, changed):
    win, paths = make_window([Metadata(**{field: original}) for _ in range(2)])
    before = [p.read_bytes() for p in paths]
    edit(qtbot, getattr(win, editor), changed)
    assert win.multi_edit_fields == {field}
    assert win._has_unsaved_changes()
    edit(qtbot, getattr(win, editor), str(original))
    assert not win.multi_edit_fields
    assert not win._has_unsaved_changes()
    monkeypatch.setattr(module, 'write_mp3_metadata', lambda *a, **k: pytest.fail('write'))
    monkeypatch.setattr(module, 'write_m4b_metadata', lambda *a, **k: pytest.fail('write'))
    win._save_changes()
    assert [p.read_bytes() for p in paths] == before
    assert getattr(win._get_edited_metadata(), field) == original


@pytest.mark.parametrize('value', ['Original', ''])
def test_mixed_explicit_value(make_window, qtbot, value):
    win, paths = make_window([Metadata(artist='Original'), Metadata(artist='Different')])
    edit(qtbot, win.artist_edit, 'intermediate')
    edit(qtbot, win.artist_edit, value)
    assert win.multi_edit_fields == {'artist'}
    assert win._has_unsaved_changes()
    win._save_changes()
    assert all(read_metadata(p).artist == value for p in paths)
    assert not win._has_unsaved_changes()


NUMBERS = [('track_number', 'track_edit', 'Track'),
           ('track_total', 'track_total_edit', 'Track Total'),
           ('disc_number', 'disc_edit', 'Disc'),
           ('disc_total', 'disc_total_edit', 'Disc Total')]


@pytest.mark.parametrize('field,editor,label', NUMBERS)
@pytest.mark.parametrize('baseline', [None, 3])
@pytest.mark.parametrize('multiple', [False, True])
def test_invalid_numeric_pending(make_window, qtbot, monkeypatch, field, editor, label, baseline, multiple):
    values = {field: baseline}
    if field.endswith("_total") and baseline is not None:
        values[field.replace("_total", "_number")] = 1
    win, paths = make_window([Metadata(**values) for _ in range(2 if multiple else 1)])
    assert getattr(read_metadata(paths[0]), field) == baseline
    before = [p.read_bytes() for p in paths]
    widget = getattr(win, editor)
    edit(qtbot, widget, 'invalid')
    assert win._has_unsaved_changes()
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args))
    win._save_changes()
    assert warnings[0][1:] == ('Invalid Number', f'{label} must be a whole number.')
    assert win.focusWidget() is widget
    assert widget.selectedText() == 'invalid'
    assert [p.read_bytes() for p in paths] == before
    edit(qtbot, widget, '8')
    assert win._has_unsaved_changes()
    edit(qtbot, widget, '' if baseline is None else str(baseline))
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('action', ['selection', 'directory', 'refresh', 'close'])
@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_invalid_numeric_guards(make_window, qtbot, monkeypatch, tmp_path, multiple, action, reply):
    win, paths = make_window([Metadata() for _ in range(2 if multiple else 1)])
    before = [p.read_bytes() for p in paths]
    edit(qtbot, win.track_edit, 'invalid')
    prompts, warnings = [], []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: prompts.append(args) or reply)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args))
    event = QCloseEvent()
    if action == 'selection':
        win.file_list.clearSelection()
    elif action == 'directory':
        destination = tmp_path / 'empty'
        destination.mkdir()
        win._directory_selected(destination)
    elif action == 'refresh':
        win._refresh_tree()
    else:
        win.closeEvent(event)
    assert len(prompts) == 1
    assert bool(warnings) == (reply == QMessageBox.Save)
    if reply != QMessageBox.Discard:
        assert win.selected_files == [str(p) for p in paths]
        assert win.track_edit.text() == 'invalid'
        assert win._has_unsaved_changes()
        if action == 'close':
            assert not event.isAccepted()
    elif action == 'close':
        assert event.isAccepted()
    else:
        assert not win._has_unsaved_changes()
        assert win.track_edit.text() == ''
    assert [p.read_bytes() for p in paths] == before


@pytest.mark.parametrize('covers', [(), (0,), (0, 1)])
@pytest.mark.parametrize('multiple', [False, True])
def test_paste_absent_artwork(make_window, monkeypatch, covers, multiple):
    values = [Metadata(artwork=b'cover' if i in covers else None,
                       artwork_mime='image/jpeg' if i in covers else '')
              for i in range(2 if multiple else 1)]
    win, paths = make_window(values)
    before = [p.read_bytes() for p in paths]
    win.metadata_clipboard = Metadata()
    if not covers:
        win.file_list.select_files([str(paths[0])])
        win._copy_metadata()
        win.file_list.select_files([str(p) for p in paths])
        assert win.metadata_clipboard.artwork is None
    writes = []
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    def record_write(path, *args, **kwargs):
        writes.append(path)
        return writer(path, *args, **kwargs)
    monkeypatch.setattr(module, writer_name, record_write)
    monkeypatch.setattr(module.PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.PasteFieldsDialog, 'selected_fields', property(lambda self: {'artwork'}))
    win._paste_metadata()
    expected = any(v.artwork is not None for v in values)
    assert win._has_unsaved_changes() == expected
    assert win.artwork_edited == expected
    assert win.multi_edit_artwork == (multiple and expected)
    assert win.artwork_label.pixmap().isNull()
    for row in range(len(paths)):
        item = win.file_list.item(row, 0)
        index = paths.index(Path(item.data(256)))
        assert item.text().startswith('*') == (values[index].artwork is not None)
    win._save_changes()
    assert not win._has_unsaved_changes()
    assert writes == [p for p, value in zip(paths, values) if value.artwork is not None]
    for i, path in enumerate(paths):
        assert read_metadata(path).artwork is None
        if values[i].artwork is None:
            assert path.read_bytes() == before[i]


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('field,editor,label', NUMBERS)
def test_negative_and_discard_restore(make_window, qtbot, monkeypatch, multiple, field, editor, label):
    win, paths = make_window([Metadata(track_number=2, track_total=5, disc_number=1, disc_total=3)
                             for _ in range(2 if multiple else 1)])
    widget = getattr(win, editor)
    original = widget.text()
    before = [p.read_bytes() for p in paths]
    edit(qtbot, widget, '-1')
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args))
    win._save_changes()
    assert warnings[0][2] == f'{label} cannot be negative.'
    assert widget.selectedText() == '-1'
    assert win._has_unsaved_changes()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Discard)
    assert win._guard_selection_change()
    assert widget.text() == original
    assert not win._has_unsaved_changes()
    assert [p.read_bytes() for p in paths] == before


def test_restore_preserves_other_intent_without_reads(make_window, qtbot, monkeypatch):
    win, paths = make_window([Metadata(artist='Original', track_number=2, disc_number=1)] * 2)
    original_reader = module.read_metadata
    monkeypatch.setattr(module, 'read_metadata', lambda *args: pytest.fail('read during edit'))
    edit(qtbot, win.disc_edit, '4')
    edit(qtbot, win.track_edit, '8')
    edit(qtbot, win.artist_edit, 'Other')
    edit(qtbot, win.track_edit, '2')
    edit(qtbot, win.artist_edit, 'Original')
    assert win.multi_edit_fields == {'disc_number'}
    assert win._has_unsaved_changes()
    monkeypatch.setattr(module, 'read_metadata', original_reader)
    win._save_changes()
    assert all(read_metadata(p).disc_number == 4 and read_metadata(p).track_number == 2 for p in paths)
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('text,expected', [('2', 2), ('', None)])
def test_mixed_numeric_explicit_value(make_window, qtbot, text, expected):
    win, paths = make_window([Metadata(track_number=2), Metadata(track_number=None)])
    edit(qtbot, win.track_edit, '8')
    edit(qtbot, win.track_edit, text)
    assert win.multi_edit_fields == {'track_number'}
    win._save_changes()
    assert all(read_metadata(p).track_number == expected for p in paths)
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('readback_failure', [False, True])
def test_restore_uses_verified_immediate_save_baseline(make_window, qtbot, monkeypatch, readback_failure):
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths = make_window([Metadata(artist='Original')] * 2)
    original_readback = win._read_after_write
    for path in paths:
        if readback_failure:
            def fail(p):
                raise MetadataReadError(p, 'injected readback failure')
            monkeypatch.setattr(win, '_read_after_write', fail)
            with pytest.raises(MetadataReadError):
                win._save_metadata_field(path, 'artist', 'Saved')
        else:
            win._save_metadata_field(path, 'artist', 'Saved')
    monkeypatch.setattr(win, '_read_after_write', original_readback)
    if readback_failure:
        win._verify_field_saves()
    edit(qtbot, win.artist_edit, 'Other')
    edit(qtbot, win.artist_edit, 'Saved')
    assert not win.multi_edit_fields
    assert not win._has_unsaved_changes()
    edit(qtbot, win.artist_edit, 'Original')
    assert win.multi_edit_fields == {'artist'}


def test_paste_absent_cancels_pending_addition(make_window, monkeypatch):
    win, _ = make_window([Metadata(), Metadata()])
    monkeypatch.setattr(module.PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.PasteFieldsDialog, 'selected_fields', property(lambda self: {'artwork'}))
    win.metadata_clipboard = Metadata(artwork=b'pending', artwork_mime='image/jpeg')
    win._paste_metadata()
    assert win._has_unsaved_changes()
    win.metadata_clipboard = Metadata()
    win._paste_metadata()
    assert not win._has_unsaved_changes()
    assert not win.multi_edit_artwork


def test_verification_keeps_new_invalid_numeric_input(make_window, qtbot, monkeypatch):
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths = make_window([Metadata()])
    readback = win._read_after_write
    def fail(path):
        raise MetadataReadError(path, 'injected readback failure')
    monkeypatch.setattr(win, '_read_after_write', fail)
    with pytest.raises(MetadataReadError):
        win._save_metadata_field(paths[0], 'track_number', 2)
    edit(qtbot, win.track_edit, 'invalid')
    monkeypatch.setattr(win, '_read_after_write', readback)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args))
    before = paths[0].read_bytes()
    win._save_changes()
    assert win.track_edit.text() == 'invalid'
    assert win._has_unsaved_changes()
    assert warnings[0][2] == 'Track must be a whole number.'
    assert paths[0].read_bytes() == before
    win._undo_changes()
    assert win.track_edit.text() == '2'
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('failure', ['second_write', 'first_readback'])
def test_restore_after_partial_panel_save_stays_pending(make_window, qtbot, monkeypatch, failure):
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths = make_window([Metadata(artist='Original')] * 2)
    edit(qtbot, win.artist_edit, 'Changed')
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    readback = win._read_after_write
    def write(path, *args, **kwargs):
        if path == paths[1]:
            raise OSError('injected second write failure')
        return writer(path, *args, **kwargs)
    def fail_readback(path):
        raise MetadataReadError(path, 'injected readback failure')
    if failure == 'second_write':
        monkeypatch.setattr(module, writer_name, write)
    else:
        monkeypatch.setattr(win, '_read_after_write', fail_readback)
    win._save_changes()
    assert errors
    assert read_metadata(paths[0]).artist == 'Changed'
    edit(qtbot, win.artist_edit, 'Original')
    assert win.multi_edit_fields == {'artist'}
    assert win._has_unsaved_changes()
    monkeypatch.setattr(module, writer_name, writer)
    monkeypatch.setattr(win, '_read_after_write', readback)
    win._save_changes()
    assert all(read_metadata(p).artist == 'Original' for p in paths)
    assert not win._has_unsaved_changes()
