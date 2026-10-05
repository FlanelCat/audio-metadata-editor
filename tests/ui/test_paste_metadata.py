from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox, QPushButton

from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata, write_m4b_metadata
from audio_metadata_editor.ui.main_window import MainWindow
import audio_metadata_editor.ui.main_window as module


# Preserve the complete existing order, wording, and logical identifiers.
FIELDS = [
    ('title', 'Title'), ('artist', 'Artist'), ('album', 'Album'),
    ('album_artist', 'Album Artist'), ('genre', 'Genre'),
    ('track_number', 'Track'), ('track_total', 'Track Total'),
    ('disc_number', 'Disc'), ('disc_total', 'Disc Total'),
    ('narrator', 'Narrator'), ('series', 'Series'),
    ('series_number', 'Series Number'), ('publisher', 'Publisher'),
    ('date', 'Date'), ('composer', 'Composer'), ('comment', 'Comment'),
    ('id3v1_comment', 'ID3v1 Comment'), ('copyright', 'Copyright'),
    ('description', 'Description'), ('artwork', 'Artwork'),
]


@pytest.fixture(params=['mp3', 'm4b'])
def window(request, tmp_path, qtbot, monkeypatch, audio_fixture_dir):
    master = audio_fixture_dir / f'silence.{request.param}'
    writer = write_mp3_metadata if request.param == 'mp3' else write_m4b_metadata
    for name in ('a', 'b'):
        path = tmp_path / f'{name}.{request.param}'
        shutil.copy2(master, path)
        writer(path, Metadata(), artwork=b'original artwork', artwork_mime='image/jpeg', fields=set())
    win = MainWindow()
    def cleanup(widget):
        widget.current_metadata = None
        widget.selected_files = []
        widget.multi_edit_fields.clear()
        widget.multi_edit_artwork = False
    qtbot.addWidget(win, before_close_func=cleanup)
    win.file_list.setSortingEnabled(False)
    win.file_list.load_directory(tmp_path)
    win.show()
    win.file_list.setCurrentCell(0, 2)
    win.metadata_clipboard = Metadata(title='Copied title', artist='Not selected',
                                      artwork=b'copied artwork', artwork_mime='image/png')
    def unexpected(*args, **kwargs):
        pytest.fail('Unexpected metadata write or prompt')
    for name in ('write_metadata', 'write_mp3_metadata', 'write_m4b_metadata'):
        monkeypatch.setattr(module, name, unexpected)
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    monkeypatch.setattr(QMessageBox, 'critical', unexpected)
    return win


def paste(window, selected, initial, cancel=False):
    def respond():
        dialog = QApplication.activeModalWidget()
        assert dialog.windowTitle() == 'Paste Metadata'
        boxes = dialog.findChildren(QCheckBox)
        assert [box.text() for box in boxes] == [label for _, label in FIELDS]
        assert {field for (field, _), box in zip(FIELDS, boxes) if box.isChecked()} == initial
        for (field, _), box in zip(FIELDS, boxes):
            box.setChecked(field in selected)
        next(button for button in dialog.findChildren(QPushButton)
             if button.text() == ('Cancel' if cancel else 'Paste')).click()
    QTimer.singleShot(0, respond)
    window._paste_metadata()


def disk_snapshot(window):
    return {Path(window.file_list.item(row, 0).data(256)):
            Path(window.file_list.item(row, 0).data(256)).read_bytes()
            for row in range(window.file_list.rowCount())}


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('artwork', [b'copied artwork', None])
def test_paste_pending_values_and_artwork(window, multiple, artwork):
    before = disk_snapshot(window)
    if multiple:
        window.file_list.select_files([str(path) for path in before])
    window.metadata_clipboard.artwork = artwork
    window.metadata_clipboard.artwork_mime = 'image/png' if artwork else ''
    baseline = read_metadata(window.current_file)
    artist = window.artist_edit.text()
    paste(window, {'title', 'artwork'}, set())
    assert window.paste_metadata_fields == {'title', 'artwork'}
    assert window.title_edit.text() == 'Copied title'
    assert window.artist_edit.text() == artist
    assert window.pending_artwork == artwork
    assert window.pending_artwork_mime == ('image/png' if artwork else '')
    assert window.current_metadata == baseline
    assert window._has_unsaved_changes()
    assert window.multi_edit_artwork == multiple
    if multiple:
        assert window.multi_edit_fields == {'title'}
    for row in range(2 if multiple else 1):
        assert window.file_list.item(row, 2).text() == 'Copied title'
        assert window.file_list.item(row, 0).text().startswith('*')
    assert disk_snapshot(window) == before
    # Subsequent cancellation must preserve pending edits and remembered artwork.
    paste(window, {'artist'}, {'title', 'artwork'}, cancel=True)
    assert window.paste_metadata_fields == {'title', 'artwork'}
    assert window.title_edit.text() == 'Copied title'
    assert window.pending_artwork == artwork
    assert window._has_unsaved_changes()
    assert disk_snapshot(window) == before


