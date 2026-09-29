"""Pure Date syntax, representation and readback-equivalence rules."""
from datetime import datetime
import re


class DateValidationError(ValueError):
    pass


class DateVerificationError(ValueError):
    pass


def normalize_date(value: str, *, id3_version: int | None = None) -> str:
    """Canonical ISO text; v2.3 cannot retain month-only/hour-only/seconds."""
    text = value.strip().replace('T', ' ')
    if not text:
        return ''
    if not re.fullmatch(r'[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2}(?: [0-9]{2}(?::[0-9]{2}(?::[0-9]{2})?)?)?)?)?', text):
        raise DateValidationError('Date must be YYYY, YYYY-MM, YYYY-MM-DD, or a date with HH, HH:MM or HH:MM:SS (no timezone).')
    try:
        datetime(int(text[:4]), int(text[5:7]) if len(text) >= 7 else 1,
                 int(text[8:10]) if len(text) >= 10 else 1,
                 int(text[11:13]) if len(text) >= 13 else 0,
                 int(text[14:16]) if len(text) >= 16 else 0,
                 int(text[17:19]) if len(text) >= 19 else 0)
    except ValueError as exc:
        raise DateValidationError('Date contains an impossible calendar date or time.') from exc
    # Mutagen expands legacy TIME to seconds ':00' on readback.
    if len(text) == 19 and text.endswith(':00'):
        text = text[:-3]
    if id3_version == 3 and len(text) not in (4, 10, 16):
        raise DateValidationError('Date in ID3v2.3 must be YYYY, YYYY-MM-DD, or YYYY-MM-DD HH:MM; other precision cannot be preserved.')
    return text


def verify_date(requested: str, actual: str) -> None:
    """Reading successfully is insufficient if the requested Date was lost."""
    try:
        matches = normalize_date(requested) == normalize_date(actual)
    except DateValidationError:
        matches = False
    if not matches:
        raise DateVerificationError('The write may have occurred, but readback did not match the requested Date. Pending changes are retained; no rollback was attempted.')
