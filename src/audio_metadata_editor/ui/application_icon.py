"""Load the original project icon from installed package data."""
from importlib.resources import files

from PySide6.QtGui import QIcon, QPixmap


def load_application_icon() -> QIcon:
    """Materialize the PNG before returning, without a temporary-path lifetime."""
    resource = files("audio_metadata_editor").joinpath("resources/application-icon.png")
    try:
        data = resource.read_bytes()
    except OSError as exc:
        raise RuntimeError("Could not read the packaged application icon.") from exc
    pixmap = QPixmap()
    if not pixmap.loadFromData(data, "PNG"):
        raise RuntimeError("The packaged application icon is not a valid PNG.")
    return QIcon(pixmap)
