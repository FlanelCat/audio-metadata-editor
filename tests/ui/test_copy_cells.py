"""Directional copies snapshot selected visual targets and remain pending."""
from copy import deepcopy
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLineEdit, QMessageBox, QFileDialog

from audio_metadata_editor.metadata import Metadata, MetadataReadError, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{name}.{request.param}' for name in 'abcde']
    for i, path in enumerate(paths):
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        write_metadata(path, Metadata(title=['A', 'B', 'C', 'D', 'C'][i], artist='Original',
                                      album='Album', track_number=i + 1, track_total=17))
    win = module.MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.root_path = tmp_path
    win._populate_root()
    win.show()
    win.file_list.sortItems(0, Qt.AscendingOrder)
    win.file_list.select_files([str(p) for p in paths])
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: pytest.fail(str(a)))
    return win, paths


def row(win, path):
    return next(r for r in range(win.file_list.rowCount()) if win.file_list.item(r, 0).data(256) == str(path))


def activate(win, path, column=2):
    win.file_list.setCurrentCell(row(win, path), column, QItemSelectionModel.NoUpdate)
    win.file_list.setFocus()


def copy(win, down=True):
    (win.file_list.copy_down_action if down else win.file_list.copy_up_action).trigger()


def title(win, path):
    return win.file_list.item(row(win, path), 2).text()


def dirty(win):
    return {Path(win.file_list.item(r, 0).data(256)) for r in range(win.file_list.rowCount())
            if win.file_list.item(r, 0).text().startswith('*')}


@pytest.mark.parametrize('down', [True, False])
def test_discontinuous_middle_source(setup, down, monkeypatch):
    win, paths = setup
    win.file_list.select_files([str(paths[i]) for i in (0, 2, 3)])
    activate(win, paths[2])
    before = {p: p.read_bytes() for p in paths}
    accepted = deepcopy(win._multi_field_baselines)
    def unexpected_write(*args, **kwargs):
        pytest.fail("Copy must not invoke a metadata writer")
    monkeypatch.setattr(module, "write_metadata", unexpected_write)
    monkeypatch.setattr(module, "write_mp3_metadata", unexpected_write)
    monkeypatch.setattr(module, "write_m4b_metadata", unexpected_write)
    copy(win, down)
    target = paths[3] if down else paths[0]
    assert win._per_file_edits == {target: {'title': 'C'}}
    assert dirty(win) == {target}
    assert title(win, paths[2]) == 'C' and title(win, paths[1]) == 'B'
    assert win._multi_field_baselines == accepted
    assert win.title_edit.placeholderText()
    assert {p: p.read_bytes() for p in paths} == before


def test_matching_target_and_common_panel(setup):
    win, paths = setup
    win.file_list.select_files([str(p) for p in paths[2:]])
    activate(win, paths[2])
    copy(win)
    assert dirty(win) == {paths[3]}
    assert win.title_edit.text() == 'C' and not win.title_edit.placeholderText()
    assert paths[2] not in win._per_file_edits
    win._save_changes()
    assert [read_metadata(p).title for p in paths[2:]] == ['C', 'C', 'C']
    assert not win._has_unsaved_changes() and not dirty(win)
    assert all(read_metadata(p).track_total == 17 for p in paths)


def test_repeated_copy_of_effective_value(setup):
    win, paths = setup
    activate(win, paths[2])
    copy(win, False)  # a/b receive C; b is a copied source for the next operation.
    activate(win, paths[1])
    copy(win)
    assert all(title(win, p) == 'C' for p in paths)
    assert read_metadata(paths[1]).title == 'B' and read_metadata(paths[3]).title == 'D'



