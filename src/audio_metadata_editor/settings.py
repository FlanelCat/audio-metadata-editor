"""Lightweight application preferences stored through one QSettings identity."""
from PySide6.QtCore import QSettings

ROOT_KEY = "navigator/rootPath"
GENERATE_TEXT_FIELD_KEY = "generateText/lastField"
GENERATE_TEXT_TEMPLATE_KEY = "generateText/lastTemplate"


def create_settings():
    return QSettings("AudioMetadataEditor", "AudioMetadataEditor")
