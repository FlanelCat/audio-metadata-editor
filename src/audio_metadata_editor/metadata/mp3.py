from pathlib import Path

from mutagen.id3 import ID3

from .model import Metadata


def read_mp3_metadata(path: Path) -> Metadata:
    try:
        tags = ID3(path)
    except Exception:
        return Metadata()

    def get_text(frame_id: str) -> str:
        frame = tags.get(frame_id)

        if frame is None:
            return ""

        if hasattr(frame, "text") and frame.text:
            return str(frame.text[0])

        return ""

    return Metadata(
        title=get_text("TIT2"),
        artist=get_text("TPE1"),
        album=get_text("TALB"),
        album_artist=get_text("TPE2"),
        genre=get_text("TCON"),
        track=get_text("TRCK"),
        disc=get_text("TPOS"),
        date=get_text("TDRC"),
        composer=get_text("TCOM"),
        comment=get_text("COMM"),
        description=get_text("TIT3"),
        publisher=get_text("TPUB"),
        copyright=get_text("TCOP"),
    )