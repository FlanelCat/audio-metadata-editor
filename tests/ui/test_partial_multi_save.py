"""Selection-wide retry and unresolved intent, on temporary MP3/M4B copies."""
from collections import Counter
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
    paths = [tmp_path / f'{letter}.{request.param}' for letter in 'ABCD']
    for path in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        writer(path, Metadata(title='old', artist='artist', track_number=4, track_total=17,
                              disc_number=1, disc_total=5),
               artwork=b'old cover', artwork_mime='image/jpeg')
    win = module.MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.root_path = tmp_path
    win._populate_root()
    win.file_list.setSortingEnabled(False)
    win.file_list.select_files([str(p) for p in paths])
    state = SimpleNamespace(win=win, paths=paths, writer=writer, fail=None,
                            trace=[], writes=[], errors=[], successes=[], counts=Counter())
    def read(path):
        path = Path(path)
        state.trace.append('R' + path.stem)
        state.counts[path.stem] += 1
        if state.fail == 'reload' or (
            path == paths[2] and
            ((state.fail == 'prewrite' and state.counts[path.stem] == 1) or
             (state.fail == 'readback' and state.counts[path.stem] == 2))
        ) or (state.fail == 'final' and path == paths[0] and state.counts[path.stem] == 3):
            raise MetadataReadError(path, 'injected read failure')
        return read_metadata(path)
    def write(path, metadata, **kwargs):
        state.trace.append('W' + path.stem)
        state.writes.append((path, set(kwargs['fields']), dict(kwargs)))
        if path == paths[2] and state.fail == 'writer':
            raise OSError('injected writer failure')
        writer(path, metadata, **kwargs)
        if path == paths[2] and state.fail == 'after_write':
            raise OSError('injected exception after writing')
    monkeypatch.setattr(module, 'read_metadata', read)
    monkeypatch.setattr(module, 'write_mp3_metadata', write)
    monkeypatch.setattr(module, 'write_m4b_metadata', write)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: state.errors.append(a))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: state.successes.append(a))
    return state


def edit(qtbot, widget, value):
    widget.selectAll()
    if value:
        qtbot.keyClicks(widget, value)
    else:
        qtbot.keyClick(widget, Qt.Key_Backspace)


def reset_trace(state, failure=None):
    state.fail = failure
    state.trace.clear()
    state.writes.clear()
    state.counts.clear()
    state.successes.clear()


def save_failure(state, qtbot, failure='writer'):
    edit(qtbot, state.win.title_edit, 'new')
    reset_trace(state, failure)
    state.win._save_changes()
    assert state.errors and not state.successes
    assert state.win.multi_edit_fields == {'title'}
    assert state.win._has_unsaved_changes()


FULL_RETRY = 'RA WA RA RB WB RB RC WC RC RD WD RD RA RB RC RD'.split()


@pytest.mark.parametrize('stage,count', [('prewrite', 2), ('writer', 2),
                                         ('after_write', 3), ('readback', 3), ('final', 4)])
def test_failure_stages_and_selection_wide_retry(setup, qtbot, stage, count):
    s = setup
    save_failure(s, qtbot, stage)
    assert [read_metadata(p).title for p in s.paths] == ['new'] * count + ['old'] * (4-count)
    message = s.errors[-1][2]
    assert str(s.paths[0] if stage == 'final' else s.paths[2]) in message
    assert f'Writes completed and verified: {4 if stage == "final" else 2}.' in message
    assert 'Save again reapplies the current pending changes to the selected files.' in message
    assert 'rollback' in message
    if stage != 'final':
        assert 'Files later in the save order were not attempted.' in message
    if stage in ('readback', 'final'):
        assert 'Write may have succeeded' in message
    shown = 4 if stage == 'final' else 2
    assert [s.win.file_list.item(i, 2).text() for i in range(4)] == ['new'] * shown + ['old'] * (4-shown)
    edit(qtbot, s.win.artist_edit, 'other')
    edit(qtbot, s.win.artist_edit, 'artist')
    assert s.win.multi_edit_fields == {'title'}
    assert s.win._has_unsaved_changes()
    assert all(s.win.file_list.item(i, 0).text().startswith('*') for i in range(4))
    reset_trace(s)
    s.win._save_changes()
    assert s.trace == FULL_RETRY
    assert not s.win._unresolved_multi_fields
    assert all(fields == {'title'} for _, fields, _ in s.writes)
    assert all(read_metadata(p).title == 'new' for p in s.paths)
    assert not s.win._has_unsaved_changes()
    edit(qtbot, s.win.title_edit, 'other')
    edit(qtbot, s.win.title_edit, 'new')
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('external', [False, True])
@pytest.mark.parametrize('action', ['unrelated', 'restore_failed', 'old_value', 'clear'])
def test_final_read_uncertainty_survives_edits(setup, qtbot, external, action):
    s = setup
    save_failure(s, qtbot, 'final')
    if external:
        metadata = read_metadata(s.paths[0])
        metadata.title = 'external'
        metadata.album = 'external album'
        s.writer(s.paths[0], metadata, fields={'title', 'album'})
    reset_trace(s)
    expected = 'new'
    if action == 'unrelated':
        edit(qtbot, s.win.artist_edit, 'other')
        edit(qtbot, s.win.artist_edit, 'artist')
    else:
        edit(qtbot, s.win.title_edit, 'other')
        expected = {'restore_failed': 'new', 'old_value': 'old', 'clear': ''}[action]
        edit(qtbot, s.win.title_edit, expected)
    assert s.trace == []  # Recalculation uses accepted state, without speculative reads.
    assert s.win.multi_edit_fields == {'title'}
    assert s.win._has_unsaved_changes()
    s.win._save_changes()
    assert s.trace == FULL_RETRY
    assert all(read_metadata(p).title == expected for p in s.paths)
    assert read_metadata(s.paths[0]).album == ('external album' if external else '')
    assert not s.win._has_unsaved_changes()


