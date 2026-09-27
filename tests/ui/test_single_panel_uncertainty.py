"""Single-panel persistence uncertainty must outlive stale baseline equality."""
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QMessageBox

from audio_metadata_editor.metadata import (
    Metadata, MetadataReadError, read_metadata, write_mp3_metadata, write_m4b_metadata,
)
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    writer = write_mp3_metadata if request.param == 'mp3' else write_m4b_metadata
    paths = [tmp_path / f'{name}.{request.param}' for name in 'ab']
    for path in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        writer(path, Metadata(title='A', artist='artist', track_number=4, track_total=17,
                              disc_number=1, disc_total=5),
               artwork=b'old cover', artwork_mime='image/jpeg')
    win = module.MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.root_path = tmp_path
    win._populate_root()
    win.file_list.setSortingEnabled(False)
    win.file_list.setCurrentCell(0, 2)
    s = SimpleNamespace(win=win, paths=paths, writer=writer, stage=None,
                        writes=[], reads=[], errors=[], successes=[])
    def write(path, metadata, **kwargs):
        s.writes.append((Path(path), set(kwargs['fields']), dict(kwargs)))
        if s.stage == 'before':
            raise OSError('injected before write')
        writer(path, metadata, **kwargs)
        if s.stage == 'after':
            raise OSError('injected after write')
    def read(path):
        s.reads.append(Path(path))
        if s.stage == 'reload' or (s.stage == 'readback' and s.writes):
            raise MetadataReadError(path, 'injected read failure')
        return read_metadata(path)
    monkeypatch.setattr(module, 'write_mp3_metadata', write)
    monkeypatch.setattr(module, 'write_m4b_metadata', write)
    monkeypatch.setattr(module, 'read_metadata', read)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: s.errors.append(args))
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: s.successes.append(args))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: s.errors.append(args))
    return s


def fail_save(s, stage='readback'):
    s.win.title_edit.setText('new')
    s.stage = stage
    s.win._save_changes()
    assert s.errors and not s.successes
    s.stage = None


@pytest.mark.parametrize('stage', ['before', 'after', 'readback', 'success'])
@pytest.mark.parametrize('retry', ['A', 'new', 'newer', ''])
def test_failure_stage_and_current_intent_retry(setup, stage, retry):
    s = setup
    win = s.win
    win.title_edit.setText('new')
    s.stage = stage
    win._save_changes()
    verified = stage == 'success'
    assert read_metadata(s.paths[0]).title == ('A' if stage == 'before' else 'new')
    assert win.current_metadata.title == ('new' if verified else 'A')
    assert win.title_edit.text() == 'new'
    assert win.file_list.item(0, 2).text() == ('new' if verified else 'A')
    assert win.pending_artwork == b'old cover' and not win.artwork_edited
    assert not win._unverified_fields
    assert win._unresolved_single_fields == (set() if verified else {'title'})
    assert win._has_unsaved_changes() == (not verified)
    # There is no separate MainWindow pre-write read in this workflow.
    assert len(s.reads) == (1 if stage in ('success', 'readback') else 0)
    win.title_edit.setText(retry)
    assert win._has_unsaved_changes() == (not verified or retry != 'new')
    s.stage = None
    s.writes.clear()
    win._save_changes()
    assert read_metadata(s.paths[0]).title == retry
    assert not win._has_unsaved_changes()
    assert all(fields == {'title'} for _, fields, _ in s.writes)
    assert win.current_metadata == read_metadata(s.paths[0])


