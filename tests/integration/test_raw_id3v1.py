"""The physical ID3v1 trailer is opaque, unrelated data for every app edit."""
import shutil

import pytest
from mutagen.id3 import ID3, TIT2, TPE1, COMM, TSIZ, TXXX, delete

from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata
import audio_metadata_editor.metadata.mp3 as module


@pytest.fixture(params=[3, 4])
def raw_tagged(request, tmp_path, audio_fixture_dir):
    path = tmp_path / 'audio.mp3'
    shutil.copy2(audio_fixture_dir / 'silence.mp3', path)
    tags = ID3(path)
    tags.add(TIT2(encoding=1, text=['v2 title']))
    tags.add(TPE1(encoding=1, text=['v2 artist']))
    tags.add(COMM(encoding=1, lang='eng', desc='', text=['v2 comment']))
    tags.add(COMM(encoding=1, lang='eng', desc='ID3v1 Comment', text=['logical comment']))
    tags.add(TXXX(encoding=1, desc='Unrelated', text=['Keep']))
    if request.param == 3:
        tags.add(TSIZ(encoding=0, text=['123']))
    tags.save(path, v2_version=request.param, v1=0)
    trailer = (b'TAG' + b'raw title'.ljust(30, b' ') + b'raw artist'.ljust(30, b'\0')
               + b'raw album'.ljust(30, b' ') + b'1987'
               + b'raw comment\xff'.ljust(28, b' ') + b'\0\x07\xfe')
    assert len(trailer) == 128
    with path.open('ab') as stream:
        stream.write(trailer)
    return path, trailer, request.param


def test_title_only_preserves_raw_trailer(raw_tagged):
    path, trailer, version = raw_tagged
    payload = path.read_bytes()[ID3(path).size:-128]
    write_mp3_metadata(path, Metadata(title='New'), fields={'title'})
    assert path.read_bytes()[-128:] == trailer
    tags = ID3(path, translate=False)
    assert tags.version == (2, version, 0)
    assert tags['TIT2'].text == ['New']
    assert path.read_bytes()[tags.size:-128] == payload


@pytest.mark.parametrize('field,value', [
    ('artist', 'New'), ('comment', 'New'), ('comment', ''),
    ('id3v1_comment', 'New'), ('id3v1_comment', ''),
    ('track_number', 9), ('track_total', 12), ('disc_number', 2), ('disc_total', 4),
    ('date', '2025-06-07'), ('narrator', 'Reader'), ('series', 'Series'),
    ('series_number', '01.50'), ('publisher', 'Publisher'),
])
def test_filtered_writes_preserve_raw_and_unrelated_frames(raw_tagged, field, value):
    path, trailer, version = raw_tagged
    expected = read_metadata(path)
    setattr(expected, field, value)
    metadata = Metadata()
    setattr(metadata, field, value)
    write_mp3_metadata(path, metadata, fields={field})
    assert path.read_bytes()[-128:] == trailer
    assert read_metadata(path) == expected
    tags = ID3(path, translate=False, load_v1=False)
    assert tags.version == (2, version, 0)
    assert tags['TXXX:Unrelated'].text == ['Keep']
    if version == 3:
        assert tags['TSIZ'].text == ['123']


@pytest.mark.parametrize('full', [False, True])
@pytest.mark.parametrize('cover', [b'new cover', None])
def test_full_and_artwork_writes(raw_tagged, full, cover):
    path, trailer, version = raw_tagged
    write_mp3_metadata(path, Metadata(title='Full', artist='Artist', date='2025'),
                       fields=None if full else set(), artwork=cover, artwork_mime='image/png')
    assert path.read_bytes()[-128:] == trailer
    assert read_metadata(path).artwork == cover
    assert read_metadata(path).title == ('Full' if full else 'v2 title')
    assert ID3(path, load_v1=False).version == (2, version, 0)


@pytest.mark.parametrize('untagged', [False, True])
def test_absent_raw_trailer_stays_absent(raw_tagged, untagged):
    path, trailer, version = raw_tagged
    with path.open('r+b') as stream:
        stream.truncate(path.stat().st_size - 128)
    if untagged:
        delete(path)
    payload = path.read_bytes()[0 if untagged else ID3(path).size:]
    for fields in ({'title'}, None):
        write_mp3_metadata(path, Metadata(title='New'), fields=fields)
        assert not path.read_bytes()[-128:].startswith(b'TAG')
        assert path.read_bytes()[ID3(path).size:] == payload
        assert ID3(path).version == (2, 4 if untagged else version, 0)


