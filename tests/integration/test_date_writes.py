import shutil
import pytest
from mutagen.id3 import ID3
from audio_metadata_editor.metadata import Metadata, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.metadata.date import normalize_date, DateValidationError

@pytest.fixture(params=['v23', 'v24', 'm4b'])
def audio(request, tmp_path, audio_fixture_dir):
    suffix = 'm4b' if request.param == 'm4b' else 'mp3'
    p = tmp_path / f'a.{suffix}'
    shutil.copy2(audio_fixture_dir / f'silence.{suffix}', p)
    write_metadata(p, Metadata(date='2020', title='Keep', artist='Artist', track_number=3, track_total=9))
    if request.param == 'v23':
        tags = ID3(p); tags.update_to_v23(); tags.save(p, v2_version=3)
    return p, request.param

@pytest.mark.parametrize('value', ['2024', '2024-02-29', '', ' 2024 ', '2024-02-29T00:00', '2024-02-29T12:00', '2024-02-29T00:30', '2024-02-29 12:34', '2024-02', '2024-02-29T12', '2024-02-29T12:34:56'])
def test_roundtrip(audio, value):
    p, kind = audio
    if kind == 'v23' and len(value.strip()) in (7, 13, 19):
        before = p.read_bytes()
        with pytest.raises(DateValidationError): write_metadata(p, Metadata(date=value), fields={'date'})
        assert p.read_bytes() == before
        return
    original = read_metadata(p)
    write_metadata(p, Metadata(date=value), fields={'date'})
    original.date = normalize_date(value)
    actual = read_metadata(p)
    actual.date = normalize_date(actual.date)
    assert actual == original
    if kind != 'm4b': assert ID3(p, translate=False).version[1] == (3 if kind == 'v23' else 4)

@pytest.mark.parametrize('value', ['not a date', '2023-02-29', '2024-02-29T12:00Z'])
@pytest.mark.parametrize('fields', [None, {'date'}])
def test_invalid_preserves_all_bytes(audio, value, fields):
    p, _ = audio
    before = p.read_bytes()
    with pytest.raises(DateValidationError): write_metadata(p, Metadata(date=value, title='Must not write'), fields=fields)
    assert p.read_bytes() == before


def test_unedited_invalid_date_does_not_block_title(audio):
    p, _ = audio
    write_metadata(p, Metadata(date='ignored invalid', title='Changed'), fields={'title'})
    assert read_metadata(p).title == 'Changed'
    assert read_metadata(p).date == '2020'
