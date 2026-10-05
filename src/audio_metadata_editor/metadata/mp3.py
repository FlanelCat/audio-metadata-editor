from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import (
    ID3NoHeaderError,
    APIC,
    COMM,
    ID3,
    TALB,
    TCOM,
    TCOP,
    TCON,
    TDRC,
    TIT2,
    TIT3,
    TPE1,
    TPE2,
    TPUB,
    TRCK,
    TPOS,
    TIME,
    TXXX,
)

from .date import normalize_date
from .model import Metadata
from .errors import MetadataReadError
from .representation import scalar_values, validate_values

_ARTWORK_UNCHANGED = object()

def _get_text(tags, frame_id: str) -> str:
    frame = tags.get(frame_id)
    if frame is None:
        return ""

    if hasattr(frame, "text") and frame.text:
        return str(frame.text[0])

    return ""


def _get_txxx(tags, description: str) -> str:
    for frame in tags.getall("TXXX"):
        if frame.desc.lower() == description.lower() and frame.text:
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
        number = None

    total = None

    if len(parts) == 2 and parts[1]:
        try:
            total = int(parts[1])
        except ValueError:
            pass

    return number, total


def _comment_field(frame):
    """Only English undescribed COMM is ordinary Comment; never fall back.

    Keep the existing description-wide ID3v1 Comment convention (not a raw
    ID3v1 trailer editor). Other languages/descriptions are unrelated metadata.
    """
    if frame.desc == "ID3v1 Comment":
        return "id3v1_comment"
    if frame.desc == "" and frame.lang == "eng":
        return "comment"
    return None


def _get_artwork(tags) -> tuple[bytes | None, str]:
    for frame in tags.values():
        if isinstance(frame, APIC):
            return frame.data, frame.mime

    return None, ""


def read_mp3_metadata(path: Path) -> Metadata:
    try:
        try:
            tags = ID3(path, load_v1=False)
        except ID3NoHeaderError:
            # No ID3 header is valid only if the underlying MPEG audio is readable.
            MP3(path)
            return Metadata()

        track_number, track_total = _get_pair(tags, "TRCK")
        disc_number, disc_total = _get_pair(tags, "TPOS")
        artwork, artwork_mime = _get_artwork(tags)

        comment = ""
        id3v1_comment = ""

        # The legacy description-wide category prefers English, then language
        # code order, independent of physical frame ordering.
        for frame in sorted(tags.getall("COMM"), key=lambda f: (f.lang != "eng", f.lang)):
            if not frame.text:
                continue
            field = _comment_field(frame)
            if field == "id3v1_comment" and not id3v1_comment:
                id3v1_comment = str(frame.text[0])
            elif field == "comment":
                comment = str(frame.text[0])

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
            comment=comment,
            id3v1_comment=id3v1_comment,
            description=_get_text(tags, "TIT3"),
            publisher=_get_text(tags, "TPUB"),
            copyright=_get_text(tags, "TCOP"),
            narrator=_get_txxx(tags, "Narrator"),
            series=_get_txxx(tags, "Series"),
            series_number=_get_txxx(tags, "Series Number"),
            artwork=artwork,
            artwork_mime=artwork_mime,
        )
    except Exception as exc:
        raise MetadataReadError(path, exc) from exc


def load_mp3_tags_for_write(path: Path):
    """Return existing tags, or new in-memory v2.4 tags after MPEG validation."""
    try:
        return ID3(path, translate=False, load_v1=False), False
    except ID3NoHeaderError:
        # A missing header alone is not proof of audio. Match the reader's
        # validation policy before allowing an explicit write to create tags.
        MP3(path)
        return ID3(), True


