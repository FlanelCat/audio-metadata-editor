from pathlib import Path
import shutil
import pytest
from PySide6.QtWidgets import QMessageBox, QTreeWidgetItem
from audio_metadata_editor.metadata import Metadata, read_metadata
from audio_metadata_editor.ui.main_window import MainWindow


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, qtbot, monkeypatch, audio_fixture_dir):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir(); b.mkdir()
    for directory in (a, b):
        for name in ('one', 'two'):
            shutil.copy2(audio_fixture_dir / f'silence.{request.param}',
                         directory / f'{name}.{request.param}')
    win = MainWindow()
    qtbot.addWidget(win)
    win.root_path = a
    win._populate_root()
    win.file_list.setCurrentCell(0, 2)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    yield win, a, b
    win.current_metadata = None
    win.selected_files = []
    win.multi_edit_fields.clear()
    win.multi_edit_artwork = False


def change(win, directory):
    item = QTreeWidgetItem([directory.name])
    item.setData(0, 256, str(directory))
    win.directory_tree.addTopLevelItem(item)
    win.directory_tree.setCurrentItem(item)
    win.directory_tree.itemClicked.emit(item, 0)


def assert_empty(win):
    assert win.current_file is None
    assert win.current_metadata is None
    assert win.selected_files == []
    assert win.metadata_panel.collect_metadata() == Metadata()
    assert win.pending_artwork is None
    assert win.pending_artwork_mime == ''
    assert not win.multi_edit_fields
    assert not win.multi_edit_artwork
    assert not win.artwork_edited
    assert win.artwork_label.pixmap().isNull()
    assert not win.id3v1_comment_edit.isEnabled()
    assert not win._has_unsaved_changes()
    assert not win.statusBar().currentMessage()
    assert not win.file_list.selected_paths_in_row_order()
    assert all(not win.file_list.item(row, 0).text().startswith('*')
               for row in range(win.file_list.rowCount()))


@pytest.mark.parametrize('action', ['directory', 'empty', 'refresh', 'clear'])
def test_clean_transition(setup, action):
    win, a, b = setup
    clipboard = Metadata(title='Copied')
    win.metadata_clipboard = clipboard
    before = {path: path.read_bytes() for directory in (a, b)
              for path in directory.iterdir() if path.is_file()}
    if action == 'empty':
        b = b / 'empty'; b.mkdir()
    if action in ('directory', 'empty'):
        change(win, b)
    elif action == 'refresh':
        win._refresh_tree()
    else:
        win.file_list.clearSelection()
    assert_empty(win)
    assert win.metadata_clipboard is clipboard
    assert all(path.read_bytes() == contents for path, contents in before.items())


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('action', ['directory', 'refresh', 'clear'])
@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_dirty_transition(setup, qtbot, monkeypatch, multiple, action, reply):
    win, a, b = setup
    paths = [win.file_list.item(i, 0).data(256) for i in range(2)]
    if multiple:
        win.file_list.select_files(paths)
    original = list(win.selected_files)
    qtbot.keyClicks(win.artist_edit, 'Pending')
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: prompts.append(a) or reply)
    if action == 'directory': change(win, b)
    elif action == 'refresh': win._refresh_tree()
    else: win.file_list.clearSelection()
    assert len(prompts) == 1
    if reply == QMessageBox.Cancel:
        assert win.selected_files == original
        assert win.artist_edit.text() == 'Pending'
        assert win._has_unsaved_changes()
        assert Path(win.file_list.item(0, 0).data(256)).parent == a
    else:
        assert_empty(win)
    for path in original:
        assert read_metadata(Path(path)).artist == ('Pending' if reply == QMessageBox.Save else '')


@pytest.mark.parametrize('action', ['directory', 'refresh', 'open'])
def test_failed_save_preserves_directory(setup, monkeypatch, action):
    import audio_metadata_editor.ui.main_window as module
    from PySide6.QtWidgets import QFileDialog
    win, a, b = setup
    original = list(win.selected_files)
    root_item = win.directory_tree.currentItem()
    win.artist_edit.setText('Pending')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Save)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    def fail(*args, **kwargs):
        raise OSError('Save failed')
    monkeypatch.setattr(module, 'write_mp3_metadata', fail)
    monkeypatch.setattr(module, 'write_m4b_metadata', fail)
    if action == 'directory': change(win, b)
    elif action == 'refresh': win._refresh_tree()
    else:
        monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(b))
        win._open_folder()
    assert len(errors) == 1
    assert win.root_path == a
    assert win.directory_tree.currentItem() is root_item
    assert win.selected_files == original
    assert win.file_list.selected_paths_in_row_order() == original
    assert win.artist_edit.text() == 'Pending'
    assert win.file_list.item(0, 0).text().startswith('*')
    assert win.status_label.text() == str(a)


def test_open_folder_cancel_preserves_root(setup, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    win, a, b = setup
    win.artist_edit.setText('Pending')
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(b))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Cancel)
    win._open_folder()
    assert win.root_path == a
    assert win.artist_edit.text() == 'Pending'
    assert win._has_unsaved_changes()


def test_selection_signal_empty_payload(setup):
    win, a, b = setup
    observed = []
    win.file_list.files_selected.connect(observed.append)
    win.file_list.clearSelection()
    assert observed == [[]]
    assert_empty(win)


