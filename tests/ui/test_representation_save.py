"""S4 preflight and mismatched readback through each explicit save workflow."""
import shutil
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QMessageBox, QDialog, QLineEdit

from audio_metadata_editor.metadata import Metadata, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{i}.{request.param}' for i in range(3)]
    for p in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', p)
        write_metadata(p, Metadata(title='old', artist='keep', track_number=4, track_total=17))
    w = module.MainWindow()
    qtbot.addWidget(w, before_close_func=lambda w: w._clear_editing_context())
    w.file_list.setSortingEnabled(False)
    w.file_list.load_directory(tmp_path)
    w.file_list.setCurrentCell(0, 2)
    w.show()
    messages = []
    for kind in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, kind, lambda *a, kind=kind: messages.append((kind, a[1], a[2])))
    return w, paths, messages


def stage(w, paths, mode, value):
    if mode != 'single':
        w.file_list.select_files([str(p) for p in paths])
    if mode in ('single', 'multi'):
        w.title_edit.setText(value)
        w.title_edit.textEdited.emit(value)
    elif mode == 'generated':
        w._apply_generated('title', {p: value for p in paths})
    else:
        w._apply_generated('title', {p: value if p == paths[0] else 'old' for p in paths})
        w.file_list.setCurrentCell(0, 2, QItemSelectionModel.NoUpdate)
        w.file_list.copy_down_action.trigger()
        assert all(w._per_file_edits[p]['title'] == w.file_list.item(0, 2).text() for p in paths[1:])


@pytest.mark.parametrize('mode', ['single', 'multi', 'generated', 'copy'])
def test_preflight_zero_calls_retains_raw(setup, monkeypatch, mode):
    w, paths, messages = setup
    # M4B accepts NUL, but cannot encode an unpaired surrogate.
    value = 'left\0right' if paths[0].suffix == '.mp3' else 'left\ud800right'
    stage(w, paths, mode, value)
    before = [p.read_bytes() for p in paths]
    writers = []
    for name in ('write_metadata', 'write_mp3_metadata', 'write_m4b_metadata'):
        spy = Mock()
        monkeypatch.setattr(module, name, spy)
        writers.append(spy)
    w._save_changes()
    assert all(spy.call_count == 0 for spy in writers)
    assert [p.read_bytes() for p in paths] == before
    if mode == 'copy':
        assert w._per_file_edits[paths[0]]['title'] == value
    else:
        assert w._get_edited_metadata().title == value
    assert w._has_unsaved_changes()
    assert not w._unresolved_single_fields and not w._unresolved_multi_fields
    assert not w._unresolved_per_file_fields
    assert any('Title' in text for _, _, text in messages)
    assert not any(title == 'Saved' for _, title, _ in messages)


def test_later_invalid_target_preflights_whole_batch(setup, monkeypatch):
    w, paths, messages = setup
    w.file_list.select_files([str(p) for p in paths])
    value = 'bad\0value' if paths[0].suffix == '.mp3' else 'bad\ud800'
    w._apply_generated('title', {paths[0]: 'valid', paths[1]: value, paths[2]: 'old'})
    spies = [Mock(), Mock()]
    monkeypatch.setattr(module, 'write_mp3_metadata', spies[0])
    monkeypatch.setattr(module, 'write_m4b_metadata', spies[1])
    w._save_changes()
    assert all(spy.call_count == 0 for spy in spies)
    assert w._per_file_edits[paths[1]]['title'] == value
    assert w._has_unsaved_changes()


