"""v0.1.0 audio-path policy; this is not race-proof filesystem isolation."""
from pathlib import Path


class UnsupportedAudioPathError(ValueError):
    pass


def require_supported_audio_path(path: Path) -> None:
    """Reject the path's final symlink component without resolving its target."""
    if path.is_symlink():
        raise UnsupportedAudioPathError(
            f"Audio-file symlinks are not supported; refusing to load or edit: {path}"
        )
