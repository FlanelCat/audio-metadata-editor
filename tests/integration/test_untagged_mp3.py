import shutil

import pytest
from mutagen.id3 import ID3, delete, ID3NoHeaderError
from mutagen.mp3 import MP3
from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata

@pytest.fixture
def untagged(tmp_path, audio_fixture_dir):
    path = tmp_path / 'audio.mp3'
    shutil.copy2(audio_fixture_dir / 'silence.mp3', path)
    delete(path)
    return path


def test_title_creates_tag_without_changing_audio(untagged):
    payload = untagged.read_bytes()
    assert read_metadata(untagged) == Metadata()
    assert untagged.read_bytes() == payload
    before = MP3(untagged).info
    write_mp3_metadata(untagged, Metadata(title='Title', artist='Must not leak'), fields={'title'})
    assert read_metadata(untagged) == Metadata(title='Title')
    assert ID3(untagged).version == (2, 4, 0)
    after = MP3(untagged).info
    assert (after.length, after.sample_rate, after.channels) == (before.length, before.sample_rate, before.channels)
    assert untagged.read_bytes()[ID3(untagged).size:] == payload

@pytest.mark.parametrize('field,value', [('artist', 'Artist'), ('album', 'Album'), ('track_number', 3), ('disc_number', 2), ('date', '2024-02'), ('comment', 'Comment'), ('id3v1_comment', 'Separate'), ('narrator', 'Reader'), ('series', 'Series'), ('series_number', '01.5')])
def test_isolated_new_field(untagged, field, value):
    expected = Metadata()
    setattr(expected, field, value)
    write_mp3_metadata(untagged, expected, fields={field})
    assert read_metadata(untagged) == expected
    assert ID3(untagged).version == (2, 4, 0)

@pytest.mark.parametrize('fields,artwork', [({'title'}, None), ({'date'}, None), ({'track_number'}, None), (set(), None), (None, None), (set(), b'')])
def test_empty_operations_do_not_create_tag(untagged, fields, artwork):
    before = untagged.read_bytes()
    write_mp3_metadata(untagged, Metadata(), fields=fields, artwork=artwork)
    assert untagged.read_bytes() == before
    with pytest.raises(ID3NoHeaderError): ID3(untagged)


def test_artwork_and_full_write(untagged):
    write_mp3_metadata(untagged, Metadata(), fields=set(), artwork=b'cover', artwork_mime='image/jpeg')
    assert read_metadata(untagged) == Metadata(artwork=b'cover', artwork_mime='image/jpeg')
    delete(untagged)
    write_mp3_metadata(untagged, Metadata(title='Title', artist='Artist'))
    assert read_metadata(untagged) == Metadata(title='Title', artist='Artist')


def test_invalid_date_does_not_create_tag(untagged):
    from audio_metadata_editor.metadata.date import DateValidationError
    before = untagged.read_bytes()
    with pytest.raises(DateValidationError):
        write_mp3_metadata(untagged, Metadata(title='Do not write', date='not a date'))
    assert untagged.read_bytes() == before

@pytest.mark.parametrize('contents', [b'', b'not audio at all', b'RIFF' + b'\x00' * 100])
def test_invalid_audio_unchanged(tmp_path, contents):
    from mutagen import MutagenError
    p = tmp_path / 'invalid.mp3'
    p.write_bytes(contents)
    with pytest.raises(MutagenError): write_mp3_metadata(p, Metadata(title='Title'), fields={'title'})
    assert p.read_bytes() == contents


def test_disguised_m4b_unchanged(tmp_path, audio_fixture_dir):
    from mutagen import MutagenError
    p = tmp_path / 'not-mp3.mp3'
    shutil.copy2(audio_fixture_dir / 'silence.m4b', p)
    before = p.read_bytes()
    with pytest.raises(MutagenError): write_mp3_metadata(p, Metadata(title='Title'), fields={'title'})
    assert p.read_bytes() == before


def test_failed_save_leaves_untagged_audio(untagged, monkeypatch):
    before = untagged.read_bytes()
    def fail(*a, **k): raise OSError('save failed')
    monkeypatch.setattr(ID3, 'save', fail)
    with pytest.raises(OSError): write_mp3_metadata(untagged, Metadata(title='Title'), fields={'title'})
    assert untagged.read_bytes() == before