@pytest.mark.parametrize('mode', ['single', 'multi', 'generated', 'copy'])
@pytest.mark.parametrize('final_read', [False, True])
def test_mismatch_retains_current_intent_and_retry(setup, monkeypatch, mode, final_read):
    w, paths, messages = setup
    stage(w, paths, mode, 'requested')
    real_read = w._read_after_write
    calls = 0
    def mismatch(path):
        nonlocal calls
        calls += 1
        result = real_read(path)
        if not final_read or calls == (4 if mode != 'single' else 1):
            result.title = 'different'
        return result
    with monkeypatch.context() as patch:
        patch.setattr(w, '_read_after_write', mismatch)
        w._save_changes()
    assert w._has_unsaved_changes()
    assert w._get_edited_metadata().title == 'requested'
    assert not any(title == 'Saved' for _, title, _ in messages)
    assert any('did not match' in text for _, _, text in messages)
    assert not w._unverified_fields
    if mode in ('generated', 'copy'):
        assert all(w._per_file_edits[p]['title'] == 'requested' for p in paths)
        assert w._unresolved_per_file_fields
    # Current intent wins on panel/per-file retry, even when it restores old text.
    w.title_edit.setText('old')
    w.title_edit.textEdited.emit('old')
    w._save_changes()
    assert not w._has_unsaved_changes()
    for p in paths:
        assert read_metadata(p).title == 'old'
        assert read_metadata(p).artist == 'keep'
        assert read_metadata(p).track_total == 17


def test_enter_preflight_keeps_editor_and_does_not_advance(setup, monkeypatch, qtbot):
    w, paths, messages = setup
    table = w.file_list
    column = 2 if paths[0].suffix == '.mp3' else 1
    value = 'left\0right' if column == 2 else '65536'
    table.setCurrentCell(0, column)
    accepted = table.item(0, column).text()
    table.editItem(table.item(0, column))
    editor = table.focusWidget()
    assert isinstance(editor, QLineEdit)
    editor.setText(value)
    writer = Mock()
    monkeypatch.setattr(module, 'write_metadata', writer)
    qtbot.keyClick(editor, Qt.Key_Return)
    assert writer.call_count == 0
    assert table.currentRow() == 0
    assert table.item(0, column).text() == accepted
    assert editor.text() == value and editor.selectedText() == value
    assert editor.hasFocus()
    assert messages


@pytest.mark.parametrize('mode', ['table', 'auto'])
def test_immediate_mismatch_verifies_without_replay(setup, monkeypatch, qtbot, mode):
    w, paths, messages = setup
    field = 'title' if mode == 'table' else 'track_number'
    expected = 'requested' if mode == 'table' else 8
    writes = []
    def writer(path, metadata, **kwargs):
        writes.append(path)
        write_metadata(path, metadata, **kwargs)
    monkeypatch.setattr(module, 'write_metadata', writer)
    real_read = w._read_after_write
    def mismatch(path):
        result = real_read(path)
        setattr(result, field, 'different' if mode == 'table' else 99)
        return result
    with monkeypatch.context() as patch:
        patch.setattr(w, '_read_after_write', mismatch)
        if mode == 'table':
            w.file_list.editItem(w.file_list.item(0, 2))
            editor = w.file_list.focusWidget()
            editor.setText(expected)
            qtbot.keyClick(editor, Qt.Key_Return)
            assert not w.file_list.cell_save_succeeded
            assert w.file_list.currentRow() == 0
        else:
            w.file_list.select_files([str(p) for p in paths])
            patch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
            patch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: expected))
            w._auto_number_tracks()
            assert any('0 file(s) saved and verified' in text for _, _, text in messages)
        assert writes == [paths[0]]
        assert w._unverified_fields == {paths[0]: {field}}
        assert w._unverified_requests[paths[0]][field] == expected
        assert w._has_unsaved_changes()
        w._save_changes()  # Still mismatched: do not clear or replay.
        assert w._unverified_fields
        assert writes == [paths[0]]
    w._save_changes()
    assert not w._unverified_fields and not w._unverified_requests
    assert writes == [paths[0]]
    assert getattr(read_metadata(paths[0]), field) == expected
    assert read_metadata(paths[0]).track_total == 17
    assert any('did not match' in text for _, _, text in messages)


