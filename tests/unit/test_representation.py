from pathlib import Path

import pytest

from audio_metadata_editor.metadata import Metadata
from audio_metadata_editor.metadata.representation import SCALAR_FIELDS, NUMERIC_FIELDS, VerificationError, verify_values


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
@pytest.mark.parametrize('field', sorted(SCALAR_FIELDS - {'date'}))
def test_requested_fields_only_and_mismatch(suffix, field):
    value = 3 if field in NUMERIC_FIELDS else ' 03 日本語 '
    actual = Metadata(artist='unrelated')
    setattr(actual, field, value)
    verify_values(Path('audio.' + suffix), {field: value}, actual)
    setattr(actual, field, None if field in NUMERIC_FIELDS else 'different')
    with pytest.raises(VerificationError, match='did not match'):
        verify_values(Path('audio.' + suffix), {field: value}, actual)


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
def test_date_and_artwork_semantics(suffix):
    path = Path('audio.' + suffix)
    verify_values(path, {'date': ' 2024-02-29T00:00:00 '}, Metadata(date='2024-02-29 00:00'))
    verify_values(path, {'artwork': None, 'artwork_mime': 'stale'}, Metadata())
    verify_values(path, {'artwork': b'cover', 'artwork_mime': ''}, Metadata(artwork=b'cover', artwork_mime='image/jpeg'))
    for actual in (Metadata(), Metadata(artwork=b'other', artwork_mime='image/png'),
                   Metadata(artwork=b'cover', artwork_mime='image/jpeg')):
        with pytest.raises(VerificationError):
            verify_values(path, {'artwork': b'cover', 'artwork_mime': 'image/png'}, actual)


def test_only_documented_numeric_and_genre_normalizations():
    verify_values(Path('audio.m4b'), {'track_number': 0}, Metadata())
    with pytest.raises(VerificationError):
        verify_values(Path('audio.mp3'), {'track_number': 0}, Metadata())
    for requested in ('name\ntruncated', '(17)(18)'):
        with pytest.raises(VerificationError):
            verify_values(Path('audio.mp3'), {'genre': requested}, Metadata(genre='name' if '\n' in requested else 'Rock'))
    verify_values(Path('audio.mp3'), {'series_number': '01'}, Metadata(series_number='01'))
    with pytest.raises(VerificationError):
        verify_values(Path('audio.mp3'), {'series_number': '01'}, Metadata(series_number='1'))