@pytest.mark.parametrize('stage', ['before', 'after', 'readback'])
def test_multiple_fields_restore_one_change_other(setup, stage):
    s = setup
    s.win.artist_edit.setText('attempted artist')
    fail_save(s, stage)
    s.win.title_edit.setText('A')
    s.win.artist_edit.setText('newer artist')
    s.writes.clear()
    s.win._save_changes()
    saved = read_metadata(s.paths[0])
    assert (saved.title, saved.artist) == ('A', 'newer artist')
    assert s.writes[0][1] == {'title', 'artist'}
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('field,editor,original', [
    ('track_number', 'track_edit', 4), ('track_total', 'track_total_edit', 17),
    ('disc_number', 'disc_edit', 1), ('disc_total', 'disc_total_edit', 5),
])
@pytest.mark.parametrize('retry', ['original', 'different', 'invalid'])
def test_numeric_component_retry(setup, field, editor, original, retry):
    s = setup
    widget = getattr(s.win, editor)
    baseline = read_metadata(s.paths[0])
    widget.setText('8')
    s.stage = 'readback'
    s.win._save_changes()
    s.stage = None
    assert s.win._unresolved_single_fields == {field}
    widget.setText(str(original) if retry == 'original' else '9' if retry == 'different' else 'bad')
    assert s.win._has_unsaved_changes()
    s.writes.clear()
    s.win._save_changes()
    if retry == 'invalid':
        assert not s.writes
        assert widget.selectedText() == 'bad'
        assert s.win._has_unsaved_changes()
        widget.setText(str(original))
        s.win._save_changes()
    expected = 9 if retry == 'different' else original
    setattr(baseline, field, expected)
    assert read_metadata(s.paths[0]) == baseline
    assert s.writes[0][1] == {field}
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('stage', ['before', 'after', 'readback'])
@pytest.mark.parametrize('action,reply', [
    (action, reply) for action in ('single', 'multi', 'directory', 'refresh', 'close', 'undo')
    for reply in ('save', 'discard', 'cancel', 'failed_save', 'failed_discard')
    if action != 'undo' or reply in ('discard', 'failed_discard')
])
def test_guards_after_restoration(setup, monkeypatch, tmp_path, stage, action, reply):
    s = setup
    fail_save(s, stage)
    s.win.title_edit.setText('A')
    s.writes.clear()
    s.stage = {'failed_save': 'after', 'failed_discard': 'reload'}.get(reply)
    prompts = []
    choice = {'save': QMessageBox.Save, 'failed_save': QMessageBox.Save,
              'discard': QMessageBox.Discard, 'failed_discard': QMessageBox.Discard,
              'cancel': QMessageBox.Cancel}[reply]
    def answer(*args):
        prompts.append(args)
        return choice
    monkeypatch.setattr(QMessageBox, 'question', answer)
    event = QCloseEvent()
    if action in ('single', 'multi'):
        s.win.file_list.select_files([str(p) for p in (s.paths[1:] if action == 'single' else s.paths)])
    elif action == 'directory':
        directory = tmp_path / 'empty'
        directory.mkdir()
        s.win._directory_selected(directory)
    elif action == 'refresh':
        s.win._refresh_tree()
    elif action == 'close':
        s.win.closeEvent(event)
    else:
        s.win._undo_changes()
    accepted = reply in ('save', 'discard') or (action == 'close' and reply == 'failed_discard')
    if action == 'close':
        assert event.isAccepted() == accepted
    if not accepted:
        assert s.win.selected_files == [str(s.paths[0])]
        assert s.win.title_edit.text() == 'A'
        assert s.win.current_metadata.title == 'A'
        assert s.win._has_unsaved_changes()
    elif action != 'close' or reply == 'save':
        assert not s.win._has_unsaved_changes()
    if reply in ('discard', 'cancel', 'failed_discard'):
        assert not s.writes
    assert read_metadata(s.paths[0]).title == (
        'A' if stage == 'before' or reply in ('save', 'failed_save') else 'new')
    if action == 'undo' and reply == 'discard':
        assert s.win.current_metadata == read_metadata(s.paths[0])
        assert s.win.file_list.item(0, 2).text() == s.win.current_metadata.title


