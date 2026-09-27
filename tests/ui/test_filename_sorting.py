"""Filename order uses file identity, never pending-status decoration."""
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QMessageBox

from audio_metadata_editor.metadata import Metadata, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.ui.main_window import MainWindow


def choose(editor, value):
    next(a for a in editor.findChild(QMenu).actions() if a.data() == value).trigger()


def assert_rows(win, paths, dirty):
    table = win.file_list
    assert [Path(table.item(r, 0).data(256)) for r in range(3)] == paths
    for row, path in enumerate(paths):
        item = table.item(row, 0)
        assert item.text() == ('* ' if path in dirty else '') + path.name
        assert table.item(row, 2).text() == path.stem


@pytest.fixture
def window(tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{name}.mp3' for name in 'abc']
    for path, artist, album in zip(paths, ['A', 'B', 'A'], ['X', 'Y', 'X']):
        shutil.copy2(audio_fixture_dir / 'silence.mp3', path)
        write_metadata(path, Metadata(title=path.stem, artist=artist, album=album))
    win = MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: pytest.fail(str(a)))
    win.root_path = tmp_path
    win._populate_root()
    win.file_list.select_files([str(p) for p in paths])
    win.show()
    return win, paths


@pytest.mark.parametrize('descending', [False, True])
def test_pending_markers_save_discard_and_refresh(window, qtbot, descending):
    win, paths = window
    a, b, c = paths
    order = Qt.DescendingOrder if descending else Qt.AscendingOrder
    win.file_list.sortItems(0, order)
    ordered = list(reversed(paths)) if descending else paths
    assert_rows(win, ordered, set())
    for value, dirty in [('A', {b}), ('B', {a, c}), ('', set(paths))]:
        choose(win.artist_edit, value)
        assert_rows(win, ordered, dirty)
    qtbot.keyClicks(win.artist_edit, 'C')
    assert_rows(win, ordered, set(paths))
    win.artist_edit.selectAll()
    qtbot.keyClicks(win.artist_edit, 'A')
    assert_rows(win, ordered, {b})
    choose(win.album_edit, 'Y')
    assert_rows(win, ordered, set(paths))
    choose(win.album_edit, 'X')
    assert_rows(win, ordered, {b})
    win._undo_changes()
    assert_rows(win, ordered, set())
    choose(win.artist_edit, 'A')
    win._save_changes()
    assert_rows(win, ordered, set())
    assert all(read_metadata(p).artist == 'A' for p in paths)
    win._refresh_tree()
    assert_rows(win, ordered, set())


@pytest.mark.parametrize('descending', [False, True])
def test_uncertainty_markers_do_not_move_rows(window, descending):
    win, paths = window
    win.file_list.sortItems(0, Qt.DescendingOrder if descending else Qt.AscendingOrder)
    ordered = list(reversed(paths)) if descending else paths
    win._unverified_fields[paths[1]] = {'artist'}
    win._update_dirty_indicators()
    assert_rows(win, ordered, {paths[1]})
    win._verify_field_saves()
    assert_rows(win, ordered, set())
    win._unresolved_multi_fields.add('artist')
    win._update_dirty_indicators()
    assert_rows(win, ordered, set(paths))
    win._undo_changes()
    assert_rows(win, ordered, set())
    win.file_list.select_files([str(paths[1])])
    win._unresolved_single_fields.add('artist')
    win._update_dirty_indicators()
    assert_rows(win, ordered, {paths[1]})
    win._undo_changes()
    assert_rows(win, ordered, set())


def test_filename_comparison_uses_undecorated_basename(qtbot):
    from audio_metadata_editor.ui.file_list import FilenameTableWidgetItem
    a = FilenameTableWidgetItem(Path('/z/A.mp3'))
    b = FilenameTableWidgetItem(Path('/a/b.mp3'))
    equal = FilenameTableWidgetItem(Path('/other/a.MP3'))
    assert a < b and not b < a
    assert not a < equal and not equal < a
    b.setText('* b.mp3')
    assert a < b and not b < a
    assert b.data(256) == '/a/b.mp3' and b.data(257) == 'b.mp3'
    # A literal asterisk in a real filename is data, not a status prefix to strip.
    literal = FilenameTableWidgetItem(Path('/z/* actual.mp3'))
    literal.setText('* * actual.mp3')
    assert literal < a
    assert literal.data(257) == '* actual.mp3'


@pytest.mark.parametrize('descending', [False, True])
def test_empty_choice_keeps_matching_rows_clean_and_stationary(window, descending):
    win, paths = window
    choose(win.artist_edit, 'A')  # Make Discard reload the externally changed baselines.
    for path in (paths[0], paths[2]):
        write_metadata(path, Metadata(artist=''), fields={'artist'})
    win._undo_changes()
    win.file_list.sortItems(0, Qt.DescendingOrder if descending else Qt.AscendingOrder)
    ordered = list(reversed(paths)) if descending else paths
    choose(win.artist_edit, '')
    assert_rows(win, ordered, {paths[1]})
    win._undo_changes()
    assert_rows(win, ordered, set())
