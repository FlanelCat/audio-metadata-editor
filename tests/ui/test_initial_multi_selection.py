from pathlib import Path
import shutil

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata, write_m4b_metadata
from audio_metadata_editor.ui.main_window import MainWindow


@pytest.fixture
def make_window(tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    def make(formats, artwork=()):
        paths = []
        for i, suffix in enumerate(formats):
            path = tmp_path / f'file-{i}.{suffix}'
            shutil.copy2(audio_fixture_dir / f'silence.{suffix}', path)
            writer = write_mp3_metadata if suffix == 'mp3' else write_m4b_metadata
            writer(path, Metadata(), fields=set(),
                   artwork=b'cover' if i in artwork else None, artwork_mime='image/jpeg')
            paths.append(str(path))
        win = MainWindow()
        qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
        win.root_path = tmp_path
        win._populate_root()
        win.file_list.setSortingEnabled(False)
        assert win.current_file is win.current_metadata is None
        assert win.selected_files == []
        assert win.file_list.selected_paths_in_row_order() == []
        monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
        return win, paths
    return make


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
@pytest.mark.parametrize('choice', ['save', 'discard', 'cancel', 'fail'])
def test_initial_multi_close(make_window, qtbot, monkeypatch, suffix, choice):
    import audio_metadata_editor.ui.main_window as module
    win, paths = make_window([suffix] * 2)
    win.file_list.select_files(paths)
    qtbot.keyClicks(win.artist_edit, 'Pending')
    before = {p: Path(p).read_bytes() for p in paths}
    prompts, errors = [], []
    reply = {'save': QMessageBox.Save, 'fail': QMessageBox.Save,
             'discard': QMessageBox.Discard, 'cancel': QMessageBox.Cancel}[choice]
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: prompts.append(args) or reply)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args))
    if choice == 'fail':
        def fail(*args, **kwargs):
            raise OSError('write failed')
        monkeypatch.setattr(module, 'write_mp3_metadata', fail)
        monkeypatch.setattr(module, 'write_m4b_metadata', fail)
    event = QCloseEvent()
    win.closeEvent(event)
    assert len(prompts) == 1
    assert '2 files' in prompts[0][2]
    assert event.isAccepted() == (choice in ('save', 'discard'))
    assert bool(errors) == (choice == 'fail')
    if choice in ('cancel', 'fail'):
        assert win.artist_edit.text() == 'Pending'
        assert win.file_list.selected_paths_in_row_order() == paths
        assert win._has_unsaved_changes()
    for p in paths:
        if choice == 'save':
            assert read_metadata(Path(p)).artist == 'Pending'
        else:
            assert Path(p).read_bytes() == before[p]


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
@pytest.mark.parametrize('artwork', [(), (0,), (0, 1)])
@pytest.mark.parametrize('finish', ['save', 'undo', 'discard'])
def test_initial_multi_remove(make_window, monkeypatch, suffix, artwork, finish):
    win, paths = make_window([suffix] * 2, artwork)
    win.file_list.select_files(paths)
    assert win.current_metadata is None
    before = {p: Path(p).read_bytes() for p in paths}
    for _ in range(2):
        win._remove_artwork()
        assert win.multi_edit_artwork == bool(artwork)
        assert win._has_unsaved_changes() == bool(artwork)
        assert win.artwork_label.pixmap().isNull()
        assert win.artwork_label.text() == ''
        for row in range(2):
            item = win.file_list.item(row, 0)
            assert item.text().startswith('*') == (paths.index(item.data(256)) in artwork)
        assert all(Path(p).read_bytes() == before[p] for p in paths)
    if finish == 'save':
        win._save_changes()
    elif finish == 'undo':
        win._undo_changes()
    else:
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Discard)
        win.file_list.clearSelection()
    assert not win._has_unsaved_changes()
    for i, p in enumerate(paths):
        assert read_metadata(Path(p)).artwork == (None if finish == 'save' or i not in artwork else b'cover')
        if finish != 'save' or i not in artwork:
            assert Path(p).read_bytes() == before[p]
    if finish == 'undo' and artwork:
        assert win.artwork_label.text() == ('Multiple artworks' if len(artwork) == 2 else 'Mixed artwork')


