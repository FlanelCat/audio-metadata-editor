from dataclasses import dataclass


@dataclass
class Metadata:
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""

    track_number: int | None = None
    track_total: int | None = None

    disc_number: int | None = None
    disc_total: int | None = None

    date: str = ""
    composer: str = ""
    comment: str = ""
    description: str = ""
    publisher: str = ""
    copyright: str = ""

    narrator: str = ""
    series: str = ""
    series_number: str = ""

    artwork: bytes | None = None
    artwork_mime: str = ""