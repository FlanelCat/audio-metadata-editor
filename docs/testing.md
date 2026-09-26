# Audio Metadata Editor — Testing Strategy

## 1. Purpose

Testing protects audiobook files from unintended metadata changes and helps ensure that application behavior remains consistent as the project develops.

Automated tests should focus particularly on metadata integrity, editing behavior, dirty-state tracking, and regression prevention.

Automated testing complements rather than replaces manual testing of the graphical user interface.

## 2. Testing Principles

Tests must be:

* repeatable;
* independent of the user's audiobook library;
* safe to run at any time;
* reasonably fast;
* deterministic where practical.

Tests must never modify production audiobook files.

Tests that write metadata must operate on temporary copies of dedicated test files.

## 3. Test Structure

Tests should be organized as:

```text
tests/
├── conftest.py
├── fixtures/
│   ├── README.md
│   └── audio/
│       ├── silence.mp3
│       └── silence.m4b
├── unit/
├── integration/
└── ui/
```

### `tests/unit/`

Tests ordinary Python logic independently of the GUI and filesystem where practical.

Examples:

* dirty-state calculation;
* metadata comparison;
* metadata normalization;
* field updates;
* validation;
* format-independent metadata models.

### `tests/integration/`

Tests interaction with real audio files and metadata formats.

Examples:

* reading MP3 metadata;
* writing MP3 metadata;
* reading M4B metadata;
* writing M4B metadata;
* preserving artwork;
* preserving unrelated metadata;
* preserving unsupported metadata where possible.

### `tests/ui/`

Tests important PySide6 behavior.

Examples:

* file selection;
* field editing;
* Enter-key navigation;
* dirty-state indicators;
* multi-file selection behavior;
* unsaved-change handling.

### `tests/fixtures/`

Contains fixture documentation and immutable generated audio samples in `tests/fixtures/audio/`. The shared `audio_fixture_dir` pytest fixture in `tests/conftest.py` centralizes their location. Tests select named samples (`silence.mp3` or `silence.m4b`) and copy them into `tmp_path` before use; generated images and modified audio stay in temporary directories. Unreferenced local media is not part of the automated fixture set and should not be added to version control without establishing its provenance and purpose.

Fixtures must not contain personal audiobook content.

Master fixtures must be treated as read-only.

Tests that modify metadata must first copy the fixture to a temporary location.

## 4. Test Framework

Pytest should be the primary test runner.

PySide6 GUI testing should use pytest-qt where appropriate.

Tests should use pytest facilities such as `tmp_path` for temporary files and directories.

## 5. Unit Testing

Core application behavior should be testable without starting the graphical interface whenever practical.

Important logic should not exist solely inside Qt signal handlers.

For example, determining whether metadata has changed should be implemented as testable application logic rather than being inferred from whether an editor emitted a signal.

Important dirty-state cases include:

* changing a value marks the file dirty;
* assigning the existing value does not mark the file dirty;
* restoring the original value clears dirty state;
* navigating through fields without changing them does not mark the file dirty.

## 6. Metadata Integration Testing

Metadata read/write operations should be tested against actual supported file formats.

At minimum, integration tests should cover MP3 and M4B.

A metadata write test should generally follow this pattern:

1. Copy a fixture into a pytest temporary directory.
2. Read its original metadata.
3. Perform the metadata operation.
4. Read the file again.
5. Verify the intended change.
6. Verify that unrelated metadata remains intact.

Particular attention should be given to preservation of:

* artwork;
* unsupported metadata;
* metadata fields unrelated to the edit.

## 7. UI Testing

UI tests should concentrate on behavior where interaction between Qt widgets and application state could cause regressions.

Not every visual behavior needs an automated test.

Important automated UI tests include:

