import importlib
from pathlib import Path
import shutil

import pytest
from PySide6.QtWidgets import QMessageBox
from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{name}.{request.param}' for name in 'abc']
    for path in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
    win = MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.file_list.setSortingEnabled(False)
    win.file_list.load_directory(tmp_path)
    errors, successes = [], []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: successes.append(args))
    module = importlib.import_module(f'audio_metadata_editor.metadata.{request.param}')
    original = getattr(module, 'ID3' if request.param == 'mp3' else 'MP4')
    def break_reads():
        def fail(*args, **kwargs):
            raise OSError('injected read failure')
        monkeypatch.setattr(module, 'ID3' if request.param == 'mp3' else 'MP4', fail)
    return win, paths, errors, successes, break_reads


@pytest.mark.parametrize('existing', [False, True])
def test_selection_failure_preserves_context(setup, existing):
    win, paths, errors, _, fail = setup
    if existing:
        win.file_list.select_files([str(paths[0])])
    baseline = win.current_metadata
    fail()
    win.file_list.select_files([str(paths[1])])
    assert errors
    assert win.current_metadata is baseline
    assert win.selected_files == ([str(paths[0])] if existing else [])
    assert win.file_list.selected_paths_in_row_order() == win.selected_files


@pytest.mark.parametrize('multiple', [False, True])
def test_panel_readback_failure(setup, monkeypatch, qtbot, multiple):
    import audio_metadata_editor.ui.main_window as module
    win, paths, errors, successes, fail = setup
    win.file_list.select_files([str(p) for p in paths[:2 if multiple else 1]])
    baseline = win.current_metadata
    qtbot.keyClicks(win.artist_edit, 'Pending')
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    original = getattr(module, writer_name)
    def write_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        fail()
    monkeypatch.setattr(module, writer_name, write_then_fail)
    win._save_changes()
    assert errors and not successes
    assert 'readback' in errors[0][2].lower()
    assert win.current_metadata is baseline
    assert win.artist_edit.text() == 'Pending'
    assert win._has_unsaved_changes()


def test_field_readback_failure(setup, monkeypatch):
    import audio_metadata_editor.ui.main_window as module
    win, paths, errors, _, fail = setup
    win.file_list.select_files([str(paths[0])])
    baseline = win.current_metadata
    original = module.write_metadata
    def write_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        fail()
    monkeypatch.setattr(module, 'write_metadata', write_then_fail)
    win._save_table_cell(str(paths[0]), 2, 'Changed')
    assert not win.file_list.cell_save_succeeded
    assert errors and 'readback' in errors[0][2].lower()
    assert win.current_metadata is baseline
    assert win.title_edit.text() == 'Original'


@pytest.mark.parametrize('operation', ['copy', 'undo', 'remove', 'paste', 'selection'])
def test_nonwrite_operations_preserve_pending_on_read_failure(setup, monkeypatch, qtbot, operation):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import Metadata, MetadataReadError
    from PySide6.QtWidgets import QDialog
    win, paths, errors, _, _ = setup
    selected = paths[:1] if operation == 'copy' else paths[:2]
    win.file_list.select_files([str(p) for p in selected])
    qtbot.keyClicks(win.artist_edit, 'Pending')
    clipboard = Metadata(title='Copied')
    win.metadata_clipboard = clipboard
    baseline = win.current_metadata
    before = win._get_edited_metadata()
    def fail(path):
        raise MetadataReadError(path, 'injected')
    monkeypatch.setattr(module, 'read_metadata', fail)
    if operation == 'paste':
        monkeypatch.setattr(module.PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
        monkeypatch.setattr(module.PasteFieldsDialog, 'selected_fields', property(lambda self: {'title'}))
        win._paste_metadata()
    elif operation == 'selection':
        win.file_list.select_files([str(paths[2])])
    else:
        getattr(win, {'copy': '_copy_metadata', 'undo': '_undo_changes', 'remove': '_remove_artwork'}[operation])()
    assert errors
    assert win.current_metadata is baseline
    assert win._get_edited_metadata() == before
    assert win.metadata_clipboard is clipboard
    assert set(win.selected_files) == set(map(str, selected))
    assert win._has_unsaved_changes()


@pytest.mark.parametrize('phase', ['prewrite', 'readback', 'final_refresh'])
def test_multi_save_stops_without_rollback(setup, monkeypatch, qtbot, phase):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths, errors, successes, _ = setup
    win.file_list.select_files([str(p) for p in paths])
    qtbot.keyClicks(win.artist_edit, 'Pending')
    real_read = module.read_metadata
    calls = 0
    def fail_later(path):
        nonlocal calls
        calls += 1
        # Per file: preservation read, write, readback; final refresh follows.
        if calls == {'prewrite': 3, 'readback': 4, 'final_refresh': 7}[phase]:
            raise MetadataReadError(path, 'injected')
        return real_read(path)
    monkeypatch.setattr(module, 'read_metadata', fail_later)
    win._save_changes()
    assert errors and not successes
    assert 'rollback' in errors[0][2].lower()
    assert win.artist_edit.text() == 'Pending'
    assert 'artist' in win.multi_edit_fields
    count = {'prewrite': 1, 'readback': 2, 'final_refresh': 3}[phase]
    for i, path in enumerate(paths):
        assert real_read(path).artist == ('Pending' if i < count else '')


@pytest.mark.parametrize('operation', ['enter', 'auto'])
def test_immediate_readback_stops_and_can_verify_without_rewrite(setup, monkeypatch, qtbot, operation):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import MetadataReadError
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog
    win, paths, errors, _, _ = setup
    win.file_list.setCurrentCell(0, 1)
    baseline = win.current_metadata
    if operation == 'auto':
        win.file_list.select_files([str(p) for p in paths])
    real_read, real_write = module.read_metadata, module.write_metadata
    written = []
    def write(path, *args, **kwargs):
        real_write(path, *args, **kwargs)
        written.append(path)
    def read(path):
        if path in written:
            raise MetadataReadError(path, 'injected')
        return real_read(path)
    monkeypatch.setattr(module, 'write_metadata', write)
    monkeypatch.setattr(module, 'read_metadata', read)
    if operation == 'enter':
        win.show()
        table = win.file_list
        table.editItem(table.item(0, 1))
        editor = table.focusWidget()
        editor.selectAll()
        qtbot.keyClicks(editor, '8')
        qtbot.keyClick(editor, Qt.Key_Return)
        qtbot.wait(10)
        assert table.currentRow() == 0
        assert not table.cell_save_succeeded
    else:
        monkeypatch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
        monkeypatch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: 8))
        win._auto_number_tracks()
    assert written == paths[:1]
    assert errors and 'readback' in errors[0][2].lower()
    assert win.current_metadata is baseline
    assert baseline.track_number is None
    assert win._has_unsaved_changes()
    assert real_read(paths[0]).track_number == 8
    assert real_read(paths[1]).track_number is None
    monkeypatch.setattr(module, 'read_metadata', real_read)
    win._save_changes()
    assert written == paths[:1]  # Verification retry never repeats the write.
    assert not win._has_unsaved_changes()


