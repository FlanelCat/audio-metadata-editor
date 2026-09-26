import shutil

import pytest
from PySide6.QtCore import QSignalBlocker

from audio_metadata_editor.metadata import Metadata
from audio_metadata_editor.ui.file_list import FileList, SortableTableWidgetItem


@pytest.fixture
def table(qtbot):
    table = FileList()
    qtbot.addWidget(table)
    table.setSortingEnabled(False)
    table.resize(700, 250)
    table.show()
    return table


def expected_width(table, column):
    return max(table.horizontalHeader().sectionSizeHint(column),
               table.sizeHintForColumn(column))


def assert_fitted(table, qtbot):
    qtbot.waitUntil(lambda: all(table.columnWidth(c) == expected_width(table, c)
                               for c in range(table.columnCount())))


def test_empty_headers(table, qtbot):
    assert_fitted(table, qtbot)
    for column in range(table.columnCount()):
        assert table.columnWidth(column) >= table.fontMetrics().horizontalAdvance(
            table.horizontalHeaderItem(column).text())


@pytest.mark.parametrize('column', range(8))
def test_grow_and_shrink_all_rows(table, qtbot, column):
    # Beyond Qt's default 1000-row sampling limit and below the viewport.
    table.setRowCount(1002)
    with QSignalBlocker(table):
        for row in range(table.rowCount()):
            table.setItem(row, column, SortableTableWidgetItem(''))
    assert_fitted(table, qtbot)
    small = table.columnWidth(column)
    with QSignalBlocker(table):
        table.item(1001, column).setText('A wide displayed value ' * 8)
    assert_fitted(table, qtbot)
    assert table.columnWidth(column) > small
    with QSignalBlocker(table):
        table.item(1001, column).setText('i')
    assert_fitted(table, qtbot)
    assert table.columnWidth(column) == small
    table.setRowCount(0)
    assert_fitted(table, qtbot)


def test_load_update_and_replace_directory(table, qtbot, tmp_path, audio_fixture_dir):
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    path = first / ('Long filename ' * 6 + '.mp3')
    shutil.copy2(audio_fixture_dir / 'silence.mp3', path)
    before = path.read_bytes()
    table.load_directory(first)
    assert_fitted(table, qtbot)
    filename_width = table.columnWidth(0)
    table.update_file_metadata(path, Metadata(title='A long title ' * 12))
    assert_fitted(table, qtbot)
    title_width = table.columnWidth(2)
    table.update_file_metadata(path, Metadata(title='Short'))
    assert_fitted(table, qtbot)
    assert table.columnWidth(2) < title_width
    table.load_directory(second)
    assert_fitted(table, qtbot)
    assert table.columnWidth(0) < filename_width
    assert path.read_bytes() == before
