from .model import Metadata
from .reader import read_metadata
from .mp3 import write_mp3_metadata
from .m4b import write_m4b_metadata

__all__ = [
    "Metadata",
    "read_metadata",
    "write_mp3_metadata",
    "write_m4b_metadata",
]