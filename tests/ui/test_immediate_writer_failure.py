"""Writer failure is not evidence that an immediate write left disk unchanged."""
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from audio_metadata_editor.metadata import Metadata, MetadataReadError, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{name}.{request.param}' for name in 'abc']
    for path in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        write_metadata(path, Metadata(title='A', artist='artist', track_number=4, track_total=17))
    win = module.MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.file_list.setSortingEnabled(False)
    win.file_list.load_directory(tmp_path)
    win.show()
    win.file_list.setCurrentCell(0, 2)
    s = SimpleNamespace(win=win, paths=paths, failure=paths[0], stage='after',
                        recovery_fails=False, raised=False, writes=[], errors=[])
    def write(path, metadata, *, fields):
        s.writes.append((Path(path), set(fields)))
        if path != s.failure:
            write_metadata(path, metadata, fields=fields)
            return
        if s.stage != 'before':
            if s.stage == 'different':
                for field in fields:
                    setattr(metadata, field, 27 if field == 'track_number' else 'partial')
            write_metadata(path, metadata, fields=fields)
        s.raised = True
        raise OSError('injected immediate writer failure')
    def read(path):
        if s.raised and s.recovery_fails and Path(path) == s.failure:
            raise MetadataReadError(path, 'injected recovery read failure')
        return read_metadata(path)
    monkeypatch.setattr(module, 'write_metadata', write)
    monkeypatch.setattr(module, 'read_metadata', read)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: s.errors.append(a))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    def unexpected(*args):
        pytest.fail(f'Unexpected prompt: {args[1:]}')
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    return s


def enter(s, qtbot, column, value):
    table = s.win.file_list
    table.setCurrentCell(0, column)
    table.editItem(table.item(0, column))
    editor = table.focusWidget()
    editor.setText(value)
    qtbot.keyClick(editor, Qt.Key_Return)
    qtbot.wait(1)


@pytest.mark.parametrize('column,field,value,stage,unreadable', [
    (2, 'title', 'new', 'before', False),
    (2, 'title', 'new', 'after', False),
    (2, 'title', 'new', 'different', False),
    (2, 'title', 'new', 'after', True),
    (2, 'title', 'new', 'before', True),
    (1, 'track_number', '8', 'after', False),
    (1, 'track_number', '8', 'after', True),
])
def test_enter_failure_outcomes(setup, qtbot, column, field, value, stage, unreadable):
    s = setup
    s.stage, s.recovery_fails = stage, unreadable
    path = s.paths[0]
    before = read_metadata(path)
    others = {p: p.read_bytes() for p in s.paths[1:]}
    enter(s, qtbot, column, value)
    actual = getattr(read_metadata(path), field)
    requested = int(value) if column == 1 else value
    expected = getattr(before, field) if stage == 'before' else 'partial' if stage == 'different' else requested
    assert actual == expected
    assert read_metadata(path).track_total == 17
    assert all(p.read_bytes() == data for p, data in others.items())
    assert s.writes == [(path, {field})]
    assert len(s.errors) == 1 and 'injected immediate writer failure' in s.errors[0][2]
    message = s.errors[0][2]
    outcome = 'could not verify' if unreadable or stage != 'after' else 'requested field value'
    assert outcome in message and 'No rollback was attempted' in message
    assert not s.win.file_list.cell_save_succeeded
    assert s.win.current_file == path and s.win.file_list.currentRow() == 0
    if unreadable or stage != 'after':
        assert s.win._unverified_requests == {path: {field: requested}}
        assert s.win._unverified_fields == {path: {field}}
        assert getattr(s.win.current_metadata, field) == getattr(before, field)
        assert s.win.file_list.item(0, 0).text().startswith('*')
        assert s.win._has_unsaved_changes()
        s.recovery_fails = False
        s.win._save_changes()
        if stage != 'after':
            assert s.win._unverified_fields == {path: {field}}
            assert s.win._unverified_requests == {path: {field: requested}}
            assert 'did not match' in s.errors[-1][2]
            s.win._undo_changes()  # Explicitly accept disk truth, without replay.
    else:
        assert 'Recovery read found' in s.errors[0][2]
    assert not s.win._unverified_fields
    assert not s.win._unverified_requests
    assert getattr(s.win.current_metadata, field) == expected
    assert getattr(s.win, 'track_edit' if column == 1 else 'title_edit').text() == str(expected)
    assert s.win.file_list.item(0, column).text() == str(expected)
    assert not s.win._has_unsaved_changes()
    assert s.writes == [(path, {field})]  # Recovery never replays the write.