@pytest.mark.parametrize('stage', ['before', 'after', 'readback'])
@pytest.mark.parametrize('action', ['replace', 'same', 'remove', 'absent_restore'])
def test_artwork_uncertainty(setup, monkeypatch, stage, action):
    s = setup
    if action == 'absent_restore':
        s.writer(s.paths[0], read_metadata(s.paths[0]), fields=set(), artwork=None)
        s.win._file_selected(str(s.paths[0]))
        # Removing an already absent cover is still a no-op.
        s.win._remove_artwork()
        assert not s.win._has_unsaved_changes()
    monkeypatch.setattr(module.PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.PasteFieldsDialog, 'selected_fields', property(lambda self: {'artwork'}))
    attempted = None if action == 'remove' else b'old cover' if action == 'same' else b'new cover'
    s.win.metadata_clipboard = Metadata(artwork=attempted, artwork_mime='image/jpeg' if attempted else '')
    s.win._paste_metadata()
    s.stage = stage
    s.win._save_changes()
    assert s.errors
    assert s.win._unresolved_single_fields == {'artwork'}
    s.stage = None
    # Restore old preview, including cancelling an addition against a stale
    # absent baseline after that addition may already have reached disk.
    retry = None if action in ('remove', 'absent_restore') else b'old cover'
    s.win.metadata_clipboard = Metadata(artwork=retry, artwork_mime='image/jpeg' if retry else '')
    s.win._paste_metadata()
    if action == 'absent_restore':
        s.win._remove_artwork()  # This resets ordinary intent against old baseline.
    assert s.win._has_unsaved_changes()
    s.writes.clear()
    s.win._save_changes()
    assert len(s.writes) == 1 and s.writes[0][1] == set()
    assert s.writes[0][2]['artwork'] == retry
    assert read_metadata(s.paths[0]).artwork == retry
    assert not s.win._has_unsaved_changes()


def test_final_presentation_failure_characterization(setup, monkeypatch):
    s = setup
    original = s.win.file_list.update_file_metadata
    def fail(*args):
        raise RuntimeError('injected presentation failure')
    monkeypatch.setattr(s.win.file_list, 'update_file_metadata', fail)
    s.win.title_edit.setText('new')
    with pytest.raises(RuntimeError, match='presentation'):
        s.win._save_changes()
    assert read_metadata(s.paths[0]).title == 'new'
    assert s.win.current_metadata.title == 'new'
    assert s.win.title_edit.text() == 'new'
    assert s.win.file_list.item(0, 2).text() == 'A'
    assert s.win._has_unsaved_changes()
    monkeypatch.setattr(s.win.file_list, 'update_file_metadata', original)
    s.win._save_changes()
    assert s.win.file_list.item(0, 2).text() == 'new'
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('same_field', [False, True])
def test_table_verification_does_not_drop_panel_retry(setup, monkeypatch, same_field):
    s = setup
    fail_save(s)
    s.win.title_edit.setText('A')
    field, column, value = ('title', 2, 'table') if same_field else ('track_number', 1, '8')
    # Inject failure only after the immediate writer has run.
    real_write = module.write_metadata
    def write(*args, **kwargs):
        real_write(*args, **kwargs)
        s.stage = 'readback'
    monkeypatch.setattr(module, 'write_metadata', write)
    s.win._save_table_cell(str(s.paths[0]), column, value)
    assert s.win._unverified_fields == {s.paths[0]: {field}}
    s.stage = None
    s.writes.clear()
    s.win._save_changes()
    assert read_metadata(s.paths[0]).title == 'A'
    assert len(s.writes) == 1 and s.writes[0][1] == {'title'}
    assert not s.win._unverified_fields
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('other_field', [False, True])
def test_auto_number_resolves_only_track(setup, monkeypatch, other_field):
    s = setup
    s.win.track_edit.setText('8')
    if other_field:
        s.win.title_edit.setText('new')
    s.stage = 'readback'
    s.win._save_changes()
    s.stage = None
    s.win.track_edit.setText('4')
    if other_field:
        s.win.title_edit.setText('A')
    monkeypatch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: 12))
    s.win._auto_number_tracks()
    assert read_metadata(s.paths[0]).track_number == 12
    assert s.win.track_edit.text() == '12'
    assert s.win._has_unsaved_changes() == other_field
    if other_field:
        s.writes.clear()
        s.win._save_changes()
        assert s.writes[0][1] == {'title'}
        assert read_metadata(s.paths[0]).title == 'A'