@pytest.mark.parametrize('multiple', [False, True])
def test_artwork_mismatch_retains_replacement(setup, monkeypatch, multiple):
    w, paths, messages = setup
    if multiple:
        w.file_list.select_files([str(p) for p in paths])
        w.multi_edit_artwork = True
    w.pending_artwork = b'cover'
    w.pending_artwork_mime = 'image/png'
    w.artwork_edited = True
    real_read = w._read_after_write
    def mismatch(path):
        result = real_read(path)
        result.artwork = b'different'
        return result
    with monkeypatch.context() as patch:
        patch.setattr(w, '_read_after_write', mismatch)
        w._save_changes()
    assert w._has_unsaved_changes()
    assert w.pending_artwork == b'cover'
    assert not any(title == 'Saved' for _, title, _ in messages)
    w._save_changes()
    assert not w._has_unsaved_changes()


@pytest.mark.parametrize('field,editor_name', [('track_number', 'track_edit'), ('track_total', 'track_total_edit'),
                                             ('disc_number', 'disc_edit'), ('disc_total', 'disc_total_edit')])
@pytest.mark.parametrize('multiple', [False, True])
def test_numeric_preflight_and_valid_boundaries(setup, monkeypatch, field, editor_name, multiple):
    w, paths, messages = setup
    if multiple:
        w.file_list.select_files([str(p) for p in paths])
    editor = getattr(w, editor_name)
    editor.setText('65536')
    editor.textEdited.emit('65536')
    if paths[0].suffix == '.m4b':
        with monkeypatch.context() as patch:
            spy = Mock()
            patch.setattr(module, 'write_m4b_metadata', spy)
            w._save_changes()
            assert spy.call_count == 0
        assert editor.text() == '65536' and w._has_unsaved_changes()
        assert editor.hasFocus()
    else:
        w._save_changes()
        assert not w._has_unsaved_changes()
    editor.setText('65535')
    editor.textEdited.emit('65535')
    w._save_changes()
    assert not w._has_unsaved_changes()
    for p in paths if multiple else paths[:1]:
        assert getattr(read_metadata(p), field) == 65535


def test_valid_text_and_m4b_nul_save(setup):
    w, paths, messages = setup
    value = '日本語 🎧' if paths[0].suffix == '.mp3' else 'left\0right 日本語 🎧'
    stage(w, paths, 'multi', value)
    w._save_changes()
    assert all(read_metadata(p).title == value for p in paths)
    assert not w._has_unsaved_changes()
    assert any(title == 'Saved' for _, title, _ in messages)


@pytest.mark.parametrize('phase', ['refresh', 'final'])
def test_auto_number_common_readback_mismatch(setup, monkeypatch, phase):
    w, paths, messages = setup
    w.file_list.select_files([str(p) for p in paths])
    monkeypatch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: 8))
    writes = []
    def writer(path, metadata, **kwargs):
        writes.append(path)
        write_metadata(path, metadata, **kwargs)
    monkeypatch.setattr(module, 'write_metadata', writer)
    # Only the presentation reads use module.read_metadata directly; keep the
    # immediate write verification real to distinguish this later boundary.
    monkeypatch.setattr(w, '_read_after_write', read_metadata)
    if phase == 'final':
        w.track_edit.setText('9')
        w.track_edit.textEdited.emit('9')  # Suppress intermediate common refresh.
    def mismatch(path):
        result = read_metadata(path)
        if writes and path == paths[0]:
            result.track_number = 99
        return result
    with monkeypatch.context() as patch:
        patch.setattr(module, 'read_metadata', mismatch)
        w._auto_number_tracks()
    assert len(writes) == (1 if phase == 'refresh' else 3)
    assert w._unverified_requests[paths[0]] == {'track_number': 8}
    assert w._has_unsaved_changes()
    assert any('did not match' in text for _, _, text in messages)
    assert 'Auto-numbered' not in w.statusBar().currentMessage()
    w._verify_field_saves()
    assert not w._unverified_fields
