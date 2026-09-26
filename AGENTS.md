# AGENTS.md

## Project

Audio Metadata Editor is a Python/PySide6 desktop application for viewing and editing audiobook metadata.

The application currently supports MP3 and M4B files and uses Mutagen for metadata access.

Before making changes, read the relevant project documentation:

* `docs/requirements.md`
* `docs/architecture.md`
* `docs/testing.md`
* files under `docs/decisions/`

These documents define intended application behavior and architectural decisions.

If implementation behavior conflicts with documented requirements or decisions, do not silently change the requirements to match the implementation. Identify the conflict.

## Development Principles

Make small, focused, reviewable changes.

Do not perform unrelated refactoring while implementing a feature or fixing a bug.

Prefer preserving existing working behavior unless the requested change explicitly modifies that behavior.

Do not introduce a database or other persistent metadata store. Audio files are the authoritative metadata source.

Do not introduce automatic metadata modification.

Metadata writes must follow the explicit-save behavior defined in the project documentation.

## Editing and Save Behavior

The application intentionally has two different editing workflows.

### Center-Panel File Table

The center-panel table supports rapid field-by-field editing.

When the user edits a metadata cell and presses Enter, Enter is an explicit save action.

The expected sequence is:

```text
Edit cell
    │
    ▼
Press Enter
    │
    ├── commit edited value
    ├── save that field to the audio file
    ├── synchronize application state with the saved value
    └── continue editing the same column in the next row
```

After a successful Enter-save:

* the edited value must be persisted;
* unrelated metadata must remain unchanged;
* the saved edit must not remain dirty;
* the saved edit must not cause a later Unsaved Changes prompt.

Merely entering, selecting, or navigating through table cells must not modify audio files.

### Metadata Panel

Edits in the metadata panel remain pending.

They are saved only when the user:

* clicks **Save Changes**; or
* chooses **Save** from an Unsaved Changes prompt.

Pressing Enter or changing focus in the metadata panel is not a save operation.

Do not merge these two editing models into one behavior.

## Metadata Architecture

Application code should use the common `Metadata` model rather than format-specific metadata identifiers.

Keep format-specific behavior inside the metadata layer.

The UI should not need to know ID3 frame names or MP4 atom names.

General dependency direction should remain:

```text
UI
 │
 ▼
application / editing logic
 │
 ▼
metadata interface
 │
 ▼
format-specific MP3 / M4B handlers
 │
 ▼
Mutagen / filesystem
```

Lower-level metadata modules must not depend on Qt UI classes.

## Metadata Safety

Metadata preservation is a primary requirement.

When changing a supported field, preserve unrelated metadata whenever technically possible.

Do not rewrite, normalize, remove, or replace unrelated tags merely because a file is being saved.

Preserve artwork unless the user explicitly changes or removes it.

Never use the user's production audiobook library as test data.

## Dirty State

Dirty state must represent a real unsaved metadata difference.

Do not treat a Qt editing signal by itself as proof that a file is dirty.

For metadata-panel editing, compare pending values with the loaded/saved state where appropriate.

If the user changes a value and then restores its original value, it should no longer be considered dirty.

A successfully saved center-panel Enter edit must not remain dirty.

Navigation alone must not create dirty state.

Prefer dirty-state logic that can be tested independently of Qt widgets.

## Multi-File Editing

Multi-file editing must modify only fields that the user explicitly chose to change.

Mixed values displayed in the metadata panel must not accidentally overwrite differing values in selected files.

Selecting multiple files is not itself an editing action.

## Testing

Use `pytest` for automated tests.

Use `pytest-qt` for Qt behavior where appropriate.

Before modifying behavior:

1. inspect existing relevant tests;
2. determine what behavior should be protected;
3. add or update tests when appropriate.

Bug fixes should normally include a regression test demonstrating the bug.

Prefer unit tests for ordinary Python logic.

Use integration tests for actual MP3/M4B metadata reading and writing.

Use UI tests only for behavior that genuinely requires Qt interaction.

Integration tests that write metadata must operate on temporary copies of test fixtures.

Never modify fixture masters in place.

Never test against files in the user's audiobook library.

## Local Development Media

* `dev-fixtures/` contains local/private media for manual development and testing only. Everything inside must remain untracked; never `git add`, commit, or push these files.
* Never remove the `dev-fixtures/` ignore rule from `.gitignore`.
* Automated tests must never depend on `dev-fixtures/`. Never reference specific files from it in reproducible test infrastructure or treat its filenames or contents as repository dependencies.
* Do not copy media from `dev-fixtures/` into tracked fixtures unless the user explicitly requests it and that file's provenance/licensing has first been established.
* Automated, version-controlled audio fixtures belong under `tests/fixtures/audio/`; the current source samples are `silence.mp3` and `silence.m4b`.
* Tests that modify automated fixture media must use temporary copies, never modify tracked master fixtures.

## Running Tests

Run the smallest relevant test set while developing.

Before considering a task complete, run the full automated test suite when practical:

```text
pytest
```

Report:

* which tests were added or changed;
* which test commands were run;
* whether they passed;
* any tests that could not be run and why.

Do not weaken or remove a failing test merely to make the suite pass unless the documented requirement has intentionally changed.

## Bug Fixes

When fixing a bug:

1. understand the existing behavior;
2. identify the underlying cause rather than only hiding the symptom;
3. create a regression test where practical;
4. make the smallest reasonable fix;
5. run relevant tests;
6. run the full test suite when practical;
7. summarize the cause and the change.

Avoid combining unrelated cleanup with a bug fix.

## Refactoring

Do not perform large architectural rewrites without explicit instruction.

Refactor incrementally when there is a concrete benefit such as:

* making behavior testable;
* fixing incorrect behavior;
* reducing meaningful duplication;
* improving metadata safety;
* supporting an agreed feature.

Working behavior should be protected by tests before significant refactoring.

## Dependencies

Do not add a new runtime dependency without explaining why it is needed.

Prefer the Python standard library, PySide6, Mutagen, and existing project dependencies when they are sufficient.

Development/test dependencies may be added when justified.

## Git

Do not create commits unless explicitly instructed to do so.

Do not push changes unless explicitly instructed to do so.

Do not rewrite Git history.

Do not modify unrelated files.

Keep changes small enough to review comfortably.

Before reporting completion, summarize the files changed and the purpose of each change.

## Documentation

If an implementation change intentionally changes documented behavior or architecture, identify the affected documentation.

Do not silently alter architectural decisions.

A change that contradicts an accepted ADR should be discussed before implementation.

## Current Development Stage

The project is under active development.

Favor correctness, metadata safety, clear behavior, and testability over premature abstraction.

The existing architecture should evolve incrementally rather than through a large rewrite.