def test_cancel_and_empty_acceptance(window, monkeypatch):
    before = disk_snapshot(window)
    remembered = {'title', 'artwork'}
    window.paste_metadata_fields = remembered
    title = window.title_edit.text()
    paste(window, {'artist'}, remembered, cancel=True)
    assert window.paste_metadata_fields is remembered
    assert remembered == {'title', 'artwork'}
    assert window.title_edit.text() == title
    assert not window._has_unsaved_changes()
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: messages.append(args))
    paste(window, set(), remembered)
    assert window.paste_metadata_fields == set()
    assert remembered == {'title', 'artwork'}
    assert messages[-1][2] == 'No fields were selected.'
    assert window.title_edit.text() == title
    assert not window._has_unsaved_changes()
    paste(window, set(), set(), cancel=True)
    assert disk_snapshot(window) == before


def png_bytes(color):
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'PNG')
    return bytes(buffer.data())


def assert_preview(window, color):
    from PySide6.QtGui import QColor
    pixmap = window.artwork_label.pixmap()
    if color is None:
        assert pixmap.isNull()
        assert window.artwork_label.text() == ''
    else:
        assert not pixmap.isNull()
        assert pixmap.toImage().pixelColor(0, 0) == QColor(color)


@pytest.mark.parametrize('removal', [False, True])
@pytest.mark.parametrize('finish', ['save', 'undo', 'discard', 'cancel_paste'])
def test_pasted_artwork_preview_lifecycle(window, monkeypatch, removal, finish):
    target = window.current_file
    source = Path(window.file_list.item(1, 0).data(256))
    writer = write_mp3_metadata if target.suffix == '.mp3' else write_m4b_metadata
    original = png_bytes('red')
    copied = None if removal else png_bytes('blue')
    writer(target, Metadata(), artwork=original, artwork_mime='image/png', fields=set())
    writer(source, Metadata(), artwork=copied, artwork_mime='image/png', fields=set())
    # Exercise the actual copy workflow rather than inventing clipboard semantics.
    window._file_selected(str(source))
    window._copy_metadata()
    window._file_selected(str(target))
    assert_preview(window, 'red')
    before = disk_snapshot(window)
    paste(window, {'artwork'}, set(), cancel=finish == 'cancel_paste')
    assert disk_snapshot(window) == before
    if finish == 'cancel_paste':
        assert_preview(window, 'red')
        assert window.pending_artwork == original
        assert not window._has_unsaved_changes()
        return
    assert window.pending_artwork == copied
    assert window.pending_artwork_mime == ('' if removal else 'image/png')
    assert_preview(window, None if removal else 'blue')
    assert window._has_unsaved_changes()
    assert window.file_list.item(0, 0).text().startswith('*')
    assert read_metadata(target).artwork == original

    if finish == 'save':
        # Only the explicit save is allowed to reach the real writer.
        monkeypatch.setattr(module, 'write_mp3_metadata', write_mp3_metadata)
        monkeypatch.setattr(module, 'write_m4b_metadata', write_m4b_metadata)
        monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
        window._save_changes()
        assert read_metadata(target).artwork == copied
        assert window.current_metadata == read_metadata(target)
        assert_preview(window, None if removal else 'blue')
    elif finish == 'undo':
        window._undo_changes()
        assert window.pending_artwork == original
        assert_preview(window, 'red')
        assert disk_snapshot(window) == before
    else:
        prompts = []
        def cancel(*args):
            prompts.append(args)
            return QMessageBox.StandardButton.Cancel
        monkeypatch.setattr(QMessageBox, 'question', cancel)
        window._file_selected(str(source))
        assert prompts and prompts[0][1] == 'Unsaved Changes'
        assert window.current_file == target
        assert window._has_unsaved_changes()
        assert_preview(window, None if removal else 'blue')
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Discard)
        window._file_selected(str(source))
        window._file_selected(str(target))
        assert window.pending_artwork == original
        assert_preview(window, 'red')
        assert disk_snapshot(window) == before
    assert not window._has_unsaved_changes()
    assert not window.file_list.item(0, 0).text().startswith('*')