def test_new_value_after_partial_failure_applies_to_every_file(setup, qtbot):
    s = setup
    save_failure(s, qtbot)
    edit(qtbot, s.win.title_edit, 'newer')
    reset_trace(s)
    s.win._save_changes()
    assert s.trace == FULL_RETRY
    assert all(read_metadata(p).title == 'newer' for p in s.paths)


@pytest.mark.parametrize('fields', [('title', 'artist'), ('track_number',), ('disc_number',)])
def test_multiple_fields_and_numeric_pairs(setup, qtbot, fields):
    s = setup
    editors = {'title': s.win.title_edit, 'artist': s.win.artist_edit,
               'track_number': s.win.track_edit, 'disc_number': s.win.disc_edit}
    for field in fields:
        edit(qtbot, editors[field], '8' if field.endswith('_number') else 'new')
    reset_trace(s, 'writer')
    s.win._save_changes()
    for i, path in enumerate(s.paths):
        metadata = read_metadata(path)
        for field in fields:
            original = {'title': 'old', 'artist': 'artist', 'track_number': 4, 'disc_number': 1}[field]
            assert getattr(metadata, field) == ((8 if field.endswith('_number') else 'new') if i < 2 else original)
        assert (metadata.track_total, metadata.disc_total) == (17, 5)
    reset_trace(s)
    s.win._save_changes()
    assert s.trace == FULL_RETRY
    assert all(written == set(fields) for _, written, _ in s.writes)
    for path in s.paths:
        metadata = read_metadata(path)
        for field in fields:
            assert getattr(metadata, field) == (8 if field.endswith('_number') else 'new')
        assert (metadata.track_total, metadata.disc_total) == (17, 5)
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('target,reply', [
    (target, reply)
    for target in ('single', 'multi', 'directory', 'close', 'undo')
    for reply in ('save', 'discard', 'cancel', 'failed_save', 'failed_discard')
    if target != 'undo' or reply in ('discard', 'failed_discard')
])
def test_navigation_after_partial_failure(setup, qtbot, monkeypatch, tmp_path, target, reply):
    s = setup
    save_failure(s, qtbot)
    reset_trace(s, {'failed_save': 'writer', 'failed_discard': 'reload'}.get(reply))
    choice = {'save': QMessageBox.Save, 'failed_save': QMessageBox.Save,
              'discard': QMessageBox.Discard, 'failed_discard': QMessageBox.Discard,
              'cancel': QMessageBox.Cancel}[reply]
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: choice)
    event = QCloseEvent()
    if target == 'single':
        s.win.file_list.select_files([str(s.paths[3])])
    elif target == 'multi':
        s.win.file_list.select_files([str(p) for p in s.paths[2:]])
    elif target == 'directory':
        directory = tmp_path / 'empty'
        directory.mkdir()
        s.win._directory_selected(directory)
    elif target == 'close':
        s.win.closeEvent(event)
    else:
        s.win._undo_changes()
    accepted = reply in ('save', 'discard') or (target == 'close' and reply == 'failed_discard')
    if target == 'close':
        assert event.isAccepted() == accepted
    if not accepted:
        assert s.win.selected_files == [str(p) for p in s.paths]
        assert s.win.file_list.selected_paths_in_row_order() == s.win.selected_files
        assert s.win.title_edit.text() == 'new'
        assert s.win.multi_edit_fields == {'title'}
        assert s.win._has_unsaved_changes()
    elif target != 'close' or reply == 'save':
        assert not s.win._has_unsaved_changes()
        assert not s.win._unresolved_multi_fields
    assert [read_metadata(p).title for p in s.paths] == (['new'] * 4 if reply == 'save' else ['new', 'new', 'old', 'old'])
    if reply in ('discard', 'cancel', 'failed_discard'):
        assert not s.writes
    if target == 'undo' and reply == 'discard':
        assert s.win.title_edit.text() == ''
        assert s.win.title_edit.placeholderText()
        assert [s.win.file_list.item(i, 2).text() for i in range(4)] == ['new', 'new', 'old', 'old']
        # Comparison is ordinary again after a successful reload.
        edit(qtbot, s.win.artist_edit, 'other')
        edit(qtbot, s.win.artist_edit, 'artist')
        assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('removal', [False, True])