def test_internal_writer_read_failure_is_conservative(setup, monkeypatch):
    import importlib
    s = setup
    handler = importlib.import_module(f'audio_metadata_editor.metadata.{s.paths[0].suffix[1:]}')
    constructor = 'ID3' if s.paths[0].suffix == '.mp3' else 'MP4'
    before = s.paths[0].read_bytes()
    s.win.title_edit.setText('new')
    def fail(*args):
        raise OSError('injected internal tag read failure')
    with monkeypatch.context() as patch:
        patch.setattr(handler, constructor, fail)
        s.win._save_changes()
    assert s.paths[0].read_bytes() == before
    assert not s.reads and len(s.writes) == 1
    assert s.win.current_metadata.title == 'A'
    assert s.win.file_list.item(0, 2).text() == 'A'
    assert s.win.pending_artwork == b'old cover'
    assert s.win._unresolved_single_fields == {'title'}
    s.win.title_edit.setText('A')
    assert s.win._has_unsaved_changes()
    assert 'may have changed' in s.errors[-1][2]
    s.writes.clear()
    s.win._undo_changes()
    assert not s.writes and not s.win._has_unsaved_changes()


@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_actual_enter_keeps_panel_guard(setup, qtbot, monkeypatch, reply):
    s = setup
    s.win.show()
    fail_save(s)
    s.win.title_edit.setText('A')
    prompts = []
    def answer(*args):
        assert read_metadata(s.paths[0]).artist == 'table artist'
        prompts.append(args)
        return reply
    monkeypatch.setattr(QMessageBox, 'question', answer)
    table = s.win.file_list
    table.setCurrentCell(0, 3)
    table.editItem(table.item(0, 3))
    editor = table.focusWidget()
    editor.setText('table artist')
    qtbot.keyClick(editor, Qt.Key_Return)
    qtbot.wait(1)
    assert len(prompts) == 1
    assert read_metadata(s.paths[0]).title == ('A' if reply == QMessageBox.Save else 'new')
    assert read_metadata(s.paths[0]).artist == 'table artist'
    assert s.win._has_unsaved_changes() == (reply == QMessageBox.Cancel)
    assert s.win.current_file == s.paths[0 if reply == QMessageBox.Cancel else 1]
    if reply == QMessageBox.Cancel:
        assert s.win._unresolved_single_fields == {'title'}
        assert s.win.title_edit.text() == 'A'


@pytest.mark.parametrize('failed', [False, True])
def test_explicit_reload_accepts_disk_truth(setup, failed):
    s = setup
    fail_save(s)
    s.win.title_edit.setText('A')
    if failed:
        s.stage = 'reload'
    s.writes.clear()
    assert s.win._file_selected(str(s.paths[0])) == (not failed)
    assert not s.writes
    assert s.win._has_unsaved_changes() == failed
    assert s.win.title_edit.text() == ('A' if failed else 'new')
    assert s.win.file_list.item(0, 2).text() == ('A' if failed else 'new')


def test_successful_table_same_field_resolves_only_that_field(setup):
    s = setup
    s.win.artist_edit.setText('attempted artist')
    fail_save(s)
    s.win.title_edit.setText('A')
    s.win._save_table_cell(str(s.paths[0]), 2, 'explicit table title')
    assert s.win.file_list.cell_save_succeeded
    assert s.win._unresolved_single_fields == {'artist'}
    assert s.win.title_edit.text() == 'explicit table title'
    assert s.win._has_unsaved_changes()
    s.win.artist_edit.setText('artist')
    s.writes.clear()
    s.win._save_changes()
    assert s.writes[0][1] == {'artist'}
    assert read_metadata(s.paths[0]).title == 'explicit table title'
    assert not s.win._has_unsaved_changes()