@pytest.mark.parametrize('removal', [False, True])
def test_multi_paste_artwork_preview_and_undo(window, removal):
    paths = list(disk_snapshot(window))
    window.file_list.select_files([str(path) for path in paths])
    saved_preview = window.artwork_label.text()
    before = disk_snapshot(window)
    window.metadata_clipboard.artwork = None if removal else png_bytes('blue')
    window.metadata_clipboard.artwork_mime = '' if removal else 'image/png'
    paste(window, {'artwork', 'title'}, set())
    assert_preview(window, None if removal else 'blue')
    assert window.title_edit.text() == 'Copied title'
    assert window.multi_edit_artwork
    assert window._has_unsaved_changes()
    assert disk_snapshot(window) == before
    window._undo_changes()
    assert window.artwork_label.pixmap().isNull()
    assert window.artwork_label.text() == saved_preview
    assert not window.multi_edit_artwork
    assert not window._has_unsaved_changes()
    assert disk_snapshot(window) == before


@pytest.mark.parametrize('finish', ['save', 'undo', 'cancel', 'discard', 'prompt_save'])
def test_remove_artwork_preview_lifecycle(window, monkeypatch, finish):
    target = window.current_file
    other = Path(window.file_list.item(1, 0).data(256))
    writer = write_mp3_metadata if target.suffix == '.mp3' else write_m4b_metadata
    original = png_bytes('red')
    writer(target, Metadata(), artwork=original, artwork_mime='image/png', fields=set())
    window._file_selected(str(target))
    assert_preview(window, 'red')
    before = disk_snapshot(window)
    window.remove_artwork_button.click()
    assert window.pending_artwork is None
    assert window.pending_artwork_mime == ''
    assert window.artwork_edited
    assert_preview(window, None)
    assert window._has_unsaved_changes()
    assert window.file_list.item(0, 0).text().startswith('*')
    assert disk_snapshot(window) == before
    if finish in ('save', 'prompt_save'):
        monkeypatch.setattr(module, 'write_mp3_metadata', write_mp3_metadata)
        monkeypatch.setattr(module, 'write_m4b_metadata', write_m4b_metadata)
        monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    if finish == 'save':
        window._save_changes()
    elif finish == 'undo':
        window._undo_changes()
    else:
        reply = {'cancel': QMessageBox.StandardButton.Cancel,
                 'discard': QMessageBox.StandardButton.Discard,
                 'prompt_save': QMessageBox.StandardButton.Save}[finish]
        prompts = []
        def respond(*args):
            prompts.append(args)
            return reply
        monkeypatch.setattr(QMessageBox, 'question', respond)
        window._file_selected(str(other))
        assert len(prompts) == 1
        if finish == 'cancel':
            assert window.current_file == target
            assert_preview(window, None)
            assert window.artwork_edited
            assert window._has_unsaved_changes()
            assert disk_snapshot(window) == before
            window._undo_changes()
        else:
            window._file_selected(str(target))
    saved = finish in ('save', 'prompt_save')
    assert read_metadata(target).artwork == (None if saved else original)
    assert_preview(window, None if saved else 'red')
    assert window.current_metadata == read_metadata(target)
    assert not window._has_unsaved_changes()
    assert not window.artwork_edited
    assert not window.file_list.item(0, 0).text().startswith('*')
    if not saved:
        assert disk_snapshot(window) == before