@pytest.mark.parametrize('failed_row,stage,unreadable', [
    (0, 'before', False), (0, 'after', False), (0, 'different', False),
    (0, 'after', True), (1, 'after', False), (1, 'after', True),
])
def test_auto_stops_and_reports_current_outcome(setup, monkeypatch, failed_row, stage, unreadable):
    s = setup
    s.failure, s.stage, s.recovery_fails = s.paths[failed_row], stage, unreadable
    s.win.file_list.select_files([str(p) for p in s.paths])
    before = {p: p.read_bytes() for p in s.paths}
    monkeypatch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: 8))
    s.win._auto_number_tracks()
    assert s.writes == [(p, {'track_number'}) for p in s.paths[:failed_row + 1]]
    expected = [4, 4, 4]
    for row in range(failed_row):
        expected[row] = 8 + row
    expected[failed_row] = 4 if stage == 'before' else 27 if stage == 'different' else 8 + failed_row
    assert [read_metadata(p).track_number for p in s.paths] == expected
    assert all(read_metadata(p).track_total == 17 for p in s.paths)
    assert all(p.read_bytes() == before[p] for p in s.paths[failed_row + 1:])
    assert len(s.errors) == 1
    assert f'{failed_row} file(s) saved and verified' in s.errors[0][2]
    if unreadable or stage != 'after':
        assert s.win._unverified_requests == {s.failure: {'track_number': 8 + failed_row}}
        assert s.win._unverified_fields == {s.failure: {'track_number'}}
        assert s.win._has_unsaved_changes()
        s.recovery_fails = False
        s.win._save_changes()
        if stage != 'after':
            assert s.win._unverified_fields == {s.failure: {'track_number'}}
            assert s.win._unverified_requests == {s.failure: {'track_number': 8 + failed_row}}
            assert 'did not match' in s.errors[-1][2]
            s.win._undo_changes()
    else:
        assert 'Recovery read found' in s.errors[0][2]
    assert not s.win._unverified_fields
    assert not s.win._unverified_requests
    assert not s.win._has_unsaved_changes()
    assert [s.win.file_list.item(r, 1).text() for r in range(3)] == list(map(str, expected))
    assert len(s.writes) == failed_row + 1


@pytest.mark.parametrize('same_field', [False, True])
def test_recovery_preserves_pending_panel_values(setup, qtbot, same_field):
    s = setup
    widget = s.win.title_edit if same_field else s.win.artist_edit
    widget.setText('pending panel')
    enter(s, qtbot, 2, 'new')
    assert s.win.current_metadata.title == 'new'
    assert widget.text() == 'pending panel'
    assert s.win._has_unsaved_changes()
    assert not s.win._unverified_fields
    assert not s.win._unverified_requests
    assert len(s.writes) == 1


@pytest.mark.parametrize('multiple,unreadable', [(False, False), (False, True), (True, False), (True, True)])
def test_auto_recovery_preserves_overlapping_panel_uncertainty(setup, monkeypatch, qtbot, multiple, unreadable):
    s = setup
    if multiple:
        s.win.file_list.select_files([str(p) for p in s.paths])
    s.win.track_edit.selectAll()
    qtbot.keyClicks(s.win.track_edit, '6')
    writer_name = 'write_mp3_metadata' if s.paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    original = getattr(module, writer_name)
    def panel_write(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('injected panel failure')
    with monkeypatch.context() as patch:
        patch.setattr(module, writer_name, panel_write)
        s.win._save_changes()
    unresolved = s.win._unresolved_multi_fields if multiple else s.win._unresolved_single_fields
    assert unresolved == {'track_number'}
    s.win.track_edit.setText('4')
    s.errors.clear()
    s.recovery_fails = unreadable
    monkeypatch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: 8))
    s.win._auto_number_tracks()
    if unreadable:
        assert s.win._unverified_fields == {s.paths[0]: {'track_number'}}
        s.recovery_fails = False
        s.win._verify_field_saves()
    assert not s.win._unverified_fields
    assert not s.win._unverified_requests
    assert unresolved == {'track_number'}
    assert s.win.track_edit.text() == '4'
    assert s.win._has_unsaved_changes()
    assert s.writes == [(s.paths[0], {'track_number'})]
    s.win._save_changes()  # Panel retry still applies its own current intent.
    assert all(read_metadata(p).track_number == 4 for p in (s.paths if multiple else s.paths[:1]))
    assert not s.win._has_unsaved_changes()


