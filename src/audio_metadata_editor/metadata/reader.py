from pathlib import Path

from .m4b import read_m4b_metadata
from .model import Metadata
from .errors import MetadataReadError
from .mp3 import read_mp3_metadata


def read_metadata(path: Path) -> Metadata:
    suffix = path.suffix.lower()

    if suffix == ".mp3":
        return read_mp3_metadata(path)

    if suffix == ".m4b":
        return read_m4b_metadata(path)

    raise MetadataReadError(path, f"Unsupported audio format: {suffix}")