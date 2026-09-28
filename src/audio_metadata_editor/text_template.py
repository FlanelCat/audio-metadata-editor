"""Restricted, pure text templates over explicit scalar contexts."""
from collections.abc import Mapping
import re

VARIABLES = frozenset(('index', 'track', 'disc', 'title', 'artist', 'album',
                       'album_artist', 'narrator', 'series', 'series_number', 'date', 'filename'))
NUMERIC = frozenset(('index', 'track', 'disc'))
MAX_WIDTH = 100


class TemplateError(ValueError):
    """A syntax error or unavailable value prevents generating this target."""


def parse_template(template: str) -> tuple[tuple[str, str | int | None], ...]:
    """Return literal/variable tokens; only exact names and :0WIDTH are allowed."""
    tokens = []
    i = 0
    while i < len(template):
        char = template[i]
        if char in '{}':
            if template[i:i + 2] == char * 2:
                tokens.append(('', char))
                i += 2
                continue
            if char == '}':
                raise TemplateError('Unmatched closing brace')
            end = template.find('}', i + 1)
            if end == -1:
                raise TemplateError('Unmatched opening brace')
            expression = template[i + 1:end]
            name, separator, spec = expression.partition(':')
            if name not in VARIABLES:
                raise TemplateError(f'Unknown variable: {name}')
            width = None
            if separator:
                if name not in NUMERIC:
                    raise TemplateError(f'{name} does not accept formatting')
                if not re.fullmatch(r'0[1-9][0-9]*', spec) or len(spec) > 4:
                    raise TemplateError('Padding must be 0 followed by a positive decimal width')
                width = int(spec[1:])
                if width > MAX_WIDTH:
                    raise TemplateError(f'Maximum padding width is {MAX_WIDTH}')
            tokens.append((name, width))
            i = end + 1
        else:
            end = i + 1
            while end < len(template) and template[end] not in '{}':
                end += 1
            tokens.append(('', template[i:end]))
            i = end
    return tuple(tokens)


def evaluate_template(tokens, context: Mapping[str, str | int | None]) -> str:
    parts = []
    for name, argument in tokens:
        if not name:
            parts.append(argument)
            continue
        if name not in context or context[name] is None:
            raise TemplateError(f'{name} is missing from accepted metadata')
        value = context[name]
        if name in NUMERIC:
            if type(value) is not int:
                raise TemplateError(f'{name} must be a whole number')
            parts.append(str(value).zfill(argument or 0))
        else:
            if not isinstance(value, str):
                raise TemplateError(f'{name} must be text')
            parts.append(value)
    return ''.join(parts)
