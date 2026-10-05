"""Logical-field representability and explicit save readback checks.

No UI state lives here. Text is exact (including whitespace and Unicode), except
for the established Date grammar and ID3's single-genre code interpretation.
"""
from dataclasses import fields as model_fields
import re

from mutagen.id3 import TCON

from .date import normalize_date, verify_date
from .model import Metadata


NUMERIC_FIELDS = frozenset({'track_number', 'track_total', 'disc_number', 'disc_total'})
SCALAR_FIELDS = frozenset(f.name for f in model_fields(Metadata)) - {'artwork', 'artwork_mime'}


class RepresentationError(ValueError):
    def __init__(self, field, reason):
        self.field = field
        label = 'ID3v1 Comment' if field == 'id3v1_comment' else field.replace('_', ' ').title()
        super().__init__(f'{label}: {reason}')


class VerificationError(ValueError):
    pass


def _genre(value):
    return TCON(encoding=3, text=[value]).genres


def _genre_alias(value):
    return re.fullmatch(r'(?:[0-9]+|RX|CR|\((?:[0-9]+|RX|CR)\))', value)


def validate_values(suffix, values):
    """Validate only requested scalar values, without reading or writing files."""
    for field, value in values.items():
        if field not in SCALAR_FIELDS:
            continue
        if field in NUMERIC_FIELDS:
            if value is not None and type(value) is not int:
                raise RepresentationError(field, 'must be an integer or empty.')
            if suffix == '.m4b' and value is not None and not 0 <= value <= 65535:
                raise RepresentationError(field, 'M4B requires 0–65535 or empty; zero represents absence.')
            continue
        try:
            value.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise RepresentationError(field, 'contains an unpaired Unicode surrogate that cannot be encoded.') from exc
        if suffix == '.mp3' and '\0' in value:
            raise RepresentationError(field, 'embedded NUL separates ID3 values and cannot be retained in a scalar field.')
        if suffix == '.m4b' and field == 'id3v1_comment' and value:
            raise RepresentationError(field, 'is not supported by M4B.')
        if suffix == '.mp3' and field == 'genre' and value:
            genres = _genre(value)
            # v2.3 conversion and subsequent reading both interpret genre codes.
            # Reject multi-value/unstable encodings instead of losing components.
            if (len(genres) != 1 or _genre(genres[0]) != genres
                    or (genres != [value] and not _genre_alias(value))):
                raise RepresentationError(field, 'this ID3 genre notation cannot be retained as one scalar genre; use a single genre name.')
        if field == 'date':
            normalize_date(value)


def scalar_values(metadata, fields=None):
    return {field: getattr(metadata, field) for field in
            (SCALAR_FIELDS if fields is None else fields) if field in SCALAR_FIELDS}


def verify_values(path, requested, actual):
    """Verify intended logical fields only; artwork compares payload and MIME.

    M4B zero means absence (None); MP3 integers are exact. series_number is exact text. Date
    permits whitespace/precision normalization. ID3 genre aliases are semantic.
    Artwork removal ignores MIME; replacement uses the writer's MIME default.
    """
    for field, value in requested.items():
        if field == 'date':
            verify_date(value, actual.date)
            continue
        if field == 'artwork_mime':
            continue
        observed = getattr(actual, field)
        if field == 'artwork':
            matches = (value or None) == observed
            if value:
                mime = requested.get('artwork_mime') or 'image/jpeg'
                matches = matches and actual.artwork_mime == mime
        elif field == 'genre' and path.suffix.lower() == '.mp3' and _genre_alias(value):
            matches = _genre(value) == [observed]
        elif field in NUMERIC_FIELDS and path.suffix.lower() == '.m4b' and value == 0:
            matches = observed is None
        else:
            matches = value == observed
            if field in NUMERIC_FIELDS:
                matches = matches and type(value) is type(observed)
        if not matches:
            label = field.replace('_', ' ').title()
            raise VerificationError(
                f'The write may have occurred, but readback did not match the requested {label} '
                f'for {path.name}. Verification failed; pending intent is retained. No rollback was attempted.'
            )
