# ADR 001: Explicit Save Model

## Status

Accepted

## Context

Audio Metadata Editor provides two different metadata-editing workflows:

1. field-by-field editing in the center-panel file table; and
2. single-file or multi-file editing in the metadata panel.

These workflows serve different purposes and intentionally use different save behavior.

The center-panel table is optimized for rapidly editing the same metadata field across multiple files. The metadata panel is designed for editing several fields before saving them together.

A single save model for both workflows would make one of these workflows less efficient and would not reflect the intended user interaction.

## Decision

The application will support two explicit save mechanisms.

### Center-Panel Table

When a metadata cell in the center-panel table is being edited, pressing **Enter** is an explicit save action.

The application will:

1. commit the edited cell value;
2. write that field to the corresponding audio file;
3. preserve unrelated metadata;
4. update the application's in-memory representation of the saved metadata;
5. ensure that the successfully saved edit is no longer considered dirty; and
6. move editing to the same column in the next row when one exists.

Pressing Enter therefore means:

```text
Edit cell → Enter → Save field → Continue to next row
```

Simply selecting or entering a cell is not a save action.

If the value has not actually changed, the operation must not create dirty state or cause a later Unsaved Changes prompt.

### Metadata Panel

Edits made in the metadata panel remain pending until explicitly saved.

They are written to disk only when the user:

* clicks **Save Changes**; or
* chooses **Save** from an Unsaved Changes prompt.

Pressing Enter, changing focus, or navigating between metadata-panel fields does not save those changes.

The metadata-panel workflow is therefore:

```text
Edit field(s)
      │
      ▼
Pending changes
      │
      ├── Save Changes ────────────► Save
      │
      └── Unsaved Changes prompt
                    │
                    ├── Save ──────► Save
                    ├── Discard
                    └── Cancel
```

### Persistence Responsibility

UI components determine when the user has requested a save.

Actual MP3 and M4B persistence remains the responsibility of the metadata layer.

The center-panel table may emit a save request when Enter confirms an edited cell, but it should not contain format-specific MP3 or M4B writing logic.

## Consequences

The application intentionally has two save workflows rather than one universal editing workflow.

Center-panel editing supports rapid sequential metadata editing without requiring the Save Changes button after every field.

Metadata-panel editing supports changing several fields before committing them together.

Dirty-state tracking must distinguish between:

* successfully saved center-panel edits; and
* pending metadata-panel edits.

After a center-panel Enter-save succeeds, application state must be synchronized with the newly saved metadata so that the saved change does not incorrectly remain dirty.

Tests must cover both workflows independently.

In particular, regression tests should verify that:

* editing a center-panel cell and pressing Enter saves the field;
* Enter moves editing to the same column in the next row;
* the successfully saved file is not left dirty;
* the saved edit does not later trigger an Unsaved Changes prompt;
* entering or leaving a center-panel cell without changing its value does not create dirty state;
* metadata-panel edits remain pending until Save Changes or Save from an Unsaved Changes prompt;
* pressing Enter in a metadata-panel field does not write metadata to disk.
