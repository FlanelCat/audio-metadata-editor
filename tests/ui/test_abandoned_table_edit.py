"""Only Enter may promote transient table-editor text to the table model."""
from pathlib import Path
import shutil

import pytest
from shiboken6 import isValid
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QLineEdit, QMessageBox, QPushButton

from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{name}.{request.param}' for name in 'abc']
    for path in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
    win = MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.root_path = tmp_path
    win._populate_root()
    win.file_list.setSortingEnabled(False)
    win.show()
    qtbot.waitExposed(win)
    win.file_list.setCurrentCell(0, 1)
    def unexpected(*args):
        pytest.fail(f'Unexpected dialog: {args[1:]}')
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    monkeypatch.setattr(QMessageBox, 'critical', unexpected)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    return win, paths


def click_cell(qtbot, table, row, column, modifier=Qt.NoModifier):
    qtbot.mouseClick(table.viewport(), Qt.LeftButton, modifier,
                     table.visualItemRect(table.item(row, column)).center())


def start_edit(win, qtbot, column, text):
    table = win.file_list
    table.setCurrentCell(0, column)
    table.editItem(table.item(0, column))
    editor = table.focusWidget()
    assert isinstance(editor, QLineEdit)
    editor.selectAll()
    qtbot.keyClicks(editor, text)
    return editor


@pytest.mark.parametrize('column,field,text', [(1, 'track_number', '2'), (2, 'title', 'Transient')])
def test_click_other_file_abandons_edit(setup, qtbot, column, field, text):
    win, paths = setup
    table = win.file_list
    before = {p: p.read_bytes() for p in paths}
    original = table.item(0, column).text()
    trace = []
    class FocusTrace(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.FocusOut:
                trace.append('FocusOut')
            return False
    editor = start_edit(win, qtbot, column, text)
    observer = FocusTrace(editor)
    editor.installEventFilter(observer)
    table.metadata_cell_edited.connect(lambda *args: trace.append('metadata_cell_edited'))
    table.model().dataChanged.connect(
        lambda first, last, roles: trace.append('dataChanged') if first.column() == column else None)
    table.itemDelegate().commitData.connect(lambda *args: trace.append('commitData'))
    table.itemDelegate().closeEditor.connect(lambda *args: trace.append('closeEditor'))
    table.currentItemChanged.connect(lambda *args: trace.append('currentItemChanged'))
    table.files_selected.connect(lambda *args: trace.append('files_selected'))
    table.itemSelectionChanged.connect(lambda: trace.append('itemSelectionChanged'))
    table.save_cell_requested.connect(lambda *args: trace.append('save_cell_requested'))
    click_cell(qtbot, table, 1, column)
    qtbot.wait(1)
    assert win.current_file == paths[1]
    assert win.current_metadata == read_metadata(paths[1])
    assert getattr(win._get_edited_metadata(), field) == getattr(read_metadata(paths[1]), field)
    assert not win._has_unsaved_changes()
    assert {p: p.read_bytes() for p in paths} == before
    assert table.item(0, column).text() == original, " -> ".join(trace)
    assert 'metadata_cell_edited' not in trace
    assert 'save_cell_requested' not in trace
    click_cell(qtbot, table, 0, column)
    assert win.current_metadata == read_metadata(paths[0])
    assert table.item(0, column).text() == original


@pytest.mark.parametrize('column,text', [(1, '2'), (2, 'Transient')])
@pytest.mark.parametrize('action', ['multi', 'clear', 'directory', 'refresh', 'close',
                                   'same_row', 'new_editor', 'escape', 'tab', 'panel_focus',
                                   'programmatic_selection'])
def test_abandoned_transition(setup, qtbot, tmp_path, column, text, action):
    win, paths = setup
    table = win.file_list
    original = table.item(0, column).text()
    before = {p: p.read_bytes() for p in paths}
    saves = []
    table.save_cell_requested.connect(lambda *args: saves.append(args))
    editor = start_edit(win, qtbot, column, text)
    if action == 'multi':
        click_cell(qtbot, table, 1, column, Qt.ShiftModifier)
        assert set(win.selected_files) == {str(p) for p in paths[:2]}
    elif action == 'clear':
        table.clearSelection()
        assert win.selected_files == []
    elif action == 'directory':
        from PySide6.QtWidgets import QTreeWidgetItem
        destination = tmp_path / 'empty'
        destination.mkdir()
        item = QTreeWidgetItem([destination.name])
        item.setData(0, Qt.UserRole, str(destination))
        win.directory_tree.addTopLevelItem(item)
        qtbot.mouseClick(win.directory_tree.viewport(), Qt.LeftButton,
                         pos=win.directory_tree.visualItemRect(item).center())
        assert win.selected_files == []
        assert table.rowCount() == 0
    elif action == 'refresh':
        button = next(b for b in win.findChildren(QPushButton) if b.text() == 'Refresh')
        qtbot.mouseClick(button, Qt.LeftButton)
        assert win.selected_files == []
    elif action == 'close':
        assert win.close()
        win.show()  # A discarded editor must not reappear with stale contents.
    elif action == 'same_row':
        click_cell(qtbot, table, 0, 3)
    elif action == 'new_editor':
        click_cell(qtbot, table, 0, 3)
        table.editItem(table.item(0, 3))
        assert isinstance(table.focusWidget(), QLineEdit)
        assert table.focusWidget().text() == read_metadata(paths[0]).artist
    elif action == 'escape':
        qtbot.keyClick(editor, Qt.Key_Escape)
    elif action == 'tab':
        qtbot.keyClick(editor, Qt.Key_Tab)
    elif action == 'panel_focus':
        win.artist_edit.setFocus()
    else:
        table.select_files([str(paths[1])])
        assert win.current_file == paths[1]
    qtbot.wait(1)
    assert saves == []
    assert not win._has_unsaved_changes()
    assert win.multi_edit_fields == set()
    assert {p: p.read_bytes() for p in paths} == before
    if action != 'directory':
        assert table.item(0, column).text() == original
        if action != 'new_editor':
            assert not isValid(editor) or not editor.isVisible()
    if win.current_file is not None and len(win.selected_files) == 1:
        assert win.current_metadata == read_metadata(win.current_file)


@pytest.mark.parametrize('column,text', [(1, '2'), (2, 'Transient')])
@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_panel_pending_guard_abandons_only_table_edit(setup, qtbot, monkeypatch, column, text, reply):
    win, paths = setup
    table = win.file_list
    before = {p: read_metadata(p) for p in paths}
    original = table.item(0, column).text()
    win.artist_edit.setText('Pending artist')
    prompts, saves = [], []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: prompts.append(args) or reply)
    table.save_cell_requested.connect(lambda *args: saves.append(args))
    start_edit(win, qtbot, column, text)
    click_cell(qtbot, table, 1, column)
    assert len(prompts) == 1
    assert saves == []
    assert table.item(0, column).text() == original
    for path in paths:
        expected = before[path]
        if path == paths[0] and reply == QMessageBox.Save:
            expected.artist = 'Pending artist'
        assert read_metadata(path) == expected
    if reply == QMessageBox.Cancel:
        assert win.current_file == paths[0]
        assert win.artist_edit.text() == 'Pending artist'
        assert win.current_metadata == before[paths[0]]
        assert win._has_unsaved_changes()
        assert table.currentRow() == 0
        assert win._context_index.row() == 0
    else:
        assert win.current_file == paths[1]
        assert not win._has_unsaved_changes()


