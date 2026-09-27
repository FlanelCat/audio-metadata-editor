from copy import deepcopy
from dataclasses import replace

import pytest

from audio_metadata_editor.editing_rules import (
    SCALAR_FIELDS, changed_scalar_fields, effective_multi_fields,
)
from audio_metadata_editor.metadata.model import Metadata


NUMERIC_FIELDS = ('track_number', 'track_total', 'disc_number', 'disc_total')
TEXT_FIELDS = ('title', 'artist', 'album', 'album_artist', 'genre', 'date',
               'composer', 'comment', 'id3v1_comment', 'description', 'publisher',
               'copyright', 'narrator', 'series', 'series_number')


def test_catalogue():
    assert isinstance(SCALAR_FIELDS, frozenset)
    assert SCALAR_FIELDS == set(TEXT_FIELDS + NUMERIC_FIELDS)


def test_identical_metadata():
    metadata = Metadata(title='Title', artist='Artist', track_number=4,
                        artwork=b'cover', artwork_mime='image/jpeg')
    assert not changed_scalar_fields(metadata, deepcopy(metadata))
    assert not changed_scalar_fields(metadata, metadata)


@pytest.mark.parametrize('field', TEXT_FIELDS)
@pytest.mark.parametrize('accepted,edited', [('', 'value'), ('value', ''), ('A', 'B')])
def test_text_fields(field, accepted, edited):
    assert changed_scalar_fields(Metadata(**{field: accepted}),
                                 Metadata(**{field: edited})) == {field}


def test_multiple_fields_and_artwork():
    accepted = Metadata(title='A', artist='B', artwork=b'old', artwork_mime='image/jpeg')
    edited = replace(accepted, title='C', artist='D', artwork=b'new', artwork_mime='image/png')
    assert changed_scalar_fields(accepted, edited) == {'title', 'artist'}
    assert not changed_scalar_fields(accepted, replace(accepted, artwork=None, artwork_mime=''))


@pytest.mark.parametrize('field', NUMERIC_FIELDS)
@pytest.mark.parametrize('accepted,edited', [(None, 3), (3, None), (1, 2), (None, 0), (0, None), (3, 3)])
def test_numeric_components(field, accepted, edited):
    assert changed_scalar_fields(Metadata(**{field: accepted}), Metadata(**{field: edited})) == (
        {field} if accepted != edited else set())


@pytest.mark.parametrize('accepted,edited', [('01', '1'), ('1.0', '1'), ('', '0'), (' 1', '1'), ('1', '1')])
def test_series_strings(accepted, edited):
    expected = {'series_number'} if accepted != edited else set()
    a, b = Metadata(series_number=accepted), Metadata(series_number=edited)
    assert changed_scalar_fields(a, b) == expected
    assert effective_multi_fields({'series_number'}, b, [{'series_number': accepted}] * 2) == expected


@pytest.mark.parametrize('values,edit,expected', [
    (['A', 'A'], 'B', {'title'}), (['A', 'A'], 'A', set()),
    (['A', 'B'], 'B', {'title'}), (['A', 'B'], '', {'title'}),
    (['B', 'B'], 'B', set()), (['', ''], '', set()),
])
def test_multi_text(values, edit, expected):
    assert effective_multi_fields({'title'}, Metadata(title=edit),
                                  [{'title': value} for value in values]) == expected


def test_common_changed_then_restored_preserves_other_intent():
    baselines = [{'title': 'A', 'artist': 'old'}] * 2
    intent = effective_multi_fields({'title', 'artist'}, Metadata(title='B', artist='new'), baselines)
    assert intent == {'title', 'artist'}
    assert effective_multi_fields(intent, Metadata(title='A', artist='new'), baselines) == {'artist'}


@pytest.mark.parametrize('field', NUMERIC_FIELDS)
@pytest.mark.parametrize('values,edit,invalid,expected', [
    ([None, None], None, False, False), ([3, 3], None, False, True),
    ([None, None], 3, False, True), ([3, 3], 3, False, False),
    ([3, 4], 3, False, True), ([None, None], None, True, True),
    ([3, 3], None, True, True),
])
def test_multi_numbers(field, values, edit, invalid, expected):
    assert effective_multi_fields(
        {field}, Metadata(**{field: edit}), [{field: value} for value in values],
        invalid_fields={field} if invalid else set(),
    ) == ({field} if expected else set())


@pytest.mark.parametrize('value', ['A', 'B'])
@pytest.mark.parametrize('intended', [set(), {'title'}])
def test_unresolved_is_effective_even_without_ordinary_intent(value, intended):
    assert effective_multi_fields(intended, Metadata(title=value), [{'title': 'A'}] * 2,
                                  unresolved_fields={'title'}) == {'title'}


@pytest.mark.parametrize('baselines', [[], [{}], [{'title': 'A'}, {}]])
def test_missing_baselines_cannot_clear_intent(baselines):
    assert effective_multi_fields({'title'}, Metadata(title='A'), baselines) == {'title'}


def test_invalid_field_does_not_create_unrequested_scalar_intent():
    # Raw-invalid dirty state is also checked separately by MainWindow.
    assert effective_multi_fields(set(), Metadata(), [{'track_number': None}],
                                  invalid_fields={'track_number'}) == set()


def test_combined_rules_and_no_input_mutation():
    intended = {'title', 'artist', 'track_number', 'album'}
    edited = Metadata(title='changed', artist='A', album='restored')
    baselines = [{'title': 'old', 'artist': 'A', 'track_number': None, 'album': 'restored'}] * 2
    invalid, unresolved = {'track_number'}, {'artist', 'series'}
    inputs = (intended, edited, baselines, invalid, unresolved)
    original = deepcopy(inputs)
    result = effective_multi_fields(intended, edited, baselines,
                                    invalid_fields=invalid, unresolved_fields=unresolved)
    assert result == {'title', 'artist', 'track_number', 'series'}
    result.clear()
    assert inputs == original
    accepted = Metadata(title='old')
    snapshot = deepcopy((accepted, edited))
    changed_scalar_fields(accepted, edited)
    assert (accepted, edited) == snapshot


@pytest.mark.parametrize('baseline,edited,intended,expected', [
    ({'artist': 'A'}, Metadata(artist='A'), {'artist'}, set()),
    ({'artist': 'B'}, Metadata(artist='A'), {'artist'}, {'artist'}),
    ({'artist': ''}, Metadata(artist=''), {'artist'}, set()),
    ({'artist': 'B'}, Metadata(artist=''), {'artist'}, {'artist'}),
    ({'artist': 'A', 'album': 'X'}, Metadata(artist='A', album='Z'),
     {'artist', 'album'}, {'album'}),
    ({'artist': 'A'}, Metadata(artist='B'), set(), set()),
    ({}, Metadata(artist=''), {'artist'}, {'artist'}),
    ({'track_number': None, 'track_total': 4}, Metadata(track_number=None, track_total=5),
     {'track_number', 'track_total'}, {'track_total'}),
    ({'series_number': '01'}, Metadata(series_number='1'), {'series_number'}, {'series_number'}),
])
def test_effective_fields_for_target(baseline, edited, intended, expected):
    from audio_metadata_editor.editing_rules import effective_fields_for_target
    before = deepcopy((baseline, edited, intended))
    result = effective_fields_for_target(intended, edited, baseline)
    assert result == expected
    result.clear()
    assert (baseline, edited, intended) == before
