import pytest
from audio_metadata_editor.metadata.date import normalize_date, verify_date, DateValidationError, DateVerificationError

@pytest.mark.parametrize('value,expected', [('', ''), (' \t', ''), (' 2020 ', '2020'), ('2020-02', '2020-02'), ('2020-02-29', '2020-02-29'), ('2020-02-29T00', '2020-02-29 00'), ('2020-02-29T00:00', '2020-02-29 00:00'), ('2020-02-29 23:59:59', '2020-02-29 23:59:59')])
def test_valid(value, expected):
    assert normalize_date(value) == expected
    verify_date(value, expected)

@pytest.mark.parametrize('value', ['not a date', '2021-02-29', '2020-13', '0000', '2020-00-01', '2020-04-31', '2020/02/02', '20', '2020-2', '2020-02-29T24:00', '2020-02-29T12:60', '2020-02-29T12:00:60', '2020-02-29T12:00Z', '2020-02-29T12:00+01:00', '2020-02-29T12:00:00.1', '2020-02-29  12:00', '２０２０'])
def test_invalid(value):
    with pytest.raises(DateValidationError): normalize_date(value)

@pytest.mark.parametrize('value', ['2020-02', '2020-02-29T12', '2020-02-29T12:00:01'])
def test_v23_precision(value):
    normalize_date(value)
    with pytest.raises(DateValidationError, match='ID3v2.3'): normalize_date(value, id3_version=3)

@pytest.mark.parametrize('actual', ['', '2019', '2020-01', 'invalid'])
def test_mismatch(actual):
    with pytest.raises(DateVerificationError): verify_date('2020', actual)


def test_legacy_zero_second_equivalence():
    verify_date('2020-02-29T00:00', '2020-02-29 00:00:00')
    assert normalize_date('2020-02-29 00:00:00', id3_version=3) == '2020-02-29 00:00'
