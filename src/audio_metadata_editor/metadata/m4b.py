from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover
from mutagen.mp4 import AtomDataType

from .date import normalize_date
from .model import Metadata
from .errors import MetadataReadError
from .representation import scalar_values, validate_values


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

    if number == 0:
        number = None

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
    except Exception as exc:
        raise MetadataReadError(path, exc) from exc


_ARTWORK_UNCHANGED = object()

def write_m4b_metadata(
    path: Path,
    metadata: Metadata,
    artwork=_ARTWORK_UNCHANGED,
    artwork_mime: str = "",
    *,
    fields: set[str] | None = None,
) -> None:
    """Filter metadata fields; explicit artwork is independent of this filter.

    Omitting artwork preserves it, including during field-specific writes.
    """
    validate_values('.m4b', scalar_values(metadata, fields))
    date = normalize_date(metadata.date) if fields is None or "date" in fields else None
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

    if fields is None or "title" in fields:
        set_text("\xa9nam", metadata.title)
    if fields is None or "artist" in fields:
        set_text("\xa9ART", metadata.artist)
    if fields is None or "album" in fields:
        set_text("\xa9alb", metadata.album)
    if fields is None or "album_artist" in fields:
        set_text("aART", metadata.album_artist)
    if fields is None or "genre" in fields:
        set_text("\xa9gen", metadata.genre)
    if fields is None or "date" in fields:
        set_text("\xa9day", date)
    if fields is None or "composer" in fields:
        set_text("\xa9wrt", metadata.composer)
    if fields is None or "comment" in fields:
        set_text("\xa9cmt", metadata.comment)
    if fields is None or "description" in fields:
        set_text("desc", metadata.description)
    if fields is None or "copyright" in fields:
        set_text("cprt", metadata.copyright)

    if fields is None or "narrator" in fields:
        set_freeform("Narrator", metadata.narrator)
    if fields is None or "series" in fields:
        set_freeform("Series", metadata.series)
    if fields is None or "series_number" in fields:
        set_freeform("Series Number", metadata.series_number)
    if fields is None or "publisher" in fields:
        set_freeform("Publisher", metadata.publisher)

    for atom, prefix in (("trkn", "track"), ("disk", "disc")):
        number_field = f"{prefix}_number"
        total_field = f"{prefix}_total"
        if fields is not None and not fields.intersection({number_field, total_field}):
            continue

        number = getattr(metadata, number_field)
        total = getattr(metadata, total_field)
        if fields is not None:
            disk_number, disk_total = _get_pair(tags, atom)
            if number_field not in fields:
                number = disk_number
            if total_field not in fields:
                total = disk_total

        if number is not None or (fields is not None and total is not None):
            # MP4 uses zero for an absent component of a retained pair.
            tags[atom] = [(number or 0, total or 0)]
        else:
            tags.pop(atom, None)

    if artwork is not _ARTWORK_UNCHANGED:
        if artwork:
            if artwork_mime == "image/png":
                cover = MP4Cover(
                    artwork,
                    imageformat=14,
                )
            else:
                cover = MP4Cover(
                    artwork,
                    imageformat=13,
                )

            audio["covr"] = [cover]
        else:
            audio.pop("covr", None)

    audio.save()