@pytest.mark.parametrize('column', [0, 1])
def test_unsupported_columns_and_no_target_are_noops(setup, column):
    win, paths = setup
    activate(win, paths[2], column)
    assert not win.file_list.copy_down_action.isEnabled()
    assert not win.file_list.copy_up_action.isEnabled()
    win.file_list._copy_cells(True)
    assert not win._per_file_edits and not dirty(win)
    activate(win, paths[-1])
    assert not win.file_list.copy_down_action.isEnabled()
    win.file_list._copy_cells(True)
    activate(win, paths[0])
    assert not win.file_list.copy_up_action.isEnabled()
    win.file_list._copy_cells(False)
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('descending', [False, True])
def test_affected_column_sort_snapshot(setup, descending):
    win, paths = setup
    win.file_list.sortItems(2, Qt.DescendingOrder if descending else Qt.AscendingOrder)
    visual = [Path(win.file_list.item(r, 0).data(256)) for r in range(5)]
    source = visual[2]
    expected = set(visual[3:])
    value = title(win, source)
    activate(win, source)
    copy(win)
    assert set(win._per_file_edits) == expected
    assert all(title(win, p) == value for p in expected)
    assert source not in win._per_file_edits
    win.file_list.sortItems(0, Qt.AscendingOrder)
    assert [Path(win.file_list.item(r, 0).data(256)) for r in range(5)] == paths
    win._save_changes()
    assert all(read_metadata(p).title == value for p in expected)


@pytest.mark.parametrize('down', [True, False])
def test_generate_and_copy_precedence(setup, qtbot, down):
    win, paths = setup
    win._apply_generated('title', {p: f'Generated {i}' for i, p in enumerate(paths)})
    win._apply_generated('series', {p: f'Series {i}' for i, p in enumerate(paths)})
    activate(win, paths[2])
    copy(win, down)
    targets = paths[3:] if down else paths[:2]
    assert all(title(win, p) == 'Generated 2' for p in targets)
    assert win._per_file_edits[paths[2]]['title'] == 'Generated 2'
    assert all(win._per_file_edits[p]['series'] == f'Series {i}' for i, p in enumerate(paths))
    win._apply_generated('title', {p: 'Regenerated' for p in paths})
    assert all(title(win, p) == 'Regenerated' for p in paths)
    win.title_edit.selectAll()
    qtbot.keyClicks(win.title_edit, 'Common')
    assert all('title' not in edits for edits in win._per_file_edits.values())
    assert win.multi_edit_fields == {'title'}
    win._save_changes()
    assert all(read_metadata(p).title == 'Common' for p in paths)


def test_common_pending_split_retains_non_targets(setup, qtbot):
    win, paths = setup
    win.artist_edit.selectAll()
    qtbot.keyClicks(win.artist_edit, 'Common')
    win._apply_generated('series', {p: 'Series' for p in paths})
    activate(win, paths[2], 3)
    copy(win)
    # Source table still displayed accepted Artist, not the common panel edit.
    assert win._per_file_edits == {
        p: {'series': 'Series', 'artist': 'Common' if i <= 2 else 'Original'}
        for i, p in enumerate(paths)
    }
    assert 'artist' not in win.multi_edit_fields
    assert win.artist_edit.placeholderText()
    win._save_changes()
    assert [read_metadata(p).artist for p in paths] == ['Common'] * 3 + ['Original'] * 2


@pytest.mark.parametrize('failure', ['before', 'after', 'readback'])
def test_copy_uncertainty_retry(setup, monkeypatch, failure):
    win, paths = setup
    activate(win, paths[0])
    copy(win)
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    reader = win._read_after_write
    def write(path, *a, **k):
        if path == paths[2] and failure == 'before':
            raise OSError('before')
        writer(path, *a, **k)
        if path == paths[2] and failure == 'after':
            raise OSError('after')
    def read(path):
        if path == paths[2] and failure == 'readback':
            raise MetadataReadError(path, 'verification failed')
        return reader(path)
    with monkeypatch.context() as patch:
        patch.setattr(module, writer_name, write)
        patch.setattr(win, '_read_after_write', read)
        patch.setattr(QMessageBox, 'critical', lambda *a: None)
        win._save_changes()
    assert win._has_unsaved_changes() and win._unresolved_per_file_fields
    assert win._per_file_edits[paths[2]]['title'] == 'A'
    assert not win._unresolved_multi_fields
    assert read_metadata(paths[1]).title == 'A'
    assert read_metadata(paths[4]).title == 'C'
    win._save_changes()
    assert all(read_metadata(p).title == 'A' for p in paths)
    assert not win._has_unsaved_changes()


