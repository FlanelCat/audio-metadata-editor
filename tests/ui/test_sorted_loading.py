"""Directory population must establish whole rows before Qt can move them."""
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from audio_metadata_editor.metadata import Metadata, MetadataReadError, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.ui.file_list import FileList
from audio_metadata_editor.ui.main_window import MainWindow
import audio_metadata_editor.ui.file_list as module


VALUES = [('a', 'Zulu', 'Beta', 'Gamma', 2),
          ('b', 'Alpha', 'Gamma', 'Beta', 10),
          ('c', 'Mike', 'Alpha', 'Alpha', 1)]


def metadata_values(directory, suffix='mp3'):
    return {directory / f'{name}.{suffix}': Metadata(
        title=title, artist=artist, album=album, track_number=track,
        series=f'Series {name}', series_number=str(track), narrator=f'Narrator {name}')
        for name, title, artist, album, track in VALUES}


def assert_rows(table, expected):
    assert table.rowCount() == len(expected)
    seen = set()
    for row in range(table.rowCount()):
        items = [table.item(row, column) for column in range(8)]
        assert all(item is not None for item in items)
        path = Path(items[0].data(256))
        assert path in expected and path not in seen
        seen.add(path)
        m = expected[path]
        assert [item.text() for item in items] == [
            path.name, str(m.track_number), m.title, m.artist, m.album,
            m.series, m.series_number, m.narrator]
        assert items[0].data(257) in (None, path.name)
    assert seen == set(expected)


def assert_sort(table, column, order, enabled=True):
    assert table.isSortingEnabled() == enabled
    assert table.horizontalHeader().sortIndicatorSection() == column
    assert table.horizontalHeader().sortIndicatorOrder() == order
    if enabled:
        values = [table.item(row, column).text() for row in range(table.rowCount())]
        key = int if column == 1 else str.casefold
        assert values == sorted(values, key=key, reverse=order == Qt.DescendingOrder)


@pytest.fixture
def setup(tmp_path, qtbot, monkeypatch):
    expected = metadata_values(tmp_path)
    for path in expected:
        path.touch()
    monkeypatch.setattr(module, 'read_metadata', lambda path: expected[path])
    table = FileList()
    qtbot.addWidget(table)
    return table, expected


@pytest.mark.parametrize('column', [0, 2, 3, 4, 1])
@pytest.mark.parametrize('order', [Qt.AscendingOrder, Qt.DescendingOrder])
def test_sorted_load_and_selection(setup, tmp_path, column, order):
    table, expected = setup
    table.sortItems(column, order)
    assert table.load_directory(tmp_path) == []
    assert_rows(table, expected)
    assert_sort(table, column, order)
    assert not table.selected_paths_in_row_order()
    assert not table.currentIndex().isValid()
    selected = []
    table.files_selected.connect(selected.append)
    for row in range(table.rowCount()):
        path = str(tmp_path / table.item(row, 0).text())
        table.setCurrentCell(row, 2)
        assert selected[-1] == [path]


def test_disabled_sort_remains_disabled(setup, tmp_path):
    table, expected = setup
    table.sortItems(2, Qt.DescendingOrder)
    table.setSortingEnabled(False)
    table.load_directory(tmp_path)
    assert_rows(table, expected)
    assert_sort(table, 2, Qt.DescendingOrder, enabled=False)
    assert [table.item(r, 0).text() for r in range(3)] == ['a.mp3', 'b.mp3', 'c.mp3']


@pytest.mark.parametrize('replace_directory', [False, True])
def test_reload_clears_old_identity_and_selection(setup, tmp_path, replace_directory):
    table, expected = setup
    table.sortItems(0, Qt.DescendingOrder)
    table.load_directory(tmp_path)
    table.setCurrentCell(0, 2)
    table.set_dirty_files(list(expected))
    directory = tmp_path / 'second' if replace_directory else tmp_path
    if replace_directory:
        directory.mkdir()
    expected.clear()
    expected.update(metadata_values(directory))
    for path, metadata in expected.items():
        path.touch()
        metadata.title += ' reloaded'
    table.load_directory(directory)
    assert_rows(table, expected)
    assert_sort(table, 0, Qt.DescendingOrder)
    assert not table.selected_paths_in_row_order()
    assert not table.currentIndex().isValid()


def test_read_failure_skips_complete_file(setup, tmp_path, monkeypatch):
    table, expected = setup
    failed = tmp_path / 'b.mp3'
    def read(path):
        if path == failed:
            raise MetadataReadError(path, 'injected read failure')
        return expected[path]
    monkeypatch.setattr(module, 'read_metadata', read)
    table.sortItems(2, Qt.AscendingOrder)
    errors = table.load_directory(tmp_path)
    assert len(errors) == 1 and str(failed) in str(errors[0])
    assert_rows(table, {p: m for p, m in expected.items() if p != failed})
    assert_sort(table, 2, Qt.AscendingOrder)


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
def test_enter_after_sorted_load_targets_visible_file(tmp_path, audio_fixture_dir, qtbot, monkeypatch, suffix):
    expected = metadata_values(tmp_path, suffix)
    for path, metadata in expected.items():
        shutil.copy2(audio_fixture_dir / f'silence.{suffix}', path)
        write_metadata(path, metadata)
    window = MainWindow()
    qtbot.addWidget(window, before_close_func=lambda w: w._clear_editing_context())
    def unexpected(*args):
        pytest.fail(f'Unexpected dialog: {args[1:]}')
    monkeypatch.setattr(QMessageBox, 'critical', unexpected)
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    table = window.file_list
    table.sortItems(0, Qt.DescendingOrder)
    window.root_path = tmp_path
    window._populate_root()
    window.show()
    assert_rows(table, expected)
    row = next(r for r in range(3) if table.item(r, 0).text() == f'b.{suffix}')
    target = tmp_path / f'b.{suffix}'
    before = {p: p.read_bytes() for p in expected}
    table.setCurrentCell(row, 2)
    assert window.current_file == target
    table.editItem(table.item(row, 2))
    editor = table.focusWidget()
    editor.setText('Saved exact file')
    qtbot.keyClick(editor, Qt.Key_Return)
    qtbot.wait(1)
    expected[target].title = 'Saved exact file'
    assert read_metadata(target) == expected[target]
    assert all(p.read_bytes() == original for p, original in before.items() if p != target)
    assert not window._has_unsaved_changes()
    assert_rows(table, expected)
    # Refresh shares the sorted-loading path and clears the accepted selection.
    window._refresh_tree()
    assert_rows(table, expected)
    assert_sort(table, 0, Qt.DescendingOrder)
    assert window.selected_files == [] and window.current_file is None
    assert not window._has_unsaved_changes()


@pytest.mark.parametrize('exit_kind', ['empty', 'directory_error', 'unexpected_read_error'])
def test_sort_state_restored_on_early_exit(setup, tmp_path, monkeypatch, exit_kind):
    table, _ = setup
    table.sortItems(1, Qt.DescendingOrder)
    if exit_kind == 'empty':
        empty = tmp_path / 'empty'
        empty.mkdir()
        assert table.load_directory(empty) == []
    elif exit_kind == 'directory_error':
        assert table.load_directory(tmp_path / 'missing') is None
    else:
        def fail(path):
            raise RuntimeError('unexpected reader error')
        monkeypatch.setattr(module, 'read_metadata', fail)
        with pytest.raises(RuntimeError, match='unexpected reader error'):
            table.load_directory(tmp_path)
    assert table.rowCount() == 0
    assert_sort(table, 1, Qt.DescendingOrder)