* editing a field updates in-memory metadata;
* entering and leaving a center-panel field without modification does not create dirty state;
* pressing Enter after changing a center-panel metadata cell saves that field to disk;
* a successful center-panel Enter-save does not leave the file dirty;
* a successful center-panel Enter-save does not subsequently cause an Unsaved Changes prompt;
* pressing Enter continues editing in the same column of the next row when one exists;
* unrelated metadata is preserved during a center-panel field save;
* metadata-panel edits remain pending until explicitly saved;
* pressing Enter in the metadata panel does not itself write metadata to disk.
* changing a value marks the corresponding file as modified;
* restoring the original value clears the modified state;
* multi-file editing changes only explicitly selected fields.

## 8. Regression Tests

A bug fix should include a regression test whenever practical.

Ideally, the regression test should reproduce the incorrect behavior before the fix and pass after the fix.

For example, the center-panel Enter-save regression tests should verify both sides of the workflow: entering and leaving an unchanged field must not create dirty state, while changing a field and pressing Enter must persist that field and leave the successfully saved state clean.

Regression tests should remain in the test suite after the bug is fixed.

## 9. Manual Testing

Some behavior is more effectively tested manually.

Manual testing should be used for areas such as:

* overall editing workflow;
* keyboard navigation feel;
* layout and resizing;
* artwork appearance;
* dialogs;
* usability;
* behavior with real audiobook collections.

Manual testing should normally occur after automated tests pass.

## 10. Test Execution

During development, relevant tests may be run individually.

Before considering a code change complete, the complete automated test suite should be run.

The standard test command should eventually be:

```bash
pytest
```

The project should be configured so that running the test suite does not require access to the user's audiobook library.

## 11. Codex Requirements

When Codex changes application behavior, it should:

1. Read the relevant project requirements and architecture documentation.
2. Inspect existing tests before modifying code.
3. Add or update tests when behavior changes.
4. Add a regression test for a bug fix whenever practical.
5. Run relevant tests while developing the change.
6. Run the complete test suite before declaring the task complete.
7. Report which tests were added or changed.
8. Report the test commands executed and their results.

Codex must not weaken or remove a test merely to make a change pass unless the documented application requirements have intentionally changed.

Codex must never run tests against the user's production audiobook collection.

## 12. Metadata Safety

Metadata integrity is a high-priority testing concern.

A successful test must verify more than whether the requested field changed.

Where appropriate, tests should also verify that unrelated data was not unintentionally altered.

Opening, scanning, selecting, or navigating through files must remain non-destructive operations.

## 13. Testability as an Architectural Requirement

Application logic should be separated from GUI behavior where this improves testability.

Qt widgets should primarily handle presentation and user interaction.

Metadata operations, comparisons, dirty-state calculations, and other core behavior should be implemented so they can be exercised independently by unit tests where practical.

Difficulty testing a piece of core behavior should be treated as a possible indication that responsibilities need to be separated more clearly.

## 14. Auto-number Tracks Regression Coverage

`tests/ui/test_auto_number_tracks.py` exercises the toolbar and real dialog with temporary copies of both dedicated MP3 and M4B fixtures. Coverage includes single/multiple selection, default/custom starting numbers, visual row order under sorting, unselected files, positive-integer validation, Cancel, and no selection. Disk and UI assertions cover track-total preservation, unrelated/unknown tags, comments, artwork, saved-state synchronization, clean state, and pending panel edits. Injected write failures verify that earlier saves remain synchronized, the failed file is not marked saved, later files are untouched, and the error identifies the failed file.

