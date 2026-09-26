import importlib
import shutil

import pytest
from mutagen.id3 import delete as delete_id3
from mutagen.mp4 import MP4

from audio_metadata_editor.metadata import Metadata, MetadataReadError, read_metadata


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
def test_valid_untagged(tmp_path, audio_fixture_dir, suffix):
    path = tmp_path / f'audio.{suffix}'
    shutil.copy2(audio_fixture_dir / f'silence.{suffix}', path)
    if suffix == 'mp3':
        delete_id3(path)
    else:
        MP4(path).delete()
    assert read_metadata(path) == Metadata()


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'open'])
def test_read_failure_is_not_empty(tmp_path, monkeypatch, suffix, failure):
    path = tmp_path / f'bad.{suffix}'
    if failure == 'corrupt':
        path.write_bytes(b'not audio')
    if failure == 'open':
        module = importlib.import_module(f'audio_metadata_editor.metadata.{suffix}')
        def fail(*args, **kwargs):
            raise PermissionError('injected access failure')
        monkeypatch.setattr(module, 'ID3' if suffix == 'mp3' else 'MP4', fail)
    with pytest.raises(MetadataReadError) as caught:
        read_metadata(path)
    assert caught.value.path == path
    assert caught.value.__cause__ is not None


@pytest.mark.parametrize('suffix', ['mp3', 'm4b'])
def test_parsing_failure_has_stable_contract(tmp_path, audio_fixture_dir, monkeypatch, suffix):
    from audio_metadata_editor.metadata import MetadataReadError
    path = tmp_path / f'audio.{suffix}'
    shutil.copy2(audio_fixture_dir / f'silence.{suffix}', path)
    before = path.read_bytes()
    module = importlib.import_module(f'audio_metadata_editor.metadata.{suffix}')
    def fail(*args):
        raise ValueError('cannot decode metadata')
    monkeypatch.setattr(module, '_get_text', fail)
    with pytest.raises(MetadataReadError, match='cannot decode metadata'):
        read_metadata(path)
    assert path.read_bytes() == before