def test_discard_and_failed_reload(setup, monkeypatch):
    win, paths = setup
    activate(win, paths[0])
    copy(win)
    before = deepcopy(win._per_file_edits)
    def fail(path):
        raise MetadataReadError(path, 'unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(module, 'read_metadata', fail)
        patch.setattr(QMessageBox, 'critical', lambda *a: None)
        win._undo_changes()
    assert win._per_file_edits == before
    win._undo_changes()
    assert not win._has_unsaved_changes() and not win._per_file_edits
    assert [title(win, p) for p in paths] == ['A', 'B', 'C', 'D', 'C']


@pytest.mark.parametrize('action', ['selection', 'directory', 'open', 'root', 'refresh', 'close'])
def test_cancel_guards(setup, tmp_path, monkeypatch, action):
    win, paths = setup
    activate(win, paths[0])
    copy(win)
    before = deepcopy(win._per_file_edits)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Cancel)
    other = tmp_path / 'Other'
    other.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a: str(other))
    if action == 'selection':
        win.file_list.select_files([str(paths[0])])
    elif action == 'directory':
        win._directory_selected(other)
    elif action == 'open':
        win._open_folder()
    elif action == 'root':
        win._choose_root()
    elif action == 'refresh':
        win._refresh_tree()
    else:
        event = QCloseEvent()
        win.closeEvent(event)
        assert not event.isAccepted()
    assert win._per_file_edits == before
    assert all(title(win, p) == 'A' for p in paths)


@pytest.mark.parametrize('down', [True, False])
def test_shortcut_ignores_transient_editor_text(setup, qtbot, down):
    win, paths = setup
    source = paths[0] if down else paths[-1]
    activate(win, source)
    value = title(win, source)
    win.file_list.editItem(win.file_list.currentItem())
    editor = win.file_list.focusWidget()
    assert isinstance(editor, QLineEdit)
    editor.setText('Unconfirmed')
    qtbot.keyClick(editor, Qt.Key_D, Qt.ControlModifier if down else Qt.ControlModifier | Qt.ShiftModifier)
    assert win._per_file_edits
    assert all(title(win, p) == value for p in paths)
    assert read_metadata(source).title == value
    assert win.file_list.isSortingEnabled()


def test_empty_text_series_string_and_artwork_preservation(setup):
    win, paths = setup
    writer = module.write_mp3_metadata if paths[0].suffix == '.mp3' else module.write_m4b_metadata
    for path in paths:
        writer(path, read_metadata(path), fields=set(), artwork=b'cover', artwork_mime='image/jpeg')
    win._apply_generated('title', {p: '' if p == paths[0] else 'Pending' for p in paths})
    win._apply_generated('series_number', {p: '01.5' if p == paths[0] else 'Other' for p in paths})
    activate(win, paths[0])
    copy(win)
    activate(win, paths[0], 6)
    copy(win)
    assert all(win._per_file_edits[p]['title'] == '' for p in paths)
    assert all(win._per_file_edits[p]['series_number'] == '01.5' for p in paths)
    win._save_changes()
    for path in paths:
        metadata = read_metadata(path)
        assert metadata.title == '' and metadata.series_number == '01.5'
        assert metadata.artwork == b'cover' and metadata.track_total == 17
        assert metadata.artist == 'Original' and metadata.album == 'Album'


def test_uncertain_common_split_and_matching_override(setup, qtbot, monkeypatch):
    win, paths = setup
    win.artist_edit.selectAll()
    qtbot.keyClicks(win.artist_edit, 'Common')
    win._unresolved_multi_fields.add('artist')
    activate(win, paths[2], 3)
    copy(win)
    assert not win._unresolved_multi_fields
    assert win._unresolved_per_file_fields == {p: {'artist'} for p in paths}
    # Targets match cached Original, but the common operation was unresolved.
    assert dirty(win) == set(paths)
    win._save_changes()
    assert not win._has_unsaved_changes()
    assert [read_metadata(p).artist for p in paths] == ['Common'] * 3 + ['Original'] * 2


def test_enter_after_copy_saves_only_explicit_field(setup, qtbot, monkeypatch):
    win, paths = setup
    activate(win, paths[0])
    copy(win)
    target = paths[1]
    activate(win, target)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Cancel)
    win.file_list.editItem(win.file_list.currentItem())
    editor = win.file_list.focusWidget()
    editor.setText('Immediate')
    qtbot.keyClick(editor, Qt.Key_Return)
    qtbot.wait(1)
    assert read_metadata(target).title == 'Immediate'
    assert 'title' not in win._per_file_edits[target]
    assert win._per_file_edits[paths[2]]['title'] == 'A'
    assert read_metadata(paths[2]).title == 'C'
    assert title(win, paths[2]) == 'A'
