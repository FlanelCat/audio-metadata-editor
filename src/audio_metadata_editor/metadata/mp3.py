from pathlib import Path

from mutagen.id3 import (
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
    TXXX,
)

from .model import Metadata


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

    comment = ""
    id3v1_comment = ""

    for frame in tags.getall("COMM"):
        if not frame.text:
            continue

        text = str(frame.text[0])

        if frame.desc == "ID3v1 Comment":
            id3v1_comment = text
        elif not comment:
            comment = text

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

def write_mp3_metadata(path: Path, metadata: Metadata) -> None:
    tags = ID3(path)

    def set_text(frame_id: str, frame_class, value: str) -> None:
        tags.delall(frame_id)

        if value:
            tags.add(
                frame_class(
                    encoding=3,
                    text=[value],
                )
            )

    set_text("TIT2", TIT2, metadata.title)
    set_text("TPE1", TPE1, metadata.artist)
    set_text("TALB", TALB, metadata.album)
    set_text("TPE2", TPE2, metadata.album_artist)
    set_text("TCON", TCON, metadata.genre)
    set_text("TDRC", TDRC, metadata.date)
    set_text("TCOM", TCOM, metadata.composer)
    set_text("TCOP", TCOP, metadata.copyright)
    set_text("TPUB", TPUB, metadata.publisher)
    set_text("TIT3", TIT3, metadata.description)

    # Track number, preserving the existing total.
    tags.delall("TRCK")
    if metadata.track_number is not None:
        value = str(metadata.track_number)
        if metadata.track_total is not None:
            value += f"/{metadata.track_total}"

        tags.add(
            TRCK(
                encoding=3,
                text=[value],
            )
        )

    # Disc number, preserving the existing total.
    tags.delall("TPOS")
    if metadata.disc_number is not None:
        value = str(metadata.disc_number)
        if metadata.disc_total is not None:
            value += f"/{metadata.disc_total}"

        tags.add(
            TPOS(
                encoding=3,
                text=[value],
        )
)

    comments = tags.getall("COMM")

    # Preserve unrelated COMM frames.
    remaining_comments = [
        frame
        for frame in comments
        if frame.desc not in ("", "ID3v1 Comment")
    ]

    tags.setall("COMM", remaining_comments)

    if metadata.comment:
        tags.add(
            COMM(
                encoding=3,
                lang="eng",
                desc="",
                text=[metadata.comment],
            )
        )

    if metadata.id3v1_comment:
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

    set_txxx("Narrator", metadata.narrator)
    set_txxx("Series", metadata.series)
    set_txxx("Series Number", metadata.series_number)

    # Do not touch APIC/artwork or any other unknown frames.
    tags.save(path)

