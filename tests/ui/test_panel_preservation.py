from pathlib import Path
import shutil

import pytest
from mutagen.id3 import ID3, APIC, COMM, TPE1, TRCK, TPOS, TXXX
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm, AtomDataType
from PySide6.QtWidgets import QMessageBox, QFileDialog

from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow


def snapshot(path, group):
    if path.suffix == '.mp3':
        tags = ID3(path)
        prefixes = {'artist': ('TPE1',), 'comments': ('COMM',),
                    'custom': ('TXXX:Narrator', 'TXXX:Series'), 'artwork': ('APIC',),
                    'unknown': ('TXXX:Unknown',), 'pairs': ('TRCK', 'TPOS')}
        return {k: repr(v) for k, v in tags.items() if k.startswith(prefixes[group])}
    tags = MP4(path).tags
    keys = {'artist': ['\xa9ART'], 'comments': ['\xa9cmt'],
            'custom': ['----:com.apple.iTunes:Narrator', '----:com.apple.iTunes:Series'],
            'artwork': ['covr'], 'unknown': ['----:com.apple.iTunes:Unknown'],
            'pairs': ['trkn', 'disk']}
    return {k: [(bytes(v), getattr(v, 'dataformat', None), getattr(v, 'imageformat', None))
                if isinstance(v, bytes) else v for v in tags.get(k, [])] for k in keys[group]}


@pytest.fixture(params=['mp3', 'm4b'])
def window(request, tmp_path, qtbot, monkeypatch):
    master = Path(__file__).parents[1] / 'fixtures' / f'silence.{request.param}'
    for name in ('a', 'b'):
        path = tmp_path / f'{name}.{request.param}'
        shutil.copy2(master, path)
        if request.param == 'mp3':
            tags = ID3(path)
            tags.add(TPE1(encoding=3, text=[name, 'Second artist']))
            tags.add(TRCK(encoding=3, text=['4/17']))
            tags.add(TPOS(encoding=3, text=['2/5']))
            for desc in ('', 'ID3v1 Comment', 'Other'):
                for lang in ('eng', 'swe'):
                    tags.add(COMM(encoding=1, lang=lang, desc=desc, text=[name, 'Second comment']))
            for desc in ('Narrator', 'Series', 'Unknown'):
                tags.add(TXXX(encoding=1, desc=desc, text=[name, 'Second value']))
            for kind in (3, 4):
                tags.add(APIC(encoding=1, mime='image/jpeg', type=kind,
                              desc=str(kind), data=b'cover' + bytes([kind])))
            tags.save(path)
        else:
            audio = MP4(path)
            audio.tags['\xa9ART'] = [name, 'Second artist']
            audio.tags['\xa9cmt'] = [name, 'Second comment']
            audio.tags['trkn'] = [(4, 17)]
            audio.tags['disk'] = [(2, 5)]
            for field in ('Narrator', 'Series', 'Unknown'):
                audio.tags[f'----:com.apple.iTunes:{field}'] = [
                    MP4FreeForm(name.encode(), dataformat=AtomDataType.UTF8),
                    MP4FreeForm(b'Second value', dataformat=AtomDataType.UTF8)]
            audio.tags['covr'] = [MP4Cover(b'front'), MP4Cover(b'back', imageformat=14)]
            audio.save()
    win = MainWindow()
    def cleanup(w):
        w.current_metadata = None
        w.selected_files = []
        w.multi_edit_fields.clear()
        w.multi_edit_artwork = False
    qtbot.addWidget(win, before_close_func=cleanup)
    win.file_list.setSortingEnabled(False)
    win.file_list.load_directory(tmp_path)
    win.file_list.setCurrentCell(0, 2)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: pytest.fail(str(a)))
    return win


def paths(window):
    return [Path(window.file_list.item(row, 0).data(256)) for row in range(2)]


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('group', ['artist', 'comments', 'custom', 'artwork', 'unknown', 'pairs'])
def test_title_save_preserves_unedited_tags(window, qtbot, multiple, group):
    targets = paths(window) if multiple else [window.current_file]
    before = {p: snapshot(p, group) for p in targets}
    if multiple:
        window.file_list.select_files([str(p) for p in targets])
    window.title_edit.selectAll()
    qtbot.keyClicks(window.title_edit, 'Changed title')
    window._save_changes()
    for p in targets:
        assert read_metadata(p).title == 'Changed title'
        assert snapshot(p, group) == before[p]
    assert window.current_metadata == read_metadata(window.current_file)
    assert not window._has_unsaved_changes()
    assert not window.file_list.item(0, 0).text().startswith('*')


