from pathlib import Path

from mutagen.mp4 import MP4

from .model import Metadata


def read_m4b_metadata(path: Path) -> Metadata:
    try:
        audio = MP4(path)
    except Exception:
        return Metadata()

    tags = audio.tags

    if tags is None:
        return Metadata()

    def get_text(atom: str) -> str:
        value = tags.get(atom)

        if not value:
            return ""

        if isinstance(value, list):
            return str(value[0])

        return str(value)

    def get_number(atom: str) -> str:
        value = tags.get(atom)

        if not value:
            return ""

        value = value[0] if isinstance(value, list) else value

        if isinstance(value, tuple):
            return str(value[0])

        return str(value)

    return Metadata(
        title=get_text("\xa9nam"),
        artist=get_text("\xa9ART"),
        album=get_text("\xa9alb"),
        album_artist=get_text("aART"),
        genre=get_text("\xa9gen"),
        track=get_number("trkn"),
        disc=get_number("disk"),
        date=get_text("\xa9day"),
        composer=get_text("\xa9wrt"),
        comment=get_text("\xa9cmt"),
        description=get_text("desc"),
        copyright=get_text("cprt"),
    )