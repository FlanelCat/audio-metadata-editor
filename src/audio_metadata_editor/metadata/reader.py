from pathlib import Path

from .m4b import read_m4b_metadata
from .model import Metadata
from .errors import MetadataReadError
from .mp3 import read_mp3_metadata
from .path_policy import require_supported_audio_path, UnsupportedAudioPathError


def read_metadata(path: Path) -> Metadata:
    try:
        require_supported_audio_path(path)
    except UnsupportedAudioPathError as exc:
        raise MetadataReadError(path, exc) from exc
    suffix = path.suffix.lower()

    if suffix == ".mp3":
        return read_mp3_metadata(path)

    if suffix == ".m4b":
        return read_m4b_metadata(path)

    raise MetadataReadError(path, f"Unsupported audio format: {suffix}")
