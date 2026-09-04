from dataclasses import dataclass
from pathlib import Path

from mutagen import File


@dataclass
class Metadata:
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    track: str = ""
    disc: str = ""


def read_metadata(path: Path) -> Metadata:
    audio = File(path, easy=True)

    if audio is None:
        return Metadata()

    def get_value(key: str) -> str:
        value = audio.get(key)

        if not value:
            return ""

        return str(value[0])

    return Metadata(
        title=get_value("title"),
        artist=get_value("artist"),
        album=get_value("album"),
        album_artist=get_value("albumartist"),
        genre=get_value("genre"),
        track=get_value("tracknumber"),
        disc=get_value("discnumber"),
    )