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

    if total == 0:
        total = None

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

def _get_freeform(tags, name: str) -> str:
    atom = f"----:com.apple.iTunes:{name}"
    value = tags.get(atom)

    if not value:
        return ""

    value = value[0] if isinstance(value, list) else value

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return str(value)

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
        narrator=_get_freeform(tags, "Narrator"),
        series=_get_freeform(tags, "Series"),
        series_number=_get_freeform(tags, "Series Number"),
        publisher=_get_freeform(tags, "Publisher"),
        artwork=artwork,
        artwork_mime=artwork_mime,
    )

def write_m4b_metadata(path: Path, metadata: Metadata) -> None:
    audio = MP4(path)

    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags

    def set_text(atom: str, value: str) -> None:
        if value:
            tags[atom] = [value]
        else:
            tags.pop(atom, None)

    def set_freeform(name: str, value: str) -> None:
        atom = f"----:com.apple.iTunes:{name}"

        if value:
            tags[atom] = [value.encode("utf-8")]
        else:
            tags.pop(atom, None)

    set_text("\xa9nam", metadata.title)
    set_text("\xa9ART", metadata.artist)
    set_text("\xa9alb", metadata.album)
    set_text("aART", metadata.album_artist)
    set_text("\xa9gen", metadata.genre)
    set_text("\xa9day", metadata.date)
    set_text("\xa9wrt", metadata.composer)
    set_text("\xa9cmt", metadata.comment)
    set_text("desc", metadata.description)
    set_text("cprt", metadata.copyright)

    set_freeform("Narrator", metadata.narrator)
    set_freeform("Series", metadata.series)
    set_freeform("Series Number", metadata.series_number)
    set_freeform("Publisher", metadata.publisher)

    if metadata.track_number is not None:
        track_total = metadata.track_total or 0
        tags["trkn"] = [(metadata.track_number, track_total)]
    else:
        tags.pop("trkn", None)

    if metadata.disc_number is not None:
        disc_total = metadata.disc_total or 0
        tags["disk"] = [(metadata.disc_number, disc_total)]
    else:
        tags.pop("disk", None)

    audio.save()