from pathlib import Path
import shutil

import pytest
from mutagen.id3 import COMM, ID3

from audio_metadata_editor.metadata import (
    Metadata, read_metadata, write_mp3_metadata, write_m4b_metadata,
)


@pytest.fixture(params=['mp3', 'm4b'])
def audio(request, tmp_path):
    path = tmp_path / f'audio.{request.param}'
    shutil.copy2(Path(__file__).parents[1] / 'fixtures' / f'silence.{request.param}', path)
    writer = write_mp3_metadata if request.param == 'mp3' else write_m4b_metadata
    writer(path, Metadata(track_number=3, track_total=12, disc_number=2, disc_total=5))
    return path, writer


@pytest.mark.parametrize('field', ['track_number', 'track_total', 'disc_number', 'disc_total'])
@pytest.mark.parametrize('value', [7, None])
def test_individual_pair_component(audio, field, value):
    path, writer = audio
    expected = read_metadata(path)
    setattr(expected, field, value)
    # Unrequested values deliberately differ from disk.
    pending = Metadata(track_number=99, track_total=99, disc_number=99, disc_total=99)
    setattr(pending, field, value)
    writer(path, pending, fields={field})
    assert read_metadata(path) == expected


@pytest.mark.parametrize('pair', ['track', 'disc'])
def test_clear_total_after_clearing_number(audio, pair):
    path, writer = audio
    writer(path, Metadata(), fields={f'{pair}_number'})
    writer(path, Metadata(), fields={f'{pair}_total'})
    saved = read_metadata(path)
    assert getattr(saved, f'{pair}_number') is None
    assert getattr(saved, f'{pair}_total') is None


def test_full_write_pair_behavior(audio):
    path, writer = audio
    writer(path, Metadata(track_total=12, disc_total=5), fields=None)
    saved = read_metadata(path)
    assert saved.track_number is saved.track_total is None
    assert saved.disc_number is saved.disc_total is None


@pytest.mark.parametrize('field,description', [('comment', ''), ('id3v1_comment', 'ID3v1 Comment')])
@pytest.mark.parametrize('value', ['Changed', ''])
def test_comment_category_isolation(tmp_path, field, description, value):
    path = tmp_path / 'audio.mp3'
    shutil.copy2(Path(__file__).parents[1] / 'fixtures' / 'silence.mp3', path)
    tags = ID3(path)
    for desc in ('', 'ID3v1 Comment', 'Unrelated'):
        for lang in ('eng', 'swe'):
            tags.add(COMM(encoding=1, lang=lang, desc=desc, text=[desc + lang, 'Second value']))
    tags.save(path)
    before = {k: f for k, f in ID3(path).items() if isinstance(f, COMM) and f.desc != description}
    pending = Metadata(comment='Must not leak', id3v1_comment='Must not leak')
    setattr(pending, field, value)
    write_mp3_metadata(path, pending, fields={field})
    comments = ID3(path).getall('COMM')
    after = {f.HashKey: f for f in comments if f.desc != description}
    assert after.keys() == before.keys()
    for key in before:
        assert after[key].text == before[key].text
        assert after[key].encoding == before[key].encoding
        assert after[key].lang == before[key].lang
    changed = [f for f in comments if f.desc == description]
    assert [f.text for f in changed] == ([[value]] if value else [])


def test_full_write_comments(tmp_path):
    path = tmp_path / 'audio.mp3'
    shutil.copy2(Path(__file__).parents[1] / 'fixtures' / 'silence.mp3', path)
    tags = ID3(path)
    for desc in ('', 'ID3v1 Comment', 'Unrelated'):
        tags.add(COMM(encoding=3, lang='swe', desc=desc, text=['Original']))
    tags.save(path)
    write_mp3_metadata(path, Metadata(comment='New'), fields=None)
    comments = {f.desc: f for f in ID3(path).getall('COMM')}
    assert set(comments) == {'', 'Unrelated'}
    assert comments[''].text == ['New']
    assert comments[''].lang == 'eng'
    assert comments['Unrelated'].text == ['Original']


def test_artwork_argument_independent_of_fields(audio):
    path, writer = audio
    writer(path, Metadata(), artwork=b'cover', artwork_mime='image/jpeg', fields=set())
    assert read_metadata(path).artwork == b'cover'
    writer(path, Metadata(title='New'), fields={'title'})
    assert read_metadata(path).artwork == b'cover'
    writer(path, Metadata(), artwork=None, fields=set())
    assert read_metadata(path).artwork is None