def test_raw_only_creates_v2_without_importing_raw_fields(raw_tagged):
    path, trailer, _ = raw_tagged
    delete(path, delete_v1=False)
    payload = path.read_bytes()
    assert read_metadata(path) == Metadata()
    write_mp3_metadata(path, Metadata(title='New'), fields={'title'})
    assert read_metadata(path) == Metadata(title='New')
    assert path.read_bytes()[ID3(path, load_v1=False).size:] == payload
    assert path.read_bytes()[-128:] == trailer


@pytest.mark.parametrize('stage', ['before', 'after'])
def test_save_failure_restores_without_duplicate(raw_tagged, monkeypatch, stage):
    path, trailer, _ = raw_tagged
    original = ID3.save
    before = path.read_bytes()
    def fail(self, stream, **kwargs):
        if stage == 'after':
            original(self, stream, **kwargs)
        raise OSError('injected save failure')
    monkeypatch.setattr(ID3, 'save', fail)
    with pytest.raises(OSError, match='injected save failure'):
        write_mp3_metadata(path, Metadata(title='New'), fields={'title'})
    contents = path.read_bytes()
    assert contents[-128:] == trailer
    assert contents.count(trailer) == 1
    if stage == 'before':
        assert contents == before


@pytest.mark.parametrize('stage', ['snapshot', 'write', 'short_write', 'flush', 'verify'])
def test_preservation_io_failure_is_surfaced(raw_tagged, monkeypatch, stage):
    path, trailer, _ = raw_tagged
    before = path.read_bytes()
    real_open = open

    class Stream:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.restored = False

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.wrapped.close()

        def read(self, size=-1):
            if stage == 'snapshot':
                raise OSError('snapshot failed')
            data = self.wrapped.read(size)
            return b'X' * len(data) if stage == 'verify' and self.restored else data

        def write(self, data):
            if data == trailer:
                if stage == 'write':
                    raise OSError('restoration write failed')
                if stage == 'short_write':
                    return self.wrapped.write(data[:10])
                self.restored = True
            return self.wrapped.write(data)

        def flush(self):
            if stage == 'flush' and self.restored:
                raise OSError('restoration flush failed')
            return self.wrapped.flush()

    monkeypatch.setattr(module, 'open', lambda *a: Stream(real_open(*a)), raising=False)
    with pytest.raises(OSError):
        write_mp3_metadata(path, Metadata(title='New'), fields={'title'})
    if stage == 'snapshot':
        assert path.read_bytes() == before


def test_raw_id3v10_bytes_preserved(raw_tagged):
    path, trailer, _ = raw_tagged
    trailer = trailer[:97] + bytes(range(1, 31)) + b'\xff'
    with path.open('r+b') as stream:
        stream.seek(-128, 2)
        stream.write(trailer)
    write_mp3_metadata(path, Metadata(title='New'), fields={'title'})
    assert path.read_bytes()[-128:] == trailer


def test_large_tag_growth_preserves_audio_and_trailer(raw_tagged):
    path, trailer, _ = raw_tagged
    payload = path.read_bytes()[ID3(path).size:-128]
    write_mp3_metadata(path, Metadata(title='A' * 40000), fields={'title'})
    assert path.read_bytes()[ID3(path).size:-128] == payload
    assert path.read_bytes()[-128:] == trailer


def test_save_and_restore_failure_are_both_chained(raw_tagged, monkeypatch):
    path, _, _ = raw_tagged
    def fail_save(*args, **kwargs):
        raise OSError('save failed')
    def fail_restore(*args):
        raise OSError('restore failed')
    monkeypatch.setattr(ID3, 'save', fail_save)
    monkeypatch.setattr(module, '_restore_raw_id3v1', fail_restore)
    with pytest.raises(OSError, match='restore failed') as caught:
        write_mp3_metadata(path, Metadata(title='New'), fields={'title'})
    assert str(caught.value.__context__) == 'save failed'