@pytest.mark.parametrize('column,text', [(1, '2'), (2, 'Transient title'),
                                       (3, 'Transient artist'), (4, 'Transient album'),
                                       (5, 'Transient series'), (6, '2.5'),
                                       (7, 'Transient narrator')])
def test_all_columns_abandon_without_reading(setup, qtbot, monkeypatch, column, text):
    import audio_metadata_editor.ui.main_window as main_module
    import audio_metadata_editor.ui.file_list as table_module
    win, paths = setup
    table = win.file_list
    original = table.item(0, column).text()
    baseline = read_metadata(paths[0])
    before = {p: p.read_bytes() for p in paths}
    changes = []
    table.metadata_cell_edited.connect(lambda *args: changes.append(args))
    start_edit(win, qtbot, column, text)
    def unexpected_read(*args):
        pytest.fail('Abandoning an editor must use accepted presentation, not reread disk')
    monkeypatch.setattr(main_module, 'read_metadata', unexpected_read)
    monkeypatch.setattr(table_module, 'read_metadata', unexpected_read)
    win.artist_edit.setFocus()
    assert changes == []
    assert table.item(0, column).text() == original
    assert win.current_metadata == baseline
    assert not win._has_unsaved_changes()
    assert {p: p.read_bytes() for p in paths} == before


@pytest.mark.parametrize('column,text', [(1, '2'), (2, 'Transient')])
def test_failed_selection_read_keeps_accepted_cell(setup, qtbot, monkeypatch, column, text):
    import audio_metadata_editor.ui.main_window as module
    from audio_metadata_editor.metadata import MetadataReadError
    win, paths = setup
    table = win.file_list
    baseline = read_metadata(paths[0])
    original = table.item(0, column).text()
    before = {p: p.read_bytes() for p in paths}
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    def fail(path):
        raise MetadataReadError(path, 'injected read failure')
    monkeypatch.setattr(module, 'read_metadata', fail)
    start_edit(win, qtbot, column, text)
    click_cell(qtbot, table, 1, column)
    assert len(errors) == 1
    assert win.current_file == paths[0]
    assert win.current_metadata == baseline
    assert win.selected_files == [str(paths[0])]
    assert table.selected_paths_in_row_order() == win.selected_files
    assert table.item(0, column).text() == original
    assert not win._has_unsaved_changes()
    assert {p: p.read_bytes() for p in paths} == before


@pytest.mark.parametrize('column,text', [(1, '2'), (2, 'ZZZ transient')])
def test_abandon_does_not_reorder_sorted_table(setup, qtbot, column, text):
    win, _ = setup
    table = win.file_list
    table.setSortingEnabled(True)
    table.sortItems(column, Qt.AscendingOrder)
    order = [table.item(r, 0).data(256) for r in range(table.rowCount())]
    original = table.item(0, column).text()
    start_edit(win, qtbot, column, text)
    click_cell(qtbot, table, 1, column)
    assert [table.item(r, 0).data(256) for r in range(table.rowCount())] == order
    assert table.item(0, column).text() == original
    assert win.current_file == Path(order[1])
    assert not win._has_unsaved_changes()
