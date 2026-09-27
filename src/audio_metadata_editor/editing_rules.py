"""Stateless scalar edit decisions; callers own persistence and editing state."""
from collections.abc import Mapping, Sequence, Set
from dataclasses import fields

from .metadata.model import Metadata


SCALAR_FIELDS = frozenset(
    field.name for field in fields(Metadata)
    if field.name not in {"artwork", "artwork_mime"}
)


def changed_scalar_fields(accepted: Metadata, edited: Metadata) -> set[str]:
    """Compare scalar values exactly, without normalization or uncertainty policy."""
    return {field for field in SCALAR_FIELDS
            if getattr(accepted, field) != getattr(edited, field)}


def effective_multi_fields(
    intended_fields: Set[str],
    edited: Metadata,
    baselines: Sequence[Mapping[str, object]],
    *,
    invalid_fields: Set[str] = frozenset(),
    unresolved_fields: Set[str] = frozenset(),
) -> set[str]:
    """Retain scalar intent unless every accepted target value equals the edit.

    All field sets contain scalar logical names, never artwork. Invalid raw text
    is represented by field names supplied by the caller, not by Metadata values.
    Missing baselines/values cannot prove restoration. Unresolved fields remain
    intended independently of cached equality. Inputs are never mutated.
    """
    effective = set(intended_fields) | set(unresolved_fields)
    if not baselines:
        return effective
    restored = {
        field for field in effective - invalid_fields - unresolved_fields
        if all(field in baseline and getattr(edited, field) == baseline[field]
               for baseline in baselines)
    }
    return effective - restored