@pytest.mark.parametrize('stage', ['writer', 'final'])
def test_artwork_retry(setup, qtbot, monkeypatch, removal, stage):
    s = setup
    monkeypatch.setattr(module.PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.PasteFieldsDialog, 'selected_fields', property(lambda self: {'artwork'}))
    s.win.metadata_clipboard = Metadata(artwork=None if removal else b'old cover',
                                       artwork_mime='' if removal else 'image/jpeg')
    s.win._paste_metadata()  # Same-cover replacement is still explicit intent.
    reset_trace(s, stage)
    s.win._save_changes()
    assert s.errors and s.win.multi_edit_artwork
    edit(qtbot, s.win.artist_edit, 'other')
    edit(qtbot, s.win.artist_edit, 'artist')
    assert s.win._has_unsaved_changes()
    assert all(s.win.file_list.item(i, 0).text().startswith('*') for i in range(4))
    reset_trace(s)
    s.win._save_changes()
    expected_paths = s.paths if not removal else (s.paths[2:] if stage == 'writer' else [])
    assert [p for p, _, _ in s.writes] == expected_paths
    assert all(read_metadata(p).artwork == (None if removal else b'old cover') for p in s.paths)
    assert not s.win._has_unsaved_changes()


def test_mixed_artwork_removal_retry_skips_absent_targets(setup):
    s = setup
    for path in (s.paths[0], s.paths[3]):
        s.writer(path, read_metadata(path), fields=set(), artwork=None)
    s.win._remove_artwork()
    reset_trace(s, 'writer')
    s.win._save_changes()
    assert s.errors
    assert [p for p, _, _ in s.writes] == s.paths[1:3]
    assert [read_metadata(p).artwork for p in s.paths] == [None, None, b'old cover', None]
    reset_trace(s)
    s.win._save_changes()
    assert [p for p, _, _ in s.writes] == [s.paths[2]]
    assert all(read_metadata(p).artwork is None for p in s.paths)
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('action', ['remove', 'paste'])
def test_absent_artwork_action_cannot_clear_unresolved_removal(setup, monkeypatch, action):
    s = setup
    s.win._remove_artwork()
    reset_trace(s, 'final')
    s.win._save_changes()
    assert all(read_metadata(p).artwork is None for p in s.paths)
    reset_trace(s)
    if action == 'remove':
        s.win._remove_artwork()
    else:
        monkeypatch.setattr(module.PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
        monkeypatch.setattr(module.PasteFieldsDialog, 'selected_fields', property(lambda self: {'artwork'}))
        s.win.metadata_clipboard = Metadata()
        s.win._paste_metadata()
    assert s.win.multi_edit_artwork
    assert s.win._has_unsaved_changes()
    s.win._save_changes()
    assert not s.writes
    assert not s.win._has_unsaved_changes()


def test_new_artwork_replacement_after_partial_failure(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(module.PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.PasteFieldsDialog, 'selected_fields', property(lambda self: {'artwork'}))
    s.win.metadata_clipboard = Metadata(artwork=b'new cover', artwork_mime='image/jpeg')
    s.win._paste_metadata()
    reset_trace(s, 'writer')
    s.win._save_changes()
    assert [read_metadata(p).artwork for p in s.paths] == [b'new cover'] * 2 + [b'old cover'] * 2
    reset_trace(s)
    s.win.metadata_clipboard = Metadata(artwork=b'newer cover', artwork_mime='image/jpeg')
    s.win._paste_metadata()
    reset_trace(s)
    s.win._save_changes()
    assert s.trace == FULL_RETRY
    assert all(read_metadata(p).artwork == b'newer cover' for p in s.paths)
    assert not s.win._has_unsaved_changes()


@pytest.mark.parametrize('other_field', [False, True])
def test_completed_auto_number_resolves_only_track_intent(setup, qtbot, monkeypatch, other_field):
    s = setup
    edit(qtbot, s.win.track_edit, '8')
    if other_field:
        edit(qtbot, s.win.title_edit, 'new')
    reset_trace(s, 'writer')
    s.win._save_changes()
    assert s.errors
    reset_trace(s)
    monkeypatch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: 10))
    s.win._auto_number_tracks()
    assert [read_metadata(p).track_number for p in s.paths] == [10, 11, 12, 13]
    assert all(read_metadata(p).track_total == 17 for p in s.paths)
    edit(qtbot, s.win.artist_edit, 'other')
    edit(qtbot, s.win.artist_edit, 'artist')
    assert s.win.multi_edit_fields == ({'title'} if other_field else set())
    assert s.win._has_unsaved_changes() == other_field
