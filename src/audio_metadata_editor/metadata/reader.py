from pathlib import Path

from mutagen import File


def read_metadata(path: Path) -> dict[str, str]:
    audio = File(path, easy=True)

    if audio is None:
        return {}

    def get_value(key: str) -> str:
        value = audio.get(key)

        if not value:
            return ""

        return str(value[0])

    return {
        "title": get_value("title"),
        "artist": get_value("artist"),
        "album": get_value("album"),
        "album_artist": get_value("albumartist"),
        "genre": get_value("genre"),
        "track": get_value("tracknumber"),
        "disc": get_value("discnumber"),
    }