@pytest.mark.parametrize('prior', [None, 'mp3', 'm4b'])
@pytest.mark.parametrize('formats,enabled', [(['mp3', 'mp3'], True),
                                            (['m4b', 'm4b'], False),
                                            (['mp3', 'm4b'], False)])
def test_comment_availability(make_window, prior, formats, enabled):
    win, paths = make_window(formats + ([prior] if prior else []))
    if prior:
        win.file_list.select_files(paths[-1:])
    win.file_list.select_files(paths[:2])
    assert win.id3v1_comment_edit.isEnabled() == enabled
    assert not win._has_unsaved_changes()


def test_close_does_not_name_previous_single(make_window, qtbot, monkeypatch):
    win, paths = make_window(['mp3'] * 3)
    win.file_list.select_files(paths[2:])
    win.file_list.select_files(paths[:2])
    qtbot.keyClicks(win.artist_edit, 'Pending')
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: prompts.append(args) or QMessageBox.Cancel)
    win.closeEvent(QCloseEvent())
    assert Path(paths[2]).name not in prompts[0][2]
    assert '2 files' in prompts[0][2]


@pytest.mark.parametrize('target', ['multi', 'single', 'empty', 'directory'])
@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_initial_multi_transitions(make_window, qtbot, monkeypatch, tmp_path, target, reply):
    win, paths = make_window(['mp3', 'm4b', 'mp3'])
    win.file_list.select_files(paths[:2])
    qtbot.keyClicks(win.artist_edit, 'Pending')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: reply)
    requested = paths[1:] if target == 'multi' else paths[2:] if target == 'single' else []
    if target == 'directory':
        directory = tmp_path / 'empty'
        directory.mkdir()
        win._directory_selected(directory)
    else:
        win.file_list.select_files(requested)
    if reply == QMessageBox.Cancel:
        assert win.selected_files == paths[:2]
        assert win.file_list.selected_paths_in_row_order() == paths[:2]
        assert win.artist_edit.text() == 'Pending'
        assert win._has_unsaved_changes()
    else:
        assert win.selected_files == requested
        assert not win._has_unsaved_changes()
        assert win.id3v1_comment_edit.isEnabled() == (target == 'single')
        if not requested:
            assert win.current_file is win.current_metadata is None
    for p in paths[:2]:
        assert read_metadata(Path(p)).artist == ('Pending' if reply == QMessageBox.Save else '')


@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_actual_window_close(make_window, qtbot, monkeypatch, reply):
    win, paths = make_window(['mp3', 'm4b'])
    win.file_list.select_files(paths)
    qtbot.keyClicks(win.artist_edit, 'Pending')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: reply)
    win.show()
    assert win.close() == (reply != QMessageBox.Cancel)
    assert win.isVisible() == (reply == QMessageBox.Cancel)
    if reply == QMessageBox.Cancel:
        assert win.selected_files == paths
        assert win.artist_edit.text() == 'Pending'


def test_initial_mp3_comment_save(make_window, qtbot):
    win, paths = make_window(['mp3', 'mp3'])
    win.file_list.select_files(paths)
    assert win.id3v1_comment_edit.isEnabled()
    qtbot.keyClicks(win.id3v1_comment_edit, 'Pending comment')
    assert 'id3v1_comment' in win.multi_edit_fields
    assert all(read_metadata(Path(p)).id3v1_comment == '' for p in paths)
    win._save_changes()
    assert all(read_metadata(Path(p)).id3v1_comment == 'Pending comment' for p in paths)
    assert win.id3v1_comment_edit.isEnabled()
    assert not win._has_unsaved_changes()
