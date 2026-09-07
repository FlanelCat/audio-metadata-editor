from pathlib import Path

from .m4b import write_m4b_metadata
from .model import Metadata
from .mp3 import write_mp3_metadata


def write_metadata(path: Path, metadata: Metadata) -> None:
    suffix = path.suffix.lower()

    if suffix == ".mp3":
        write_mp3_metadata(path, metadata)
        return

    if suffix == ".m4b":
        write_m4b_metadata(path, metadata)
        return

    raise ValueError(f"Unsupported audio format: {suffix}")