def test_directory_skips_bad_file_and_reports(setup, tmp_path):
    win, paths, errors, _, _ = setup
    paths[1].write_bytes(b'corrupt')
    win._directory_selected(tmp_path)
    assert errors and str(paths[1]) in errors[0][2]
    assert win.file_list.rowCount() == 2
    assert win.current_metadata is None
    assert win.selected_files == []
    assert {win.file_list.item(r, 0).data(256) for r in range(2)} == {str(paths[0]), str(paths[2])}


def test_optional_indicator_failure_keeps_previous_marks(setup, monkeypatch):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths, errors, _, _ = setup
    win.file_list.select_files([str(p) for p in paths[:2]])
    win.multi_edit_artwork = True
    win.file_list.set_dirty_files([paths[0]])
    before = [win.file_list.item(r, 0).text() for r in range(3)]
    def fail(path):
        raise MetadataReadError(path, 'injected')
    monkeypatch.setattr(module, 'read_metadata', fail)
    win._update_dirty_indicators()
    assert not errors
    assert [win.file_list.item(r, 0).text() for r in range(3)] == before
    assert 'injected' in win.statusBar().currentMessage()


def test_discard_reload_failure_blocks_directory_change(setup, qtbot, monkeypatch, tmp_path):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths, errors, _, _ = setup
    win.file_list.select_files([str(p) for p in paths[:2]])
    qtbot.keyClicks(win.artist_edit, 'Pending')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Discard)
    def fail(path):
        raise MetadataReadError(path, 'injected')
    monkeypatch.setattr(module, 'read_metadata', fail)
    destination = tmp_path / 'empty'
    destination.mkdir()
    win._directory_selected(destination)
    assert errors
    assert win.selected_files == list(map(str, paths[:2]))
    assert win.artist_edit.text() == 'Pending'
    assert win.file_list.rowCount() == 3


def test_verification_retry_preserves_new_pending_edits(setup, monkeypatch):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths, errors, _, _ = setup
    win.file_list.select_files([str(paths[0])])
    real_write, real_read = module.write_metadata, module.read_metadata
    def fail(path):
        raise MetadataReadError(path, 'injected')
    def write_then_fail(*args, **kwargs):
        real_write(*args, **kwargs)
        monkeypatch.setattr(module, 'read_metadata', fail)
    monkeypatch.setattr(module, 'write_metadata', write_then_fail)
    win._save_table_cell(str(paths[0]), 1, '8')
    win._save_changes()  # Verification still fails; neither baseline nor intent is cleared.
    assert len(errors) == 2
    assert win.current_metadata.track_number is None
    assert win._has_unsaved_changes()
    win.track_edit.setText('13')
    win.artist_edit.setText('New pending edit')
    monkeypatch.setattr(module, 'read_metadata', real_read)
    win._save_changes()
    assert real_read(paths[0]).track_number == 13
    assert real_read(paths[0]).artist == 'New pending edit'
    assert not win._has_unsaved_changes()