def write_mp3_metadata(
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
    validate_values('.mp3', scalar_values(metadata, fields))
    # Default translation drops v2.3-only frames before we can preserve them.
    # Keep the loaded version for both filtered and full writes; never migrate
    # unrelated metadata merely to edit a supported logical field.
    tags, new_tag = load_mp3_tags_for_write(path)
    version = 3 if tags.version[:2] == (2, 3) else 4
    if version == 4:
        tags.update_to_v24()

    date = normalize_date(metadata.date, id3_version=version) if fields is None or "date" in fields else None

    def set_text(frame_id: str, frame_class, value: str) -> None:
        tags.delall(frame_id)

        if value:
            tags.add(
                frame_class(
                    encoding=3,
                    text=[value],
                )
            )

    if fields is None or "title" in fields:
        set_text("TIT2", TIT2, metadata.title)
    if fields is None or "artist" in fields:
        set_text("TPE1", TPE1, metadata.artist)
    if fields is None or "album" in fields:
        set_text("TALB", TALB, metadata.album)
    if fields is None or "album_artist" in fields:
        set_text("TPE2", TPE2, metadata.album_artist)
    if fields is None or "genre" in fields:
        set_text("TCON", TCON, metadata.genre)
    if fields is None or "date" in fields:
        if version == 3:
            # Replace the old date components before converting the new TDRC;
            # Mutagen otherwise gives existing TYER/TDAT/TIME precedence.
            for frame_id in ("TYER", "TDAT", "TIME"):
                tags.delall(frame_id)
        set_text("TDRC", TDRC, date)
    if fields is None or "composer" in fields:
        set_text("TCOM", TCOM, metadata.composer)
    if fields is None or "copyright" in fields:
        set_text("TCOP", TCOP, metadata.copyright)
    if fields is None or "publisher" in fields:
        set_text("TPUB", TPUB, metadata.publisher)
    if fields is None or "description" in fields:
        set_text("TIT3", TIT3, metadata.description)

    for frame_id, frame_class, prefix in (
        ("TRCK", TRCK, "track"),
        ("TPOS", TPOS, "disc"),
    ):
        number_field = f"{prefix}_number"
        total_field = f"{prefix}_total"
        if fields is not None and not fields.intersection({number_field, total_field}):
            continue

        number = getattr(metadata, number_field)
        total = getattr(metadata, total_field)
        if fields is None:
            # Keep the full-write behavior: a missing number removes the pair.
            value = "" if number is None else str(number)
            if number is not None and total is not None:
                value += f"/{total}"
        else:
            # Preserve the unrequested component directly from the stored text.
            parts = _get_text(tags, frame_id).split("/", 1)
            number_text = parts[0]
            total_text = parts[1] if len(parts) == 2 else ""
            if number_field in fields:
                number_text = "" if number is None else str(number)
            if total_field in fields:
                total_text = "" if total is None else str(total)
            value = number_text + (f"/{total_text}" if total_text else "")

        set_text(frame_id, frame_class, value)

    if fields is None or "comment" in fields or "id3v1_comment" in fields:
        comments = tags.getall("COMM")

        requested_descriptions = {
            description
            for field, description in (("comment", ""), ("id3v1_comment", "ID3v1 Comment"))
            if fields is None or field in fields
        }
        requested_fields = {field for field in ("comment", "id3v1_comment")
                            if fields is None or field in fields}
        # Use exactly the reader's identities; never consume unrelated comments.
        remaining_comments = [
            frame
            for frame in comments
            if _comment_field(frame) not in requested_fields
        ]

        tags.setall("COMM", remaining_comments)

        if "" in requested_descriptions and metadata.comment:
            tags.add(
                COMM(
                    encoding=3,
                    lang="eng",
                    desc="",
                    text=[metadata.comment],
                )
            )

        if "ID3v1 Comment" in requested_descriptions and metadata.id3v1_comment:
            tags.add(
                COMM(
                    encoding=3,
                    lang="eng",
                    desc="ID3v1 Comment",
                    text=[metadata.id3v1_comment],
                )
            )

    def set_txxx(description: str, value: str) -> None:
        matching = [
            frame
            for frame in tags.getall("TXXX")
            if frame.desc.lower() == description.lower()
        ]

        for frame in matching:
            tags.delall(f"TXXX:{frame.desc}")

        if value:
            tags.add(
                TXXX(
                    encoding=3,
                    desc=description,
                    text=[value],
                )
            )

    if fields is None or "narrator" in fields:
        set_txxx("Narrator", metadata.narrator)
    if fields is None or "series" in fields:
        set_txxx("Series", metadata.series)
    if fields is None or "series_number" in fields:
        set_txxx("Series Number", metadata.series_number)

    if artwork is not _ARTWORK_UNCHANGED:
        tags.delall("APIC")

        if artwork:
            mime = artwork_mime or "image/jpeg"

            tags.add(
                APIC(
                    encoding=3,
                    mime=mime,
                    type=3,
                    desc="Cover",
                    data=artwork,
                )
            )

    if version == 3:
        tags.update_to_v23()
        # Mutagen's conversion omits TIME when either component is zero.
        if date and len(date) == 16:
            tags.setall("TIME", [TIME(encoding=3, text=[date[11:13] + date[14:16]])])
    if new_tag and not tags:
        return
    # Retain any existing multi-valued text rather than joining it with '/'.
    _save_preserving_raw_id3v1(path, tags, version)


def _read_raw_id3v1(stream):
    """Read only a physical 128-byte TAG trailer, without interpreting fields."""
    size = stream.seek(0, 2)
    if size < 128:
        return None
    stream.seek(-128, 2)
    trailer = stream.read(128)
    if len(trailer) != 128:
        raise OSError('Could not read the complete raw ID3v1 trailer')
    return trailer if trailer.startswith(b'TAG') else None


def _restore_raw_id3v1(stream, trailer):
    """Restore after deletion, or leave an already intact trailer alone."""
    if _read_raw_id3v1(stream) != trailer:
        stream.seek(0, 2)
        if stream.write(trailer) != len(trailer):
            raise OSError('Incomplete raw ID3v1 trailer restoration')
    stream.flush()
    if _read_raw_id3v1(stream) != trailer:
        raise OSError('Raw ID3v1 trailer verification failed')


def _save_preserving_raw_id3v1(path, tags, version):
    # Use the same open file for save/restoration. v1=0 prevents regeneration but
    # deletes an existing trailer, so it is never sufficient on its own.
    with open(path, 'r+b') as stream:
        trailer = _read_raw_id3v1(stream)
        try:
            stream.seek(0)
            tags.save(stream, v1=0, v2_version=version, v23_sep=None)
        finally:
            # A save may fail before or after removing the trailer. Do not
            # duplicate an intact one, and never suppress a save/restore error.
            # This is best-effort preservation, not rollback of the ID3v2 write.
            if trailer is not None:
                _restore_raw_id3v1(stream, trailer)
