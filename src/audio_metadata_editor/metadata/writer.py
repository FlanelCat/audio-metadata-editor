from pathlib import Path

from .m4b import write_m4b_metadata
from .model import Metadata
from .mp3 import write_mp3_metadata


def write_metadata(path: Path, metadata: Metadata, *, fields: set[str] | None = None) -> None:
    suffix = path.suffix.lower()

    if suffix == ".mp3":
        write_mp3_metadata(path, metadata, fields=fields)
        return

    if suffix == ".m4b":
        write_m4b_metadata(path, metadata, fields=fields)
        return

    raise ValueError(f"Unsupported audio format: {suffix}")

def validate_date_for_file(path: Path, value: str) -> None:
    """Preflight an entire batch before any file is written."""
    from mutagen.id3 import ID3
    from .date import normalize_date
    normalize_date(value)
    if path.suffix.lower() == '.mp3':
        tags = ID3(path, translate=False)
        normalize_date(value, id3_version=tags.version[1] if tags.version[0] == 2 else 4)