@pytest.mark.parametrize('prefix', ['track', 'disc'])
@pytest.mark.parametrize('multiple', [False, True])
def test_clear_number_preserves_total(window, qtbot, prefix, multiple):
    targets = paths(window) if multiple else [window.current_file]
    if multiple:
        window.file_list.select_files([str(p) for p in targets])
    editor = getattr(window, f'{prefix}_edit')
    editor.selectAll()
    from PySide6.QtCore import Qt
    qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    window._save_changes()
    for path in targets:
        saved = read_metadata(path)
        assert getattr(saved, f'{prefix}_number') is None
        assert getattr(saved, f'{prefix}_total') == (17 if prefix == 'track' else 5)
    assert not window._has_unsaved_changes()


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('action', ['remove', 'choose_same', 'paste_same'])
def test_explicit_artwork_intent(window, qtbot, monkeypatch, tmp_path, multiple, action):
    from PySide6.QtCore import QBuffer, QIODevice, QTimer
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor('blue'))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'PNG')
    cover = bytes(buffer.data())
    targets = paths(window) if multiple else [window.current_file]
    for path in targets:
        if path.suffix == '.mp3':
            tags = ID3(path)
            tags.delall('APIC')
            for kind in (3, 4):
                tags.add(APIC(encoding=3, mime='image/png', type=kind, desc=str(kind), data=cover))
            tags.save(path)
        else:
            audio = MP4(path)
            audio.tags['covr'] = [MP4Cover(cover, imageformat=14), MP4Cover(cover, imageformat=14)]
            audio.save()
    window._file_selected(str(targets[0]))
    window._copy_metadata()
    if multiple:
        window.file_list.select_files([str(p) for p in targets])
    before = {p: p.read_bytes() for p in targets}
    unrelated = {p: snapshot(p, 'artist') for p in targets}
    if action == 'remove':
        window._remove_artwork()
    elif action == 'choose_same':
        image_path = tmp_path / 'cover.png'
        image_path.write_bytes(cover)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(image_path), ''))
        window._choose_artwork()
    else:
        def accept_artwork():
            dialog = QApplication.activeModalWidget()
            for checkbox in dialog.findChildren(QCheckBox):
                checkbox.setChecked(checkbox.text() == 'Artwork')
            next(button for button in dialog.findChildren(QPushButton) if button.text() == 'Paste').click()
        QTimer.singleShot(0, accept_artwork)
        window._paste_metadata()
    assert window._has_unsaved_changes()
    assert all(p.read_bytes() == before[p] for p in targets)
    window._save_changes()
    for path in targets:
        assert read_metadata(path).artwork == (None if action == 'remove' else cover)
        entries = ID3(path).getall('APIC') if path.suffix == '.mp3' else MP4(path).tags.get('covr', [])
        assert len(entries) == (0 if action == 'remove' else 1)
        assert snapshot(path, 'artist') == unrelated[path]
    assert not window._has_unsaved_changes()
    assert not window.artwork_edited
    # A later text-only save must once again omit artwork.
    before_artwork = {p: snapshot(p, 'artwork') for p in targets}
    window.title_edit.selectAll()
    qtbot.keyClicks(window.title_edit, 'Another title')
    window._save_changes()
    assert all(snapshot(p, 'artwork') == before_artwork[p] for p in targets)


def test_restored_field_is_not_written(window):
    before = snapshot(window.current_file, 'artist')
    original = window.artist_edit.text()
    window.artist_edit.setText('Temporary change')
    window.artist_edit.setText(original)
    window.title_edit.setText('Changed title')
    window._save_changes()
    assert snapshot(window.current_file, 'artist') == before
    assert not window._has_unsaved_changes()


def test_failed_artwork_save_keeps_intent_and_undo_clears_it(window, monkeypatch):
    import audio_metadata_editor.ui.main_window as module
    before = window.current_file.read_bytes()
    original = read_metadata(window.current_file)
    window._remove_artwork()
    assert window.file_list.item(0, 0).text().startswith('*')
    def fail(*args, **kwargs):
        assert kwargs['fields'] == set()
        assert kwargs['artwork'] is None
        raise OSError('Failed write')
    errors = []
    monkeypatch.setattr(module, 'write_mp3_metadata', fail)
    monkeypatch.setattr(module, 'write_m4b_metadata', fail)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a))
    window._save_changes()
    assert errors
    assert window.artwork_edited
    assert window._has_unsaved_changes()
    assert window.current_metadata == original
    assert window.current_file.read_bytes() == before
    window._undo_changes()
    assert not window.artwork_edited
    assert not window._has_unsaved_changes()
    assert window.pending_artwork == original.artwork
