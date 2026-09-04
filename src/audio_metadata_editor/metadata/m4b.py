from pathlib import Path

from mutagen.mp4 import MP4

from .model import Metadata


def _get_text(tags, atom: str) -> str:
    value = tags.get(atom)

    if not value:
        return ""

    if isinstance(value, list):
        return str(value[0])

    return str(value)


def _get_pair(
    tags,
    atom: str,
) -> tuple[int | None, int | None]:
    value = tags.get(atom)

    if not value:
        return None, None

    value = value[0] if isinstance(value, list) else value

    if not isinstance(value, tuple):
        return None, None

    number = value[0] if len(value) > 0 else None
    total = value[1] if len(value) > 1 else None

    return number, total

def _get_artwork(tags) -> tuple[bytes | None, str]:
    covers = tags.get("covr")

    if not covers:
        return None, ""

    cover = covers[0]

    mime = "image/jpeg"

    if cover.imageformat == 14:
        mime = "image/png"

    return bytes(cover), mime

def read_m4b_metadata(path: Path) -> Metadata:
    try:
        audio = MP4(path)
    except Exception:
        return Metadata()

    tags = audio.tags

    if tags is None:
        return Metadata()

    track_number, track_total = _get_pair(tags, "trkn")
    disc_number, disc_total = _get_pair(tags, "disk")
    artwork, artwork_mime = _get_artwork(tags)

    return Metadata(
        title=_get_text(tags, "\xa9nam"),
        artist=_get_text(tags, "\xa9ART"),
        album=_get_text(tags, "\xa9alb"),
        album_artist=_get_text(tags, "aART"),
        genre=_get_text(tags, "\xa9gen"),

        track_number=track_number,
        track_total=track_total,

        disc_number=disc_number,
        disc_total=disc_total,

        date=_get_text(tags, "\xa9day"),
        composer=_get_text(tags, "\xa9wrt"),
        comment=_get_text(tags, "\xa9cmt"),
        description=_get_text(tags, "desc"),
        copyright=_get_text(tags, "cprt"),

        artwork=artwork,
        artwork_mime=artwork_mime,
    )