def test_invalid_track_does_not_invoke_writer_or_establish_uncertainty(setup, qtbot):
    s = setup
    enter(s, qtbot, 1, 'invalid')
    assert not s.writes and not s.errors and not s.win._unverified_fields
    assert s.win.file_list.focusWidget().selectedText() == 'invalid'
    assert s.win.file_list.currentRow() == 0


@pytest.mark.parametrize('reply,readable', [
    (QMessageBox.Save, True), (QMessageBox.Discard, True), (QMessageBox.Cancel, True),
    (QMessageBox.Save, False), (QMessageBox.Discard, False),
])
def test_unresolved_enter_guards_selection(setup, qtbot, monkeypatch, reply, readable):
    s = setup
    s.recovery_fails = True
    enter(s, qtbot, 2, 'new')
    assert s.win._unverified_fields == {s.paths[0]: {'title'}}
    s.recovery_fails = not readable
    prompts = []
    def answer(*args):
        prompts.append(args)
        return reply
    monkeypatch.setattr(QMessageBox, 'question', answer)
    s.win.file_list.select_files([str(s.paths[1])])
    assert len(prompts) == 1
    accepted = readable and reply != QMessageBox.Cancel
    assert s.win.selected_files == [str(s.paths[1 if accepted else 0])]
    assert bool(s.win._unverified_fields) == (not accepted)
    assert s.win._has_unsaved_changes() == (not accepted)
    assert s.writes == [(s.paths[0], {'title'})]
    assert read_metadata(s.paths[0]).title == 'new'


def test_recovery_does_not_clear_other_paths(setup):
    s = setup
    s.recovery_fails = True
    s.win._save_table_cell(str(s.paths[0]), 2, 'first')
    assert s.win._unverified_fields == {s.paths[0]: {'title'}}
    s.failure = s.paths[1]
    s.recovery_fails = False
    s.win._save_table_cell(str(s.paths[1]), 2, 'second')
    assert s.win._unverified_fields == {s.paths[0]: {'title'}}
    assert s.win.file_list.item(1, 2).text() == 'second'
    s.win._save_changes()
    assert not s.win._unverified_fields
    assert not s.win._unverified_requests
    assert s.writes == [(p, {'title'}) for p in s.paths[:2]]


def test_required_read_failure_does_not_invoke_writer(setup, monkeypatch):
    s = setup
    def fail(path):
        raise MetadataReadError(path, 'injected initial read failure')
    monkeypatch.setattr(module, 'read_metadata', fail)
    s.win._save_table_cell(str(s.paths[0]), 2, 'new')
    assert not s.writes
    assert not s.win._unverified_fields
    assert not s.win._unverified_requests
    assert not s.win._has_unsaved_changes()
    assert s.win.current_metadata.title == 'A'
    assert read_metadata(s.paths[0]).title == 'A'


@pytest.mark.parametrize('stage,unreadable', [('after', False), ('different', False), ('before', False), ('after', True)])
def test_requested_value_recorded_before_writer_and_recovery(setup, monkeypatch, stage, unreadable):
    s = setup
    path = s.paths[0]
    s.stage, s.recovery_fails = stage, unreadable
    writer = module.write_metadata
    def checked_write(path, metadata, *, fields):
        assert s.win._unverified_fields == {path: {'title'}}
        assert s.win._unverified_requests == {path: {'title': 'requested'}}
        writer(path, metadata, fields=fields)
    monkeypatch.setattr(module, 'write_metadata', checked_write)
    s.win._save_table_cell(str(path), 2, 'requested')
    unresolved = unreadable or stage != 'after'
    assert s.win._unverified_fields == ({path: {'title'}} if unresolved else {})
    assert s.win._unverified_requests == ({path: {'title': 'requested'}} if unresolved else {})
    assert not s.win.file_list.cell_save_succeeded
    assert 'Write operation failed' in s.errors[-1][2]
    s.recovery_fails = False
    s.win._save_changes()
    mismatch = stage != 'after'
    assert s.win._unverified_fields == ({path: {'title'}} if mismatch else {})
    assert s.win._unverified_requests == ({path: {'title': 'requested'}} if mismatch else {})
    assert s.writes == [(path, {'title'})]
    if mismatch:
        assert 'did not match' in s.errors[-1][2]


def test_representation_preflight_creates_no_uncertainty(setup):
    s = setup
    value = 'bad\0value' if s.paths[0].suffix == '.mp3' else 'bad\ud800'
    s.win._save_table_cell(str(s.paths[0]), 2, value)
    assert not s.writes
    assert s.win._unverified_fields == {}
    assert s.win._unverified_requests == {}
    assert not s.win.file_list.cell_save_succeeded
