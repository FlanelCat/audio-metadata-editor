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


def effective_fields_for_target(
    intended_fields: Set[str], edited: Metadata, baseline: Mapping[str, object],
) -> set[str]:
    """Return intended scalar differences; a missing value cannot prove equality.

    This is presentation comparison only. Callers retain validation, uncertainty,
    artwork and save policy independently of this result.
    """
    return {field for field in intended_fields
            if field not in baseline or getattr(edited, field) != baseline[field]}


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


def copy_target_paths(visual_paths: Sequence[str], selected_paths: Set[str],
                      source_path: str, *, down: bool) -> tuple[str, ...]:
    """Selected targets strictly on one visual side of the source, in row order."""
    if source_path not in visual_paths:
        return ()
    source = visual_paths.index(source_path)
    side = visual_paths[source + 1:] if down else visual_paths[:source]
    return tuple(path for path in side if path in selected_paths)
