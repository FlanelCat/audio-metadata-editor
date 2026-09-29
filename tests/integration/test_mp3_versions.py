"""Existing ID3 versions must survive ordinary logical field writes."""
import shutil

import pytest
from mutagen.id3 import ID3, APIC, COMM, TALB, TIT2, TPE1, TRCK, TPOS, TSIZ, TXXX, TYER, TDAT, TIME

from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata


@pytest.fixture(params=[3, 4])
def tagged(request, tmp_path, audio_fixture_dir):
    path = tmp_path / 'audio.mp3'
    shutil.copy2(audio_fixture_dir / 'silence.mp3', path)
    tags = ID3()
    for frame in (
        TIT2(encoding=1, text=['Original']),
        TPE1(encoding=1, text=['Artist', 'Second artist']), TALB(encoding=1, text=['Album']),
        TRCK(encoding=1, text=['3/12']), TPOS(encoding=1, text=['2/5']),
        COMM(encoding=1, lang='swe', desc='', text=['Comment']),
        COMM(encoding=1, lang='eng', desc='ID3v1 Comment', text=['Separate']),
        APIC(encoding=1, mime='image/jpeg', type=3, desc='Cover', data=b'cover'),
        TXXX(encoding=1, desc='Unknown to application', text=['Keep']),
        TXXX(encoding=1, desc='Narrator', text=['Reader']),
        TXXX(encoding=1, desc='Series', text=['Series']),
    ):
        tags.add(frame)
    if request.param == 3:
        tags.add(TSIZ(encoding=0, text=['123456']))
        tags.add(TYER(encoding=0, text=['2020']))
        tags.add(TDAT(encoding=0, text=['0302']))
        tags.add(TIME(encoding=0, text=['1234']))
    tags.save(path, v2_version=request.param, v23_sep=None)
    return path, request.param


def test_title_only_preserves_version_and_unrelated_frames(tagged):
    path, version = tagged
    before = ID3(path, translate=False)
    write_mp3_metadata(path, Metadata(title='Changed — Unicode'), fields={'title'})
    after = ID3(path, translate=False)
    assert (after.version, 'TSIZ' in after) == (before.version, 'TSIZ' in before)
    assert after['TIT2'].text == ['Changed — Unicode']
    assert set(after) == set(before)
    for key in before.keys() - {'TIT2'}:
        assert after[key] == before[key], key
    assert read_metadata(path).title == 'Changed — Unicode'


@pytest.mark.parametrize('date', ['2025-06-07', ''])
def test_date_update_replaces_legacy_components(tagged, date):
    path, version = tagged
    write_mp3_metadata(path, Metadata(date=date), fields={'date'})
    assert ID3(path, translate=False).version == (2, version, 0)
    assert read_metadata(path).date == date
    tags = ID3(path, translate=False)
    if version == 3:
        assert 'TIME' not in tags
        assert ('TYER' in tags) == bool(date)


def test_full_write_keeps_version_and_unmanaged_frames(tagged):
    path, version = tagged
    before = ID3(path, translate=False)
    write_mp3_metadata(path, Metadata(title='Full', date='2025', track_total=99))
    after = ID3(path, translate=False)
    assert after.version == before.version
    assert after['TXXX:Unknown to application'] == before['TXXX:Unknown to application']
    assert after['APIC:Cover'] == before['APIC:Cover']
    if version == 3:
        assert after['TSIZ'] == before['TSIZ']
    saved = read_metadata(path)
    assert saved.title == 'Full' and saved.date == '2025'
    assert saved.track_number is saved.track_total is None


@pytest.mark.parametrize('field,value', [
    ('track_number', None), ('track_total', 20), ('disc_number', 4),
    ('disc_total', None), ('comment', 'New comment'),
    ('id3v1_comment', 'New separate comment'), ('narrator', 'New narrator'),
    ('series', 'New series'),
])
def test_other_filtered_fields_keep_version_and_isolation(tagged, field, value):
    path, version = tagged
    expected = read_metadata(path)
    setattr(expected, field, value)
    pending = Metadata()
    setattr(pending, field, value)
    write_mp3_metadata(path, pending, fields={field})
    assert ID3(path, translate=False).version == (2, version, 0)
    assert read_metadata(path) == expected
    if version == 3:
        assert ID3(path, translate=False)['TSIZ'].text == ['123456']


def test_explicit_artwork_retains_version(tagged):
    path, version = tagged
    for cover in (b'replacement', None):
        write_mp3_metadata(path, Metadata(), fields=set(), artwork=cover,
                           artwork_mime='image/png')
        assert ID3(path, translate=False).version == (2, version, 0)
        assert read_metadata(path).artwork == cover
        assert read_metadata(path).title == 'Original'