@pytest.mark.parametrize('save', [False, True])
def test_multi_remove_artwork_preview(window, monkeypatch, save):
    targets = list(disk_snapshot(window))
    window.file_list.select_files([str(path) for path in targets])
    summary = window.artwork_label.text()
    before = disk_snapshot(window)
    window.remove_artwork_button.click()
    assert_preview(window, None)
    assert window.multi_edit_artwork
    assert window._has_unsaved_changes()
    assert all(window.file_list.item(row, 0).text().startswith('*') for row in range(2))
    assert disk_snapshot(window) == before
    if save:
        monkeypatch.setattr(module, 'write_mp3_metadata', write_mp3_metadata)
        monkeypatch.setattr(module, 'write_m4b_metadata', write_m4b_metadata)
        monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
        window._save_changes()
        assert all(read_metadata(path).artwork is None for path in targets)
        assert window.artwork_label.text() == 'No artwork'
    else:
        window._undo_changes()
        assert window.artwork_label.text() == summary
        assert disk_snapshot(window) == before
    assert window.artwork_label.pixmap().isNull()
    assert not window._has_unsaved_changes()


def test_choose_artwork_immediate_preview(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    image = png_bytes('green')
    path = tmp_path / 'cover.png'
    path.write_bytes(image)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(path), ''))
    before = disk_snapshot(window)
    window.choose_artwork_button.click()
    assert_preview(window, 'green')
    assert window.pending_artwork == image
    assert window._has_unsaved_changes()
    assert disk_snapshot(window) == before


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('addition', [False, True])
def test_remove_absent_artwork_is_clean(window, monkeypatch, multiple, addition):
    targets = list(disk_snapshot(window))
    writer = write_mp3_metadata if targets[0].suffix == '.mp3' else write_m4b_metadata
    for path in targets:
        writer(path, Metadata(), artwork=None, fields=set())
    window._file_selected(str(targets[0]))
    if multiple:
        window.file_list.select_files([str(p) for p in targets])
    before = disk_snapshot(window)
    if addition:
        window.metadata_clipboard.artwork = png_bytes('blue')
        paste(window, {'artwork'}, set())
        assert window._has_unsaved_changes()
    for _ in range(2):
        window.remove_artwork_button.click()
        assert_preview(window, None)
        assert not window._has_unsaved_changes()
        assert not window.artwork_edited
        assert not window.multi_edit_artwork
        assert all(not window.file_list.item(row, 0).text().startswith('*') for row in range(2))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    window._save_changes()  # The fixture rejects any writer call.
    window._file_selected(str(targets[1]))  # The fixture rejects any prompt.
    assert disk_snapshot(window) == before


@pytest.mark.parametrize('text_edit', [False, True])
def test_mixed_removal_only_changes_artwork_files(window, qtbot, monkeypatch, text_edit):
    targets = list(disk_snapshot(window))
    writer = write_mp3_metadata if targets[0].suffix == '.mp3' else write_m4b_metadata
    writer(targets[1], Metadata(), artwork=None, fields=set())
    window.file_list.select_files([str(p) for p in targets])
    if text_edit:
        window.title_edit.selectAll()
        qtbot.keyClicks(window.title_edit, 'Pending title')
    before = disk_snapshot(window)
    window.remove_artwork_button.click()
    window.remove_artwork_button.click()
    assert_preview(window, None)
    assert window._has_unsaved_changes()
    assert window.file_list.item(0, 0).text().startswith('*')
    assert window.file_list.item(1, 0).text().startswith('*') == text_edit
    assert disk_snapshot(window) == before
    prompts = []
    def cancel(*args):
        prompts.append(args)
        return QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox, 'question', cancel)
    window._file_selected(str(targets[1]))
    assert prompts
    assert_preview(window, None)
    calls = []
    def save(path, metadata, **kwargs):
        calls.append((path, kwargs.copy()))
        writer(path, metadata, **kwargs)
    monkeypatch.setattr(module, 'write_mp3_metadata', save)
    monkeypatch.setattr(module, 'write_m4b_metadata', save)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    window._save_changes()
    assert [p for p, _ in calls] == (targets if text_edit else targets[:1])
    assert calls[0][1]['artwork'] is None
    if text_edit:
        assert 'artwork' not in calls[1][1]
        assert all(read_metadata(p).title == 'Pending title' for p in targets)
    else:
        assert targets[1].read_bytes() == before[targets[1]]
    assert all(read_metadata(p).artwork is None for p in targets)
    assert not window._has_unsaved_changes()
    assert all(not window.file_list.item(row, 0).text().startswith('*') for row in range(2))


