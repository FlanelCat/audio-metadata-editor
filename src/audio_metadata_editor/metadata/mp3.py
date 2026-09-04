from pathlib import Path

from mutagen.id3 import APIC, ID3

from .model import Metadata


def _get_text(tags, frame_id: str) -> str:
    frame = tags.get(frame_id)

    if frame is None:
        return ""

    if hasattr(frame, "text") and frame.text:
        return str(frame.text[0])

    return ""


def _get_pair(tags, frame_id: str) -> tuple[int | None, int | None]:
    value = _get_text(tags, frame_id)

    if not value:
        return None, None

    parts = value.split("/", 1)

    try:
        number = int(parts[0])
    except ValueError:
        return None, None

    total = None

    if len(parts) == 2 and parts[1]:
        try:
            total = int(parts[1])
        except ValueError:
            pass

    return number, total

def _get_artwork(tags) -> tuple[bytes | None, str]:
    for frame in tags.values():
        if isinstance(frame, APIC):
            return frame.data, frame.mime

    return None, ""

def read_mp3_metadata(path: Path) -> Metadata:
    try:
        tags = ID3(path)
    except Exception:
        return Metadata()

    track_number, track_total = _get_pair(tags, "TRCK")
    disc_number, disc_total = _get_pair(tags, "TPOS")
    artwork, artwork_mime = _get_artwork(tags)

    return Metadata(
        title=_get_text(tags, "TIT2"),
        artist=_get_text(tags, "TPE1"),
        album=_get_text(tags, "TALB"),
        album_artist=_get_text(tags, "TPE2"),
        genre=_get_text(tags, "TCON"),

        track_number=track_number,
        track_total=track_total,

        disc_number=disc_number,
        disc_total=disc_total,

        date=_get_text(tags, "TDRC"),
        composer=_get_text(tags, "TCOM"),
        comment=_get_text(tags, "COMM"),
        description=_get_text(tags, "TIT3"),
        publisher=_get_text(tags, "TPUB"),
        copyright=_get_text(tags, "TCOP"),

        artwork=artwork,
        artwork_mime=artwork_mime,

    )