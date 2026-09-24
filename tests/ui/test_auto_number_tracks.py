from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QMessageBox, QToolBar
from mutagen.id3 import ID3, APIC, COMM, TRCK, TXXX, TIT2
from mutagen.mp4 import MP4, MP4Cover

from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def window(request, tmp_path, qtbot, monkeypatch):
    for name in ('a', 'b', 'c', 'd'):
        path = tmp_path / f'{name}.{request.param}'
        shutil.copy2(Path(__file__).parents[1] / 'fixtures' / f'silence.{request.param}', path)
        if request.param == 'mp3':
            tags = ID3(path)
            tags.add(TIT2(encoding=3, text=[name]))
            tags.add(TRCK(encoding=3, text=['4/17']))
            tags.add(COMM(encoding=3, lang='swe', desc='Other', text=['Keep']))
            tags.add(TXXX(encoding=3, desc='Unknown', text=['Keep']))
            tags.add(APIC(encoding=3, mime='image/jpeg', type=3, data=b'cover'))
            tags.save(path)
        else:
            audio = MP4(path)
            audio.tags['\xa9nam'] = [name]
            audio.tags['trkn'] = [(4, 17)]
            audio.tags['\xa9cmt'] = ['Keep']
            audio.tags['----:com.apple.iTunes:Unknown'] = [b'Keep']
            audio.tags['covr'] = [MP4Cover(b'cover')]
            audio.save()
    win = MainWindow()
    qtbot.addWidget(win)
    win.file_list.setSortingEnabled(False)
    win.file_list.load_directory(tmp_path)
    win.show()
    win.file_list.setCurrentCell(0, 1)
    def unexpected(*args):
        pytest.fail(f'Unexpected dialog: {args[1:]}')
    monkeypatch.setattr(QMessageBox, 'critical', unexpected)
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    yield win
    win.current_metadata = None
    win.selected_files = []
    win.multi_edit_fields.clear()


def paths(window):
    return [Path(window.file_list.item(row, 0).data(256))
            for row in range(window.file_list.rowCount())]


def run_dialog(window, start='1', cancel=False, invalid=None):
    def respond():
        dialog = window.findChild(QDialog)
        editor = dialog.findChild(QLineEdit)
        buttons = dialog.findChild(QDialogButtonBox)
        assert editor.text() == '1'
        if invalid is not None:
            editor.setText(invalid)
            assert not editor.hasAcceptableInput()
            assert not buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        editor.setText(start)
        buttons.button(QDialogButtonBox.StandardButton.Cancel if cancel else
                       QDialogButtonBox.StandardButton.Ok).click()
    QTimer.singleShot(0, respond)
    action = next(a for a in window.findChild(QToolBar).actions()
                  if a.text() == 'Auto-number Tracks…')
    action.trigger()


def raw_unrelated(path):
    if path.suffix == '.mp3':
        return {key: frame.pprint() for key, frame in ID3(path).items() if key != 'TRCK'}
    return {key: value for key, value in MP4(path).tags.items() if key != 'trkn'}


@pytest.mark.parametrize('start', ['1', '8'])
def test_single_preservation_and_clean_state(window, start):
    path = window.current_file
    before = read_metadata(path)
    raw = raw_unrelated(path)
    run_dialog(window, start)
    before.track_number = int(start)
    assert read_metadata(path) == before
    assert raw_unrelated(path) == raw
    assert read_metadata(path).track_total == 17
    assert window.current_metadata == before
    assert window.track_edit.text() == start
    assert window.file_list.item(0, 1).text() == start
    assert not window._has_unsaved_changes()
    assert not window.file_list.item(0, 0).text().startswith('*')
    window._file_selected(str(paths(window)[1]))  # No unsaved-change prompt.


@pytest.mark.parametrize('column', [0, 1])
def test_selected_visual_order(window, column):
    original = paths(window)
    table = window.file_list
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.SortOrder.DescendingOrder)
    if column == 1:
        table.sortItems(1, Qt.SortOrder.DescendingOrder)
    chosen = paths(window)[::2]
    table.select_files([str(p) for p in reversed(chosen)])
    before = {p: p.read_bytes() for p in original}
    run_dialog(window, '5')
    for p in original:
        if p in chosen:
            assert read_metadata(p).track_number == 5 + chosen.index(p)
        else:
            assert p.read_bytes() == before[p]
    for row, p in enumerate(paths(window)):
        assert table.item(row, 1).text() == str(read_metadata(p).track_number)
        assert table.item(row, 2).text() == read_metadata(p).title
    assert not window._has_unsaved_changes()


@pytest.mark.parametrize('multiple', [False, True])
def test_pending_panel_edits_survive(window, qtbot, multiple):
    if multiple:
        window.file_list.select_files([str(p) for p in paths(window)])
    window.artist_edit.selectAll()
    qtbot.keyClicks(window.artist_edit, 'Pending artist')
    window.track_total_edit.setText('25')
    run_dialog(window, '8')
    assert window.artist_edit.text() == 'Pending artist'
    assert window.track_total_edit.text() == '25'
    assert window._has_unsaved_changes()
    for p in paths(window):
        assert read_metadata(p).artist != 'Pending artist'
        assert read_metadata(p).track_total == 17
    if multiple:
        assert 'artist' in window.multi_edit_fields
        assert 'track_number' not in window.multi_edit_fields
    else:
        assert window.current_metadata.track_number == 8
        assert window.track_edit.text() == '8'
    window._undo_changes()


@pytest.mark.parametrize('invalid', ['0', '-1', '1.5', 'abc', ''])
def test_invalid_and_cancel_do_not_write(window, invalid, monkeypatch):
    before = {p: p.read_bytes() for p in paths(window)}
    monkeypatch.setattr(module, 'write_metadata', lambda *a, **k: pytest.fail('Unexpected write'))
    run_dialog(window, cancel=True, invalid=invalid)
    assert all(p.read_bytes() == data for p, data in before.items())
    assert not window._has_unsaved_changes()


def test_partial_failure(window, monkeypatch):
    ordered = paths(window)
    window.file_list.select_files([str(p) for p in ordered])
    before = {p: p.read_bytes() for p in ordered}
    writer = module.write_metadata
    calls, errors = [], []
    def fail_second(path, metadata, **kwargs):
        calls.append(path)
        assert kwargs == {'fields': {'track_number'}}
        if path == ordered[1]:
            raise OSError('Test write failure')
        writer(path, metadata, **kwargs)
    monkeypatch.setattr(module, 'write_metadata', fail_second)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    run_dialog(window, '8')
    assert calls == ordered[:2]
    assert read_metadata(ordered[0]).track_number == 8
    assert window.file_list.item(0, 1).text() == '8'
    assert window.current_metadata.track_number == 8
    for row, p in enumerate(ordered[1:], 1):
        assert p.read_bytes() == before[p]
        assert window.file_list.item(row, 1).text() == '4'
    assert len(errors) == 1
    assert str(ordered[1]) in errors[0][2]
    assert 'Test write failure' in errors[0][2]
    assert '1 file(s) saved' in errors[0][2]
    assert not window._has_unsaved_changes()


def test_no_selection(window, monkeypatch):
    window.file_list.clearSelection()  # The cached panel selection can remain stale.
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: messages.append(a))
    monkeypatch.setattr(module, 'write_metadata', lambda *a, **k: pytest.fail('Unexpected write'))
    window._auto_number_tracks()
    assert messages and 'Select at least one' in messages[0][2]