@pytest.mark.parametrize('saved_artwork', [False, True])
def test_chosen_artwork_then_remove_preserves_text_edits(window, monkeypatch, tmp_path, saved_artwork):
    from PySide6.QtWidgets import QFileDialog
    target = window.current_file
    writer = write_mp3_metadata if target.suffix == '.mp3' else write_m4b_metadata
    original = png_bytes('red') if saved_artwork else None
    writer(target, Metadata(), artwork=original, artwork_mime='image/png', fields=set())
    window._file_selected(str(target))
    before = disk_snapshot(window)
    image_path = tmp_path / 'addition.png'
    image_path.write_bytes(png_bytes('blue'))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(image_path), ''))
    window.choose_artwork_button.click()
    assert_preview(window, 'blue')
    window.title_edit.setText('Unrelated pending title')
    window.remove_artwork_button.click()
    assert_preview(window, None)
    assert window.artwork_edited == saved_artwork
    assert window.title_edit.text() == 'Unrelated pending title'
    assert window._has_unsaved_changes()
    window.title_edit.setText(window.current_metadata.title)
    assert window._has_unsaved_changes() == saved_artwork
    assert disk_snapshot(window) == before
    window._undo_changes()
    assert_preview(window, 'red' if saved_artwork else None)
    assert not window._has_unsaved_changes()


@pytest.mark.parametrize('discard', [False, True])
def test_mixed_removal_undo_or_discard(window, monkeypatch, discard):
    targets = list(disk_snapshot(window))
    writer = write_mp3_metadata if targets[0].suffix == '.mp3' else write_m4b_metadata
    writer(targets[0], Metadata(), artwork=png_bytes('red'), artwork_mime='image/png', fields=set())
    writer(targets[1], Metadata(), artwork=None, fields=set())
    window._file_selected(str(targets[0]))
    window.file_list.select_files([str(p) for p in targets])
    before = disk_snapshot(window)
    window.remove_artwork_button.click()
    if discard:
        monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.StandardButton.Discard)
        window._file_selected(str(targets[1]))
        window._file_selected(str(targets[0]))
        assert_preview(window, 'red')
    else:
        window._undo_changes()
        assert window.artwork_label.text() == 'Mixed artwork'
    assert not window._has_unsaved_changes()
    assert all(not window.file_list.item(row, 0).text().startswith('*') for row in range(2))
    assert disk_snapshot(window) == before


@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('removal', [False, True])
def test_oversized_paste_preserves_pending_intent(window, qtbot, monkeypatch, multiple, removal):
    from audio_metadata_editor.artwork import MAX_ARTWORK_BYTES
    before_disk = disk_snapshot(window)
    if multiple:
        window.file_list.select_files([str(path) for path in before_disk])
    paste(window, {'artwork'}, set())
    if removal:
        window._remove_artwork()
    qtbot.keyClicks(window.title_edit, 'Pending title')
    before = (window.pending_artwork, window.pending_artwork_mime,
              window.artwork_edited, window.multi_edit_artwork,
              window.title_edit.text(), window._has_unsaved_changes(),
              window.artwork_label.pixmap().cacheKey())
    window.metadata_clipboard.artwork = bytes(MAX_ARTWORK_BYTES + 1)
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: messages.append(a))
    paste(window, {'artwork', 'title'}, {'artwork'})
    assert len(messages) == 1
    assert before == (window.pending_artwork, window.pending_artwork_mime,
                      window.artwork_edited, window.multi_edit_artwork,
                      window.title_edit.text(), window._has_unsaved_changes(),
                      window.artwork_label.pixmap().cacheKey())
    assert disk_snapshot(window) == before_disk