def test_saved_artwork_cleared_on_directory_change(setup):
    from audio_metadata_editor.metadata import write_mp3_metadata, write_m4b_metadata
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtCore import QBuffer, QIODevice
    win, a, b = setup
    image = QImage(4, 4, QImage.Format_RGB32)
    image.fill(QColor('red'))
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, 'PNG')
    path = win.current_file
    writer = write_mp3_metadata if path.suffix == '.mp3' else write_m4b_metadata
    writer(path, Metadata(), fields=set(), artwork=bytes(buffer.data()), artwork_mime='image/png')
    win._file_selected(str(path))
    assert not win.artwork_label.pixmap().isNull()
    change(win, b)
    assert_empty(win)
    assert read_metadata(path).artwork == bytes(buffer.data())


def ctrl_click(qtbot, widget, position):
    from PySide6.QtCore import Qt
    # A QTest mouse modifier annotates events but does not release that key.
    # Model the complete gesture, even when the click/assertions raise.
    try:
        qtbot.keyPress(widget, Qt.Key_Control)
        qtbot.mouseClick(widget, Qt.LeftButton, Qt.ControlModifier, position)
    finally:
        qtbot.keyRelease(widget, Qt.Key_Control)


@pytest.mark.parametrize('reply', [QMessageBox.Discard, QMessageBox.Cancel])
def test_ctrl_click_deselects_last_row(setup, qtbot, monkeypatch, reply):
    from PySide6.QtCore import Qt
    win, a, b = setup
    win.show()
    original = list(win.selected_files)
    win.artist_edit.setText('Pending')
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: prompts.append(args) or reply)
    table = win.file_list
    ctrl_click(qtbot, table.viewport(),
               table.visualItemRect(table.item(0, 0)).center())
    from PySide6.QtWidgets import QApplication
    assert QApplication.keyboardModifiers() == Qt.NoModifier
    assert len(prompts) == 1
    if reply == QMessageBox.Cancel:
        assert table.selected_paths_in_row_order() == original
        assert win.artist_edit.text() == 'Pending'
        assert win._has_unsaved_changes()
    else:
        assert_empty(win)
        assert not table.selected_paths_in_row_order()
        assert all(not table.item(row, 0).text().startswith('*')
                   for row in range(table.rowCount()))


@pytest.mark.parametrize('reply', [QMessageBox.Discard, QMessageBox.Cancel])
def test_refresh_from_child_retains_directory_and_tree_selection(setup, monkeypatch, reply):
    win, a, b = setup
    child = a / 'child'
    child.mkdir()
    shutil.copy2(win.current_file, child / win.current_file.name)
    change(win, child)
    win.file_list.setCurrentCell(0, 2)
    win.artist_edit.setText('Pending')
    previous_item = win.directory_tree.currentItem()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: reply)
    win._refresh_tree()
    expected = child
    assert Path(win.file_list.item(0, 0).data(256)).parent == expected
    assert win.status_label.text() == str(expected)
    assert win.directory_tree.currentItem() is previous_item
    if reply == QMessageBox.Cancel:
        assert win.artist_edit.text() == 'Pending'
    else:
        assert_empty(win)


def test_file_list_reload_signals(setup, qtbot, tmp_path):
    from audio_metadata_editor.ui.file_list import FileList
    win, a, b = setup
    table = FileList()
    qtbot.addWidget(table)
    observed, singles = [], []
    table.files_selected.connect(observed.append)
    table.file_selected.connect(singles.append)
    table.load_directory(a)
    assert observed == []  # Loading rows does not select one.
    table.setCurrentCell(0, 2)
    assert len(singles) == 1
    observed.clear()
    table.load_directory(b)
    assert observed == [[]]  # Removing selected rows clears selection.
    assert len(singles) == 1
    observed.clear()
    empty = tmp_path / 'empty'
    empty.mkdir()
    table.load_directory(empty)
    assert observed == []  # Already empty selection: no notification.
    assert table.rowCount() == 0


def test_tree_synchronization_preserves_pending_context(setup, monkeypatch):
    win, a, b = setup
    original = list(win.selected_files)
    win.artist_edit.setText('Pending')
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question',
                        lambda *args: prompts.append(args) or QMessageBox.Discard)
    win.directory_tree.set_current_directory(a)
    win.directory_tree.restore_current_directory()
    assert not prompts
    assert win.selected_files == original
    assert win.file_list.selected_paths_in_row_order() == original
    assert win.artist_edit.text() == 'Pending'
    assert win._has_unsaved_changes()
    assert win.file_list.item(0, 0).text().startswith('*')


@pytest.mark.parametrize('raises', [False, True])
def test_ctrl_click_releases_modifier_before_next_interaction(qtbot, monkeypatch, raises):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication, QWidget, QTableWidget, QAbstractItemView
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.show()
    if raises:
        mouse_click = qtbot.mouseClick
        def failed_click(*args):
            mouse_click(*args)
            assert QApplication.keyboardModifiers() == Qt.ControlModifier
            raise AssertionError('simulated failed interaction')
        monkeypatch.setattr(qtbot, 'mouseClick', failed_click)
        with pytest.raises(AssertionError, match='simulated failed interaction'):
            ctrl_click(qtbot, widget, QPoint(1, 1))
    else:
        ctrl_click(qtbot, widget, QPoint(1, 1))
    assert QApplication.keyboardModifiers() == Qt.NoModifier
    # A subsequent independent widget must replace, rather than extend, selection.
    table = QTableWidget(2, 1)
    qtbot.addWidget(table)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.setCurrentCell(0, 0)
    table.setCurrentCell(1, 0)
    assert [index.row() for index in table.selectedIndexes()] == [1]
