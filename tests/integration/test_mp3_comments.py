import shutil
import pytest
from mutagen.id3 import ID3, COMM, TSIZ, APIC, TRCK, TPOS, TXXX, delete
from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata

@pytest.fixture(params=[3, 4])
def audio(request, tmp_path, audio_fixture_dir):
    p = tmp_path / 'comments.mp3'
    shutil.copy2(audio_fixture_dir / 'silence.mp3', p)
    tags = ID3(p)
    for desc, lang, text in [('Description', 'eng', 'Legacy described comment'), ('', 'swe', 'Swedish'), ('ID3v1 Comment', 'eng', 'Separate')]:
        tags.add(COMM(encoding=1, desc=desc, lang=lang, text=[text]))
    tags.add(APIC(encoding=1, mime='image/jpeg', type=3, desc='Cover', data=b'cover'))
    tags.add(TRCK(encoding=1, text=['2/9']))
    tags.add(TPOS(encoding=1, text=['1/3']))
    tags.add(TXXX(encoding=1, desc='Custom', text=['Keep']))
    if request.param == 3: tags.add(TSIZ(encoding=0, text=['123']))
    tags.save(p, v2_version=request.param)
    return p


def test_described_clear_does_not_resurrect(audio):
    # The old reader exposes unrelated described/language-specific comments,
    # and deleting desc="" cannot clear the described value it exposed.
    tags = ID3(audio, translate=False)
    tags.delall('COMM::swe')
    tags.save(audio, v2_version=tags.version[1])
    write_mp3_metadata(audio, Metadata(comment=''), fields={'comment'})
    assert read_metadata(audio).comment == ''

@pytest.mark.parametrize('value', ['Changed', ''])
def test_canonical_change_clear_preserves_other_frames(audio, value):
    tags = ID3(audio, translate=False)
    tags.add(COMM(encoding=1, desc='', lang='eng', text=['Original']))
    tags.save(audio, v2_version=tags.version[1])
    before = ID3(audio, translate=False)
    write_mp3_metadata(audio, Metadata(comment=value), fields={'comment'})
    after = ID3(audio, translate=False)
    assert after.version == before.version
    assert read_metadata(audio).comment == value
    assert read_metadata(audio).id3v1_comment == 'Separate'
    for key in before.keys() - {'COMM::eng'}:
        assert key in after and after[key] == before[key], key
    assert ('COMM::eng' in after) == bool(value)


def test_reader_ignores_uneditable_candidates(audio):
    assert read_metadata(audio).comment == ''

@pytest.mark.parametrize('value', ['Changed separate', ''])
def test_id3v1_category_isolation(audio, value):
    tags = ID3(audio, translate=False)
    tags.add(COMM(encoding=1, desc='', lang='eng', text=['Ordinary']))
    tags.add(COMM(encoding=1, desc='ID3v1 Comment', lang='swe', text=['Swedish separate']))
    tags.save(audio, v2_version=tags.version[1])
    before = {k: f for k, f in tags.items() if not isinstance(f, COMM) or f.desc != 'ID3v1 Comment'}
    write_mp3_metadata(audio, Metadata(id3v1_comment=value), fields={'id3v1_comment'})
    after = ID3(audio, translate=False)
    assert read_metadata(audio).comment == 'Ordinary'
    assert read_metadata(audio).id3v1_comment == value
    for key, frame in before.items(): assert after[key] == frame

@pytest.mark.parametrize('english', [True, False])
def test_deterministic_language_selection(audio, monkeypatch, english):
    tags = ID3(audio, translate=False)
    tags.delall('COMM:ID3v1 Comment')
    for lang in (['swe', 'deu', 'eng'] if english else ['swe', 'deu']):
        tags.add(COMM(encoding=1, desc='ID3v1 Comment', lang=lang, text=[lang]))
    tags.add(COMM(encoding=1, desc='', lang='eng', text=['Canonical']))
    tags.save(audio, v2_version=tags.version[1])
    normal = read_metadata(audio)
    getall = ID3.getall
    monkeypatch.setattr(ID3, 'getall', lambda self, key: list(reversed(getall(self, key))))
    assert read_metadata(audio) == normal
    assert normal.comment == 'Canonical'
    assert normal.id3v1_comment == ('eng' if english else 'deu')


def test_untagged_comment_identity(audio):
    delete(audio)
    write_mp3_metadata(audio, Metadata(comment='New'), fields={'comment'})
    tags = ID3(audio)
    assert tags.version == (2, 4, 0)
    assert [f.HashKey for f in tags.getall('COMM')] == ['COMM::eng']
    assert read_metadata(audio).comment == 'New'