Run focused tests, then the full suite and whitespace check:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/ui/test_auto_number_tracks.py tests/ui/test_table_editing.py tests/integration/test_field_isolation.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
git diff --check
```

## 15. File Table Column Sizing

`tests/ui/test_column_sizing.py` checks all columns against Qt header and cell size hints, including empty tables, growth and shrinkage, values beyond the default 1000-row sampling limit, metadata refreshes, and switching to an empty directory. File-loading tests use temporary fixture copies and verify that sizing does not modify audio files. Existing UI save tests also check sizing after Enter-save, metadata-panel Save Changes, and Auto-number Tracks.

## 16. Metadata-panel Save Preservation

`tests/ui/test_panel_preservation.py` uses temporary MP3/M4B fixture copies seeded with multi-valued artists, comments, custom fields, unknown tags, numeric pairs, and multiple covers. It verifies single-file and multi-file Title edits preserve unrelated raw metadata, pair components remain isolated, restored text fields are not rewritten, and explicit artwork replacement/removal remains distinct from unchanged artwork. Existing paste tests protect pending artwork preview and explicit-save behavior.

The initial preservation regression run reproduced 24 failures and 8 passes: both formats lost extra supported values and covers during Title-only saves, and clearing a number removed its untouched total. Tested unknown tags and unchanged numeric pairs already survived.

## Selection synchronization regressions

`tests/ui/test_selection_sync.py` uses temporary MP3/M4B fixture copies to cover guarded single/multi-selection transitions, Save/Discard/Cancel, failed prompt saves, clean transitions, repeated Enter-follow navigation, sorting, and unrelated pending panel edits during Enter-save. The initial regression run reproduced eight failures: six missing selection prompts and two stale-panel Enter advances. Existing table tests retain field-isolation/end-of-table assertions and now expect the panel to follow the active row after an accepted advance.

Desktop verification should include Ctrl/Shift multi-selection with different anchors, collapsing onto the original file, all three prompt choices, repeated Enter editing in sorted tables, and cancelling an advance with unrelated panel edits pending.

## Directory and empty-selection transitions

`tests/ui/test_directory_transitions.py` covers MP3/M4B clean and dirty directory changes, empty directories, populated lists without selection, root refresh, deselection, Save/Discard/Cancel, failed saves, Open Folder cancellation, artwork clearing, clipboard preservation and empty-selection signals. An isolated HEAD checkout reproduced 56 failures in the initial directory-transition tests: missing prompts and stale editing contexts. Additional coverage checks Ctrl-click deselection, refresh from a child directory, and standalone FileList reload signals. Loading an unselected list emits no selection notification; removing selected rows emits an empty list, and reloading an already unselected list emits none. Directory reloads suppress intermediate FileList selection signals after guarding the old context, then explicitly clear editing state. Standalone deselection emits an empty path list and uses the same guard.

## Direct multi-selection regressions

`tests/ui/test_initial_multi_selection.py` starts from an empty editing context and selects multiple temporary MP3/M4B fixture copies without first selecting a single file. Coverage includes close Save/Discard/Cancel and failed Save, actual window visibility, pending artwork removal (all/none/mixed artwork, repeated Remove, Undo/Discard/Save), selection/directory transitions, and MP3-only ID3v1 Comment availability and persistence. Availability tests also cover prior MP3/M4B single selections and mixed-format targets. The initial pre-fix run recorded 31 failures and 17 passes: nine close failures, 18 artwork-removal failures and four availability failures. Four further cases cover actual window close and MP3 comment persistence.

## Metadata read-error regressions

`tests/integration/test_read_errors.py` distinguishes valid untagged MP3/M4B media from missing, corrupt, inaccessible and parsing-failure inputs. Media operations use temporary fixture copies. `tests/ui/test_ui_read_errors.py` injects deterministic reader failures to cover initial and existing selection, pending panel/clipboard/artwork preservation, directory skip/reporting, failed Undo/Discard, optional indicator status, single/multi-panel post-write readback, partial progress and final common-display readback, actual Enter non-advance, Auto-number stop, and verification-only retry preserving later panel edits.

Before production changes, the initial 18 cases produced 16 failures and two passes (valid untagged files). The completed read-error coverage contains 48 cases. Tests distinguish a failed write from a successful disk write followed by failed verification; earlier writes are explicitly checked to remain on disk. Existing preservation, selection, directory, Paste, panel and Auto-number suites remain required regression coverage.
