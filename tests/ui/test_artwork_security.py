"""Content-restricted artwork decoding and preservation on real media copies."""
from pathlib import Path
import shutil
import tomllib

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog, QMessageBox

from audio_metadata_editor.metadata import (
    Metadata, read_metadata, write_mp3_metadata, write_m4b_metadata,
)
from audio_metadata_editor.ui.main_window import MainWindow
from audio_metadata_editor.ui import artwork

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"/>'


@pytest.mark.parametrize('data', [SVG, b'GIF89a', b'BM', b'RIFF', b'', b'not an image'])
def test_unsupported_content_never_reaches_a_decoder(monkeypatch, data):
    def forbidden(*args):
        pytest.fail('Unsupported content reached Qt image decoding')
    monkeypatch.setattr(artwork, 'QImageReader', forbidden)
    monkeypatch.setattr(QImage, 'fromData', forbidden)
    assert artwork.decode_artwork(data) is None


@pytest.mark.parametrize('prefix,expected_format', [
    (b'\x89PNG\r\n\x1a\n', b'png'), (b'\xff\xd8\xff', b'jpeg'),
])
def test_forged_raster_signature_cannot_enable_decoder_fallback(monkeypatch, prefix, expected_format):
    original = artwork.QImageReader
    reads = []

    class RestrictedReader(original):
        def read(self):
            assert bytes(self.format()) == expected_format
            assert not self.autoDetectImageFormat()
            assert not self.decideFormatFromContent()
            reads.append(expected_format)
            return super().read()

    monkeypatch.setattr(artwork, 'QImageReader', RestrictedReader)
    assert artwork.decode_artwork(prefix + SVG) is None
    assert reads == [expected_format]


def test_patched_dependency_baseline():
    config = tomllib.loads((Path(__file__).parents[2] / 'pyproject.toml').read_text())
    assert 'PySide6>=6.11.1' in config['project']['dependencies']


@pytest.fixture(params=['mp3', 'm4b'])
def embedded(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    path = tmp_path / ('audio.' + request.param)
    shutil.copy2(audio_fixture_dir / ('silence.' + request.param), path)
    writer = write_mp3_metadata if request.param == 'mp3' else write_m4b_metadata
    # A misleading stored MIME must never authorize decoding SVG.
    writer(path, Metadata(title='Original'), artwork=SVG, artwork_mime='image/jpeg')
    def forbidden(*args):
        pytest.fail('Artwork must not use unrestricted QImage.fromData')
    monkeypatch.setattr(QImage, 'fromData', forbidden)
    window = MainWindow()
    qtbot.addWidget(window, before_close_func=lambda w: w._clear_editing_context())
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    window._directory_selected(tmp_path)
    window.file_list.select_files([str(path)])
    return window, path


def test_embedded_svg_preserved_without_preview(embedded, qtbot):
    window, path = embedded
    assert window.artwork_label.pixmap().isNull()
    assert window.pending_artwork == SVG
    assert not window._has_unsaved_changes()
    qtbot.keyClicks(window.artist_edit, 'Artist')
    window._save_changes()
    assert read_metadata(path).artwork == SVG
    assert not window._has_unsaved_changes()
    window._remove_artwork()
    assert window._has_unsaved_changes()
    window._undo_changes()
    assert window.pending_artwork == SVG
    assert window.artwork_label.pixmap().isNull()
    assert not window._has_unsaved_changes()
    window._remove_artwork()
    window._save_changes()
    assert read_metadata(path).artwork is None


@pytest.mark.parametrize('image_format,extension,mime', [
    ('PNG', '.jpg', 'image/png'), ('JPEG', '.png', 'image/jpeg'),
])
def test_raster_selection_uses_content_and_explicit_save(
    embedded, tmp_path, monkeypatch, image_format, extension, mime,
):
    window, path = embedded
    cover = tmp_path / ('cover' + extension)
    image = QImage(3, 2, QImage.Format_RGB32)
    image.fill(Qt.red)
    assert image.save(str(cover), image_format)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(cover), ''))
    window._choose_artwork()
    assert window.pending_artwork == cover.read_bytes()
    assert window.pending_artwork_mime == mime
    assert not window.artwork_label.pixmap().isNull()
    assert read_metadata(path).artwork == SVG
    window._save_changes()
    assert read_metadata(path).artwork == cover.read_bytes()
    assert read_metadata(path).artwork_mime == mime
    assert not window._has_unsaved_changes()
