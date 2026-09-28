import pytest
from audio_metadata_editor.text_template import parse_template, evaluate_template, TemplateError, VARIABLES


def render(text, **context):
    return evaluate_template(parse_template(text), context)


@pytest.mark.parametrize('name', sorted(VARIABLES))
def test_each_variable(name):
    value = 4 if name in {'index', 'track', 'disc'} else 'Text.mp3'
    assert render('{' + name + '}', **{name: value}) == str(value)


@pytest.mark.parametrize('template,expected', [('Literal', 'Literal'), ('', ''),
    ('{{Chapter}} {track:02}', '{Chapter} 04'),
    ('{index:03}/{disc:04} {title} {title}', '002/0001  '),
    ('{filename}', '* Real File.m4b'), ('{track:010}', '0000000004')])
def test_examples(template, expected):
    assert render(template, index=2, disc=1, track=4, title='', filename='* Real File.m4b') == expected


@pytest.mark.parametrize('template', ['{unknown}', '{Track}', '{track', '}', '{', '{track:2}',
    '{track:x}', '{track:banana}', '{track:.2f}', '{track:<10}', '{track:+03}',
    '{title:02}', '{track:00}', '{track:0101}', '{track:}', '{track.foo}', '{track[0]}', '{track!r}', '{{{'])
def test_syntax_errors(template):
    with pytest.raises(TemplateError):
        parse_template(template)


@pytest.mark.parametrize('name', ['track', 'disc'])
def test_missing_numeric(name):
    with pytest.raises(TemplateError, match='missing'):
        render('{' + name + '}', **{name: None})


def test_width_is_minimum():
    assert render('{track:02}', track=123) == '123'
    assert len(render('{index:0100}', index=1)) == 100


@pytest.mark.parametrize('name', ['index', 'track', 'disc'])
@pytest.mark.parametrize('width', [2, 3, 4])
def test_numeric_padding(name, width):
    assert render('{' + name + ':0' + str(width) + '}', **{name: 4}) == '0' * (width - 1) + '4'
