from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QMessageBox

from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow


@pytest.fixture(params=['mp3', 'm4b'])
def window(request, tmp_path, qtbot, monkeypatch):
    master = Path(__file__).parents[1] / 'fixtures' / f'silence.{request.param}'
    for name in ('a', 'b'):
        shutil.copy2(master, tmp_path / f'{name}.{request.param}')
    window = MainWindow()
    qtbot.addWidget(window)
    window.file_list.setSortingEnabled(False)
    window.file_list.load_directory(tmp_path)
    window.show()
    window.file_list.setCurrentCell(0, 2)
    def unexpected(*args):
        pytest.fail(f'Unexpected dialog: {args[1:]}')
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    monkeypatch.setattr(QMessageBox, 'critical', unexpected)
    yield window
    window.current_metadata = None
    window.selected_files = []


def edit_cell(window, qtbot, row=0, column=2):
    table = window.file_list
    table.setCurrentCell(row, column)
    table.editItem(table.item(row, column))
    editor = table.focusWidget()
    assert isinstance(editor, QLineEdit)
    editor.selectAll()
    return editor


def test_enter_saves_and_advances(window, qtbot):
    table = window.file_list
    path = Path(table.item(0, 0).data(256))
    before = read_metadata(path)
    trace = []
    table.itemChanged.connect(lambda item: trace.append(('itemChanged', item.column())))
    table.itemDelegate().commitData.connect(lambda editor: trace.append(('commitData', editor.text())))
    table.itemDelegate().closeEditor.connect(lambda *args: trace.append(('closeEditor',)))
    table.save_cell_requested.connect(lambda *args: trace.append(('save', args)))
    editor = edit_cell(window, qtbot)
    qtbot.keyClicks(editor, 'Regression title')
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: table.currentRow() == 1 and isinstance(table.focusWidget(), QLineEdit))
    assert [entry[0] for entry in trace if entry[0] != 'itemChanged'] == [
        'commitData', 'closeEditor', 'save',
    ]
    saved = read_metadata(path)
    assert saved.title == 'Regression title'
    before.title = saved.title
    assert saved == before
    assert window.current_metadata.title == saved.title
    assert window.title_edit.text() == saved.title
    assert not window._has_unsaved_changes()
    assert not table.item(0, 0).text().startswith('*')
    assert table.currentColumn() == 2
    # Stop the automatic editor by moving focus, then navigate away.
    window.title_edit.setFocus()
    qtbot.wait(10)
    assert not window._has_unsaved_changes()
    window._file_selected(table.item(1, 0).data(256))


def test_same_value_is_clean(window, qtbot):
    path = window.current_file
    original = path.read_bytes()
    editor = edit_cell(window, qtbot)
    value = editor.text()
    qtbot.keyClicks(editor, value)
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(10)
    window.title_edit.setFocus()
    qtbot.wait(10)
    assert not window._has_unsaved_changes()
    assert path.read_bytes() == original


@pytest.mark.parametrize('column,field,value', [
    (1, 'track_number', '7'), (3, 'artist', 'New artist'),
    (4, 'album', 'New album'), (5, 'series', 'New series'),
    (6, 'series_number', '2.5'), (7, 'narrator', 'New narrator'),
])
def test_other_columns(window, qtbot, column, field, value):
    path = window.current_file
    editor = edit_cell(window, qtbot, column=column)
    qtbot.keyClicks(editor, value)
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(10)
    expected = int(value) if column == 1 else value
    assert getattr(read_metadata(path), field) == expected
    assert getattr(window.current_metadata, field) == expected
    assert not window._has_unsaved_changes()
    assert window.file_list.currentColumn() == column


def test_panel_pending_changes_survive_table_save(window, qtbot):
    path = window.current_file
    before = read_metadata(path)
    window.artist_edit.setFocus()
    window.artist_edit.selectAll()
    qtbot.keyClicks(window.artist_edit, 'Pending artist')
    qtbot.keyClick(window.artist_edit, Qt.Key.Key_Return)
    assert read_metadata(path) == before
    assert window._has_unsaved_changes()
    editor = edit_cell(window, qtbot)
    qtbot.keyClicks(editor, 'Saved title')
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(10)
    assert read_metadata(path).artist == before.artist
    assert window.artist_edit.text() == 'Pending artist'
    assert window.current_metadata.title == 'Saved title'
    assert window._has_unsaved_changes()
    window.artist_edit.setText(before.artist)
    assert not window._has_unsaved_changes()
    assert not window.file_list.item(0, 0).text().startswith('*')


def test_failed_save_keeps_loaded_state(window, qtbot, monkeypatch):
    import audio_metadata_editor.ui.main_window as module
    before = read_metadata(window.current_file)
    errors = []
    def fail(*args, **kwargs):
        raise OSError('Write failed')
    monkeypatch.setattr(module, 'write_mp3_metadata', fail)
    monkeypatch.setattr(module, 'write_m4b_metadata', fail)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    editor = edit_cell(window, qtbot)
    qtbot.keyClicks(editor, 'Failed title')
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(10)
    assert errors
    assert window.current_metadata == before
    assert read_metadata(window.current_file) == before
    assert window.file_list.item(0, 2).text() == before.title
    assert not window._has_unsaved_changes()


def test_unrelated_raw_tags_and_artwork_preserved(window, qtbot):
    from mutagen.id3 import ID3, APIC, TPE1, TXXX, COMM
    from mutagen.mp4 import MP4, MP4Cover

    path = window.current_file
    if path.suffix == '.mp3':
        tags = ID3(path)
        tags.add(TPE1(encoding=3, text=['First artist', 'Second artist']))
        tags.add(TXXX(encoding=3, desc='Unknown field', text=['Keep me']))
        tags.add(COMM(encoding=3, lang='swe', desc='Other comment', text=['Keep']))
        for kind in (3, 4):
            tags.add(APIC(encoding=3, mime='image/jpeg', type=kind,
                          desc=str(kind), data=b'artwork' + bytes([kind])))
        tags.save(path)
        def snapshot():
            return {key: frame.pprint() for key, frame in ID3(path).items()
                    if key != 'TIT2'}
    else:
        audio = MP4(path)
        audio.tags['\xa9ART'] = ['First artist', 'Second artist']
        audio.tags['----:com.apple.iTunes:Unknown'] = [b'Keep me']
        audio.tags['covr'] = [MP4Cover(b'front'), MP4Cover(b'back')]
        audio.save()
        def snapshot():
            return {key: value for key, value in MP4(path).tags.items()
                    if key != '\xa9nam'}
    before = snapshot()
    window._file_selected(str(path))
    editor = edit_cell(window, qtbot)
    qtbot.keyClicks(editor, 'Preservation title')
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(10)
    assert snapshot() == before
    assert not window._has_unsaved_changes()


def test_last_row_enter_and_unchanged_focus_out(window, qtbot):
    table = window.file_list
    editor = edit_cell(window, qtbot, row=1)
    path = window.current_file
    before = path.read_bytes()
    window.title_edit.setFocus()
    qtbot.wait(10)
    assert path.read_bytes() == before
    assert not window._has_unsaved_changes()
    editor = edit_cell(window, qtbot, row=1)
    qtbot.keyClicks(editor, 'Last row title')
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.wait(10)
    assert table.currentRow() == 1
    assert read_metadata(path).title == 'Last row title'
    assert not window._has_unsaved_changes()


def test_panel_explicit_save(window, qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    window.title_edit.setText('Panel saved title')
    assert window._has_unsaved_changes()
    window._save_changes()
    assert read_metadata(window.current_file).title == 'Panel saved title'
    assert not window._has_unsaved_changes()
