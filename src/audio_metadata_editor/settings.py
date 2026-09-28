"""Only the accepted navigator root is persisted as application settings."""
from PySide6.QtCore import QSettings

ROOT_KEY = "navigator/rootPath"


def create_settings():
    return QSettings("AudioMetadataEditor", "AudioMetadataEditor")
