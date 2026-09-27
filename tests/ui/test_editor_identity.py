"""Enter saves the editor's file, even when committing reorders the table."""
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QMessageBox

from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.ui.main_window import MainWindow


@pytest.fixture(params=['mp3', 'm4b'])
def window(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    for name, title, track in [('a', 'A', 5), ('b', 'M', 9), ('c', 'Z', 13)]:
        path = tmp_path / f'{name}.{request.param}'
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        metadata = read_metadata(path)
        metadata.title = metadata.artist = title
        metadata.track_number = track
        write_metadata(path, metadata, fields={'title', 'artist', 'track_number'})
    widget = MainWindow()
    qtbot.addWidget(widget, before_close_func=lambda w: w._clear_editing_context())
    widget.file_list.load_directory(tmp_path)
    widget.show()
    qtbot.waitExposed(widget)
    def unexpected(*args):
        pytest.fail(f'Unexpected dialog: {args[1:]}')
    monkeypatch.setattr(QMessageBox, 'critical', unexpected)
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    yield widget
    widget._clear_editing_context()


def paths(table):
    return [Path(table.item(row, 0).data(256)) for row in range(table.rowCount())]


def edit(window, qtbot, row, column, mouse=False):
    table = window.file_list
    table.setCurrentCell(row, column)
    if mouse:
        point = table.visualItemRect(table.item(row, column)).center()
        qtbot.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        qtbot.mouseDClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
    else:
        table.editItem(table.item(row, column))
    editor = table.focusWidget()
    assert isinstance(editor, QLineEdit)
    editor.selectAll()
    return editor


def enter(editor, text, qtbot):
    editor.setText(text)
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(1)


@pytest.mark.parametrize('column,field,low,high', [
    (2, 'title', '0', 'ZZZ'), (3, 'artist', '0', 'ZZZ'),
    (1, 'track_number', '1', '20'),
])
@pytest.mark.parametrize('descending', [False, True])
@pytest.mark.parametrize('row,to_high', [(0, True), (2, False), (1, True), (1, False)])
def test_sorted_save(window, qtbot, column, field, low, high, descending, row, to_high):
    table = window.file_list
    table.sortItems(column, Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder)
    original = {path: read_metadata(path) for path in paths(table)}
    target = paths(table)[row]
    editor = edit(window, qtbot, row, column)
    value = high if to_high else low
    enter(editor, value, qtbot)
    setattr(original[target], field, int(value) if column == 1 else value)
    assert {path: read_metadata(path) for path in original} == original
    order = paths(table)
    saved_row = order.index(target)
    expected = order[min(saved_row + 1, len(order) - 1)]
    assert window.current_file == expected
    assert table.currentColumn() == column
    assert not window._has_unsaved_changes()
    if saved_row < len(order) - 1:
        assert isinstance(table.focusWidget(), QLineEdit)
        assert table.focusWidget().text() == table.item(saved_row + 1, column).text()


@pytest.mark.parametrize('invalid', ['invalid', '0', '-1', '1.5'])
def test_automatic_numeric_editor_rejects_without_saving(window, qtbot, invalid):
    table = window.file_list
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    order = paths(table)
    enter(edit(window, qtbot, 0, 1, mouse=True), '6', qtbot)
    editor = table.focusWidget()
    assert isinstance(editor, QLineEdit) and editor.text() == '9'
    before = {path: path.read_bytes() for path in order}
    enter(editor, invalid, qtbot)
    assert {path: path.read_bytes() for path in order} == before
    assert window.current_file == order[1]
    assert table.focusWidget() is editor
    assert editor.selectedText() == invalid
    assert table.item(1, 1).text() == '9'
    assert not window._has_unsaved_changes()
    enter(editor, '10', qtbot)
    enter(table.focusWidget(), '', qtbot)
    assert [read_metadata(path).track_number for path in order] == [6, 10, None]


@pytest.mark.parametrize('choice', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_sorted_save_preserves_panel_guard(window, qtbot, monkeypatch, choice):
    table = window.file_list
    table.sortItems(2, Qt.SortOrder.AscendingOrder)
    target = paths(table)[2]
    table.setCurrentCell(2, 2)
    window.album_edit.setText('Pending album')
    prompts = []
    def answer(*args):
        assert read_metadata(target).title == 'AAA'
        prompts.append(args)
        return choice
    monkeypatch.setattr(QMessageBox, 'question', answer)
    enter(edit(window, qtbot, 2, 2), 'AAA', qtbot)
    assert len(prompts) == 1
    assert read_metadata(target).title == 'AAA'
    assert (read_metadata(target).album == 'Pending album') == (choice == QMessageBox.Save)
    assert window._has_unsaved_changes() == (choice == QMessageBox.Cancel)
    assert window.current_file == (target if choice == QMessageBox.Cancel else paths(table)[paths(table).index(target) + 1])
    if choice == QMessageBox.Cancel:
        assert window.album_edit.text() == 'Pending album'


@pytest.mark.parametrize('failure', ['writer', 'readback'])
def test_sorted_failure_targets_exact_file(window, qtbot, monkeypatch, failure):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import MetadataReadError
    table = window.file_list
    table.sortItems(2, Qt.SortOrder.AscendingOrder)
    original = {path: read_metadata(path) for path in paths(table)}
    target = paths(table)[2]
    table.setCurrentCell(2, 2)
    window.album_edit.setText('Pending album')
    writes, errors = [], []
    def write(path, metadata, **kwargs):
        writes.append((path, kwargs['fields']))
        if failure == 'writer':
            raise OSError('Injected writer failure')
        write_metadata(path, metadata, **kwargs)
    def read(path):
        if failure == 'readback' and writes and Path(path) == target:
            raise MetadataReadError(path, 'Injected readback failure')
        return read_metadata(path)
    monkeypatch.setattr(module, 'write_metadata', write)
    monkeypatch.setattr(module, 'read_metadata', read)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    enter(edit(window, qtbot, 2, 2), 'AAA', qtbot)
    assert writes == [(target, {'title'})]
    assert len(errors) == 1
    assert window.current_file == target
    assert window.album_edit.text() == 'Pending album'
    assert window._has_unsaved_changes()
    if failure == 'readback':
        original[target].title = 'AAA'
        assert window._unverified_fields == {target: {'title'}}
        monkeypatch.setattr(module, 'read_metadata', read_metadata)
        window._verify_field_saves()
        assert not window._unverified_fields
        assert writes == [(target, {'title'})]
        assert window.current_metadata.title == 'AAA'
        assert window.album_edit.text() == 'Pending album'
    else:
        assert not window._unverified_fields
    assert {path: read_metadata(path) for path in original} == original


@pytest.mark.parametrize('column', [1, 6])
def test_mouse_invalid_keeps_panel_intent(window, qtbot, column):
    table = window.file_list
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    table.setCurrentCell(0, column)
    window.album_edit.setText('Pending album')
    before = {path: path.read_bytes() for path in paths(table)}
    accepted = table.item(0, column).text()
    requests = []
    table.save_cell_requested.connect(lambda *args: requests.append(args))
    editor = edit(window, qtbot, 0, column, mouse=True)
    enter(editor, 'invalid', qtbot)
    assert not requests
    assert table.focusWidget() is editor
    assert editor.selectedText() == 'invalid'
    assert table.item(0, column).text() == accepted
    assert window.album_edit.text() == 'Pending album'
    assert window._has_unsaved_changes()
    assert {path: path.read_bytes() for path in before} == before


def test_programmatic_update_does_not_open_editor_or_save(window, monkeypatch):
    table = window.file_list
    def unexpected(*args):
        pytest.fail('Programmatic update opened editor or requested save')
    monkeypatch.setattr(table.itemDelegate(), 'createEditor', unexpected)
    table.save_cell_requested.connect(unexpected)
    before = {path: path.read_bytes() for path in paths(table)}
    for path in before:
        table.update_file_metadata(path, read_metadata(path))
    assert not window._has_unsaved_changes()
    assert {path: path.read_bytes() for path in before} == before
