"""Decode preview artwork without probing arbitrary Qt image plugins."""
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QImageReader


def decode_artwork(data: bytes) -> tuple[QImage, str] | None:
    """Validate JPEG/PNG content and return its image and MIME, or reject it.

    Signatures select an allowed decoder, not proof of a valid image. Only a
    successful restricted decode accepts the data. Never use unrestricted
    format detection here, including for embedded covers with misleading MIME.
    """
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        image_format, mime = b'png', 'image/png'
    elif data.startswith(b'\xff\xd8\xff'):
        image_format, mime = b'jpeg', 'image/jpeg'
    else:
        return None

    buffer = QBuffer()
    buffer.setData(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer, image_format)
    # Prevent fallback to another plugin when the selected decoder rejects data.
    reader.setAutoDetectImageFormat(False)
    reader.setDecideFormatFromContent(False)
    image = reader.read()
    if image.isNull():
        return None
    return image, mime
