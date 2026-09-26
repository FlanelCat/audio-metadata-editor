from pathlib import Path


class MetadataReadError(Exception):
    """Metadata could not be read; never a substitute for empty metadata."""

    def __init__(self, path, reason):
        self.path = Path(path)
        super().__init__(f"Could not read metadata from {self.path}: {reason}")
