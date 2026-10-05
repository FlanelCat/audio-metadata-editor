"""Narrow S6 encoded-byte and filesystem-object boundaries."""
from io import BytesIO
from unittest.mock import Mock
import shutil

import pytest
from PySide6.QtWidgets import QMessageBox

from audio_metadata_editor import artwork as policy
from audio_metadata_editor.ui import artwork
from audio_metadata_editor.ui.main_window import MainWindow
from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata, write_m4b_metadata


def test_limit():
    assert policy.MAX_ARTWORK_BYTES == 20 * 1024 * 1024


@pytest.mark.parametrize('extra', [0, 1])
def test_decode_boundary_before_qt_copy(monkeypatch, extra):
    data = b'\x89PNG\r\n\x1a\n' + bytes(policy.MAX_ARTWORK_BYTES - 8 + extra)
    buffer = Mock(side_effect=RuntimeError('reached format validation'))
    monkeypatch.setattr(artwork, 'QBuffer', buffer)
    if extra:
        assert artwork.decode_artwork(data) is None
        buffer.assert_not_called()
    else:
        with pytest.raises(RuntimeError, match='format validation'):
            artwork.decode_artwork(data)


def test_oversized_file_never_opened(tmp_path, monkeypatch):
    path = tmp_path / 'large.png'
    with path.open('wb') as stream:
        stream.truncate(policy.MAX_ARTWORK_BYTES + 1)
    opener = Mock(side_effect=AssertionError('must not open'))
    monkeypatch.setattr(policy, 'open', opener, raising=False)
    with pytest.raises(ValueError, match='20 MiB'):
        policy.read_artwork_file(path)
    opener.assert_not_called()


@pytest.mark.parametrize('extra', [0, 1])
def test_bounded_read_after_growth(tmp_path, monkeypatch, extra):
    path = tmp_path / 'growing.png'
    path.write_bytes(b'small at stat time')
    class GrowingStream(BytesIO):
        def read(self, size=-1):
            assert size == policy.MAX_ARTWORK_BYTES + 1
            return super().read(size)
    stream = GrowingStream(bytes(policy.MAX_ARTWORK_BYTES + extra))
    monkeypatch.setattr(policy, 'open', lambda *a: stream, raising=False)
    if extra:
        with pytest.raises(ValueError, match='20 MiB'):
            policy.read_artwork_file(path)
    else:
        assert len(policy.read_artwork_file(path)) == policy.MAX_ARTWORK_BYTES


@pytest.mark.parametrize('extension', ['mp3', 'm4b'])
def test_large_embedded_preserved_on_scalar_save(extension, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    path = tmp_path / ('audio.' + extension)
    shutil.copy2(audio_fixture_dir / ('silence.' + extension), path)
    payload = b'\x89PNG\r\n\x1a\n' + bytes(policy.MAX_ARTWORK_BYTES)
    writer = write_mp3_metadata if extension == 'mp3' else write_m4b_metadata
    writer(path, Metadata(title='Original'), artwork=payload, artwork_mime='image/png')
    monkeypatch.setattr(artwork, 'QBuffer', Mock(side_effect=AssertionError('no Qt copy')))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    window = MainWindow()
    qtbot.addWidget(window, before_close_func=lambda w: w._clear_editing_context())
    window._directory_selected(tmp_path)
    window.file_list.select_files([str(path)])
    assert window.pending_artwork == payload
    assert window.artwork_label.pixmap().isNull()
    assert not window._has_unsaved_changes()
    qtbot.keyClicks(window.artist_edit, 'Artist')
    window._save_changes()
    saved = read_metadata(path)
    assert saved.artwork == payload
    assert saved.artist == 'Artist'
    assert not window._has_unsaved_changes()


def test_m4b_reader_retains_cover_without_copy():
    from mutagen.mp4 import MP4Cover
    from audio_metadata_editor.metadata.m4b import _get_artwork
    cover = MP4Cover(b'cover')
    assert _get_artwork({'covr': [cover]})[0] is cover


@pytest.mark.parametrize('image_format,mime', [('PNG', 'image/png'), ('JPEG', 'image/jpeg')])
def test_exact_limit_file_reaches_normal_decode(tmp_path, image_format, mime):
    from PySide6.QtGui import QImage
    path = tmp_path / 'cover'
    image = QImage(2, 2, QImage.Format_RGB32)
    image.fill(0)
    assert image.save(str(path), image_format)
    with path.open('ab') as stream:
        stream.truncate(policy.MAX_ARTWORK_BYTES)
    payload = policy.read_artwork_file(path)
    assert len(payload) == policy.MAX_ARTWORK_BYTES
    decoded = artwork.decode_artwork(payload)
    assert decoded is not None
    assert decoded[1] == mime
