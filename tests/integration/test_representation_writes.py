"""S4: actual library boundaries using only temporary public-fixture copies."""
import shutil

import pytest
from mutagen.id3 import ID3, TIT2
from mutagen.mp4 import MP4

from audio_metadata_editor.metadata import Metadata, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.metadata.representation import (
    NUMERIC_FIELDS, SCALAR_FIELDS, RepresentationError, verify_values,
)

TEXT_FIELDS = sorted(SCALAR_FIELDS - NUMERIC_FIELDS - {'date'})


@pytest.fixture(params=['mp3', 'v23', 'm4b'])
def audio(request, tmp_path, audio_fixture_dir):
    ext = 'mp3' if request.param == 'v23' else request.param
    path = tmp_path / f'audio.{ext}'
    shutil.copy2(audio_fixture_dir / f'silence.{ext}', path)
    if request.param == 'v23':
        tags = ID3(path)
        tags.update_to_v23()
        tags.save(path, v2_version=3)
    return path


def test_library_nul_reproducer(audio):
    """Retain the pre-fix reproducer below application validation."""
    if audio.suffix == '.mp3':
        tags = ID3(audio, translate=False)
        tags.add(TIT2(encoding=3, text=['left\0right']))
        tags.save(audio, v2_version=tags.version[1], v23_sep=None)
        assert read_metadata(audio).title == 'left'
    else:
        tags = MP4(audio)
        tags['\xa9nam'] = ['left\0right']
        tags.save()
        assert read_metadata(audio).title == 'left\0right'


@pytest.mark.parametrize('field', TEXT_FIELDS)
@pytest.mark.parametrize('value', ['left\0right', 'left\n\r\t\x01right 日本語 🎧', 'bad\ud800', 'Ångström 日本語 🎧'])
def test_scalar_boundaries_and_isolation(audio, field, value):
    before = audio.read_bytes()
    original = read_metadata(audio)
    requested = Metadata()
    setattr(requested, field, value)
    invalid = ('\ud800' in value or (audio.suffix == '.mp3' and '\0' in value)
               or (audio.suffix == '.m4b' and field == 'id3v1_comment')
               or (audio.suffix == '.mp3' and field == 'genre' and '\n' in value))
    if invalid:
        with pytest.raises(RepresentationError, match=field.replace('_', ' ').title() if field != 'id3v1_comment' else 'ID3v1 Comment'):
            write_metadata(audio, requested, fields={field})
        assert audio.read_bytes() == before
    else:
        write_metadata(audio, requested, fields={field})
        actual = read_metadata(audio)
        verify_values(audio, {field: value}, actual)
        setattr(original, field, value)
        assert actual == original


@pytest.mark.parametrize('field', sorted(NUMERIC_FIELDS))
@pytest.mark.parametrize('value', [None, 1, 65535, 65536, 0, -1])
def test_numeric_representation(audio, field, value):
    before = audio.read_bytes()
    requested = Metadata()
    setattr(requested, field, value)
    if audio.suffix == '.m4b' and value is not None and not 0 <= value <= 65535:
        with pytest.raises(RepresentationError):
            write_metadata(audio, requested, fields={field})
        assert audio.read_bytes() == before
    else:
        write_metadata(audio, requested, fields={field})
        verify_values(audio, {field: value}, read_metadata(audio))


@pytest.mark.parametrize('value,expected', [('17', 'Rock'), ('(17)', 'Rock'), ('RX', 'Remix'), ('CR', 'Cover')])
def test_genre_alias_equivalence(audio, value, expected):
    write_metadata(audio, Metadata(genre=value), fields={'genre'})
    actual = read_metadata(audio)
    assert actual.genre == (expected if audio.suffix == '.mp3' else value)
    verify_values(audio, {'genre': value}, actual)


@pytest.mark.parametrize('value', ['(17)(18)', '(17)custom', '((17)'])
def test_genre_scalar_loss_preflight(audio, value):
    before = audio.read_bytes()
    if audio.suffix == '.mp3':
        with pytest.raises(RepresentationError, match='Genre'):
            write_metadata(audio, Metadata(genre=value), fields={'genre'})
        assert audio.read_bytes() == before
    else:
        write_metadata(audio, Metadata(genre=value), fields={'genre'})
        assert read_metadata(audio).genre == value


def test_unrequested_invalid_values_do_not_block(audio):
    write_metadata(audio, Metadata(title='valid', artist='bad\0\ud800', date='invalid'), fields={'title'})
    assert read_metadata(audio).title == 'valid'
