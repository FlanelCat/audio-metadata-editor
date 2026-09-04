from dataclasses import dataclass


@dataclass
class Metadata:
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    track: str = ""
    disc: str = ""
    date: str = ""
    composer: str = ""
    comment: str = ""
    description: str = ""
    publisher: str = ""
    copyright: str = ""
    narrator: str = ""
    series: str = ""
    series_number: str = ""