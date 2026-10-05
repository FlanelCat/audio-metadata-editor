"""Encoded artwork acceptance policy, independent of Qt and metadata formats."""
from pathlib import Path
import stat

MAX_ARTWORK_BYTES = 20 * 1024 * 1024


def require_artwork_size(size: int) -> None:
    if size > MAX_ARTWORK_BYTES:
        raise ValueError("Artwork exceeds the 20 MiB encoded size limit.")


def read_artwork_file(path: Path) -> bytes:
    """Reject unsupported objects before opening; bound reads even after growth.

    lstat deliberately does not follow the final symlink. This is a best-effort
    check, not protection against replacement between lstat and open.
    """
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Artwork must be a regular file, not a symlink or special file.")
    require_artwork_size(info.st_size)
    with open(path, "rb") as stream:
        data = stream.read(MAX_ARTWORK_BYTES + 1)
    require_artwork_size(len(data))
    return data
