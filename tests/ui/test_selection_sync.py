from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QLineEdit

from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow


@pytest.fixture(params=['mp3', 'm4b'])
def window(request, tmp_path, qtbot, monkeypatch):
    for name in 'abc':
        shutil.copy2(Path(__file__).parents[1] / 'fixtures' / f'silence.{request.param}',
                     tmp_path / f'{name}.{request.param}')
    win = MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: setattr(w, 'current_metadata', None))
    win.file_list.setSortingEnabled(False)
    win.file_list.load_directory(tmp_path)
    win.show()
    win.file_list.setCurrentCell(0, 2)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    yield win
    win.multi_edit_fields.clear()
    win.multi_edit_artwork = False
    win.selected_files = []


def paths(win):
    return [win.file_list.item(i, 0).data(256) for i in range(3)]


@pytest.mark.parametrize('target', [(0, 1), (1, 0), (1, 2)])
def test_dirty_single_to_multi_cancel(window, qtbot, monkeypatch, target):
    names = paths(window)
    qtbot.keyClicks(window.artist_edit, 'Pending')
    before = window.artist_edit.text()
    assert window._has_unsaved_changes()
    assert window.file_list.item(0, 0).text().startswith('*')
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: prompts.append(a) or QMessageBox.Cancel)
    window.file_list.select_files([names[i] for i in target])
    assert len(prompts) == 1
    assert window.selected_files == [names[0]]
    assert window.artist_edit.text() == before
    assert window.file_list.selected_paths_in_row_order() == [names[0]]


def test_enter_follows_next_file(window, qtbot):
    names = paths(window)
    for row in (0, 1):
        table = window.file_list
        if row == 0:
            table.editItem(table.item(row, 2))
        editor = table.focusWidget()
        assert isinstance(editor, QLineEdit)
        editor.selectAll()
        qtbot.keyClicks(editor, f'Title {row}')
        qtbot.keyClick(editor, Qt.Key_Return)
        qtbot.waitUntil(lambda: table.currentRow() == row + 1)
        qtbot.waitUntil(lambda: isinstance(table.focusWidget(), QLineEdit))
        assert window.current_file == Path(names[row + 1])
        assert window.current_metadata == read_metadata(Path(names[row + 1]))
        assert table.currentColumn() == 2


@pytest.mark.parametrize('initial,target', [((0,), (0, 1)), ((0,), (1, 2)),
                                            ((0, 1), (1, 2)), ((0, 1), (0,))])
@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_selection_transition(window, qtbot, monkeypatch, initial, target, reply):
    names = paths(window)
    window.file_list.select_files([names[i] for i in initial])
    window.artist_edit.selectAll()
    qtbot.keyClicks(window.artist_edit, 'Pending artist')
    before = {p: read_metadata(Path(p)) for p in names}
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: prompts.append(a) or reply)
    window.file_list.select_files([names[i] for i in target])
    assert len(prompts) == 1
    assert set(window.selected_files) == {names[i] for i in (initial if reply == QMessageBox.Cancel else target)}
    if reply == QMessageBox.Cancel:
        assert window.artist_edit.text() == 'Pending artist'
        assert window._has_unsaved_changes()
        assert window.file_list.currentRow() == 0
    else:
        assert not window._has_unsaved_changes()
    for i, p in enumerate(names):
        expected = 'Pending artist' if reply == QMessageBox.Save and i in initial else before[p].artist
        assert read_metadata(Path(p)).artist == expected


@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_enter_pending_context(window, qtbot, monkeypatch, reply):
    names = paths(window)
    original = read_metadata(Path(names[0]))
    window.artist_edit.setText('Pending artist')
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: prompts.append(a) or reply)
    table = window.file_list
    table.setCurrentCell(0, 1)
    table.editItem(table.item(0, 1))
    editor = table.focusWidget()
    editor.selectAll()
    qtbot.keyClicks(editor, '9')
    qtbot.keyClick(editor, Qt.Key_Return)
    qtbot.wait(10)
    assert len(prompts) == 1
    saved = read_metadata(Path(names[0]))
    assert saved.track_number == 9
    assert saved.track_total == original.track_total
    assert saved.artist == ('Pending artist' if reply == QMessageBox.Save else original.artist)
    if reply == QMessageBox.Cancel:
        assert table.currentRow() == 0
        assert window.artist_edit.text() == 'Pending artist'
        assert window._has_unsaved_changes()
    else:
        assert table.currentRow() == 1
        assert window.current_file == Path(names[1])
        assert not window._has_unsaved_changes()


def test_clean_transitions_do_not_prompt(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: pytest.fail('Unexpected prompt'))
    names = paths(window)
    for selected in (names[:2], names[1:], names[:1]):
        window.file_list.select_files(selected)
        assert set(window.selected_files) == set(selected)
        assert not window._has_unsaved_changes()


def test_sorted_enter_follows_visual_row(window, qtbot):
    table = window.file_list
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.DescendingOrder)
    table.setCurrentCell(0, 1)
    next_path = Path(table.item(1, 0).data(256))
    table.editItem(table.item(0, 1))
    editor = table.focusWidget()
    editor.selectAll()
    qtbot.keyClicks(editor, '8')
    qtbot.keyClick(editor, Qt.Key_Return)
    qtbot.waitUntil(lambda: window.current_file == next_path)
    assert table.isSortingEnabled()
    assert table.horizontalHeader().sortIndicatorOrder() == Qt.DescendingOrder
    assert table.currentColumn() == 1


def test_failed_prompt_save_cancels_transition(window, qtbot, monkeypatch):
    import audio_metadata_editor.ui.main_window as module
    names = paths(window)
    window.artist_edit.setText('Pending')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Save)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a))
    def fail(*a, **kw):
        raise OSError('write failed')
    monkeypatch.setattr(module, 'write_mp3_metadata', fail)
    monkeypatch.setattr(module, 'write_m4b_metadata', fail)
    window.file_list.select_files(names[1:])
    assert errors
    assert window.selected_files == [names[0]]
    assert window.artist_edit.text() == 'Pending'
    assert window.file_list.selected_paths_in_row_order() == [names[0]]
