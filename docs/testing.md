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

`tests/ui/test_effective_dirty.py` checks effective unresolved edits using temporary MP3/M4B copies: common multi-edit text, numeric and string-valued series-number restoration; mixed explicit values and blanks; independent field intent; and baseline synchronization after immediate saves and readback recovery. Invalid nonblank input in all four numeric fields remains pending with blank or populated baselines, retains validation messages/focus/selection, blocks failed Save, survives Cancel, and is removed by Discard or restoration. Selection, directory, Refresh and close guards are covered. Programmatic population remains clean. Absent-artwork Paste is a no-op on artwork-free targets, cancels pending additions, and removes covers only from targets with artwork.

Before production changes, these regressions recorded 58 failures and 44 passes: six common-restoration failures, 48 numeric pending/guard failures (including multi-file numeric restoration), and four absent-artwork Paste failures. A subsequent recovery regression reproduced two more failures: verification of an earlier immediate save overwrote new invalid numeric text. Verification now preserves that unresolved input. Four additional cases guard the new comparison baseline after partial panel saves: restoring the former value must remain pending when an earlier write succeeded or its readback is unresolved. Existing table, panel-preservation, Paste/artwork, selection, directory, Auto-number and read-error suites remain regression coverage.

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

`tests/ui/test_abandoned_table_edit.py` covers transient center-table edits on temporary MP3/M4B copies. Before the fix, the four Track/Title click-away regressions failed; the expanded transition run recorded 40 failures and 20 passes. Coverage includes returning to the original file, multi-selection, clearing selection, directory change, Refresh, close/reopen, another cell/editor, Escape, Tab, programmatic selection and pending-panel Save/Discard/Cancel. Additional cases cover every editable metadata column, sorted tables, restoring selection after a read error, and abandoning edits without additional reads. Ordinary Qt focus-loss commits must not change the accepted model value; existing Enter-save and readback-failure tests continue to protect explicit saving and navigation.

## Directory and empty-selection transitions

`tests/ui/test_directory_transitions.py` covers MP3/M4B clean and dirty directory changes, empty directories, populated lists without selection, root refresh, deselection, Save/Discard/Cancel, failed saves, Open Folder cancellation, artwork clearing, clipboard preservation and empty-selection signals. An isolated HEAD checkout reproduced 56 failures in the initial directory-transition tests: missing prompts and stale editing contexts. Additional coverage checks Ctrl-click deselection, refresh from a child directory, and standalone FileList reload signals. Loading an unselected list emits no selection notification; removing selected rows emits an empty list, and reloading an already unselected list emits none. Directory reloads suppress intermediate FileList selection signals after guarding the old context, then explicitly clear editing state. Standalone deselection emits an empty path list and uses the same guard.

## Direct multi-selection regressions

`tests/ui/test_initial_multi_selection.py` starts from an empty editing context and selects multiple temporary MP3/M4B fixture copies without first selecting a single file. Coverage includes close Save/Discard/Cancel and failed Save, actual window visibility, pending artwork removal (all/none/mixed artwork, repeated Remove, Undo/Discard/Save), selection/directory transitions, and MP3-only ID3v1 Comment availability and persistence. Availability tests also cover prior MP3/M4B single selections and mixed-format targets. The initial pre-fix run recorded 31 failures and 17 passes: nine close failures, 18 artwork-removal failures and four availability failures. Four further cases cover actual window close and MP3 comment persistence.

## Metadata read-error regressions

`tests/integration/test_read_errors.py` distinguishes valid untagged MP3/M4B media from missing, corrupt, inaccessible and parsing-failure inputs. Media operations use temporary fixture copies. `tests/ui/test_ui_read_errors.py` injects deterministic reader failures to cover initial and existing selection, pending panel/clipboard/artwork preservation, directory skip/reporting, failed Undo/Discard, optional indicator status, single/multi-panel post-write readback, partial progress and final common-display readback, actual Enter non-advance, Auto-number stop, and verification-only retry preserving later panel edits.

Before production changes, the initial 18 cases produced 16 failures and two passes (valid untagged files). The completed read-error coverage contains 48 cases. Tests distinguish a failed write from a successful disk write followed by failed verification; earlier writes are explicitly checked to remain on disk. Existing preservation, selection, directory, Paste, panel and Auto-number suites remain required regression coverage.

## Partial multi-file Save regressions

`tests/ui/test_partial_multi_save.py` instruments reads and writes on four temporary MP3/M4B copies. It covers failure on C before reading/writing, after writing, during readback, and during final common reads; exact selection-wide retry order; retained intent after unrelated edit/restoration, cached-value restoration and clearing; external divergence and unrelated-field preservation; newer pending values; multiple scalar fields and independent Track/Disc totals; same-cover/new-cover replacement; mixed/no-op artwork removal; and Discard/Cancel/Save navigation and close, including repeated failures. Successful Save and Discard restore ordinary effective-dirty comparisons. A further interaction regression ensures successful Auto-number still resolves only Track intent after its existing verification steps, preserving other unresolved fields. The initial pre-fix run recorded 14 failures and 70 passes (eight inapplicable parameter combinations were skipped and subsequently removed). Ten failures exposed lost scalar intent after final-read failure; four exposed disappearing unresolved artwork-removal markers.

`tests/ui/test_editor_identity.py` protects file/column identity across Enter commits that sort the edited row. Temporary MP3/M4B copies cover Title, Artist and numeric Track movement in both sort directions, first/last/middle positions, post-sort same-column advance, and Track edits sorted by Filename. Mouse-opened and automatic editors reject invalid numeric input without writing or advancing; correction and consecutive valid/blank saves retain each cell’s own accepted value. Sorting-specific panel Save/Discard/Cancel, writer failure, exact-file readback verification and programmatic synchronization are also covered. The initial pre-fix matrix recorded 36 failures and 20 passes. Panel-only Track Total, Disc and Disc Total retain their existing MetadataPanel/effective-dirty validation coverage; abandoned-editor tests protect non-Enter transitions.

`tests/ui/test_single_panel_uncertainty.py` uses temporary MP3/M4B copies to characterize single-panel writer-before-write, writer-after-write, readback and final presentation failures. The initial matrix recorded 156 failures and 102 passes before production changes. Regressions cover restoration to stale values, current-value retries, multiple fields, independent Track/Disc components, invalid numeric input, artwork replacement/removal/same-cover intent, failed/successful reloads, selection/directory/Refresh/close guards, real table Enter, overlapping verification-only state and Auto-number. The writer's internal tag-read failure is conservatively unresolved once invoked; MainWindow has no separate pre-write read for ordinary single-panel Save. Close Discard retains its existing no-reload exit behavior. Injected presentation exceptions still propagate, but cannot silently clear unresolved state before synchronization finishes.

`tests/unit/test_editing_rules.py` directly tests scalar comparison and effective multi-field intent with Metadata values and plain Python collections, without QApplication, qtbot, media, filesystem operations or dialog patches. Coverage includes all 19 scalar fields, independent numeric components, exact series-number strings, common/mixed/restored values, invalid-field flags, unresolved intent, missing baselines and input immutability. Run `.venv/bin/python -m pytest -q tests/unit/test_editing_rules.py`. Existing UI characterization tests remain unchanged and cover collection, signals, highlighting, dirty markers, persistence and all three uncertainty workflows.

`tests/ui/test_immediate_writer_failure.py` covers immediate writer-before-write, writer-after-write and different-value failures on temporary MP3/M4B copies. The corrected initial characterization recorded 32 failures and 6 passes against the pre-fix implementation. Tests exercise actual Enter non-advance, Auto-number stopping/progress, successful/failed recovery reads, read-only verification retry, Track Total preservation, pending panel values, overlapping single/multi-panel uncertainty, path isolation, initial read failures and guarded navigation. Writer failures remain reported even when recovery finds the requested value; no rollback or automatic replay occurs.

`tests/ui/test_existing_values.py` covers the 14 single-line text dropdowns, exact deduplication/order, Empty versus literal text, mixed/common intent, arbitrary typing, mouse/keyboard menu activation and non-committing navigation. Most cases use MetadataPanel or in-memory accepted metadata; MP3/M4B copies are used for explicit Save, guarded Save, partial-save retry, Refresh and directory integration. Tests also cover silent choice rebuilding, verification with pending edits, Cancel/Discard, stale-choice removal, applicability, layout width and unresolved cached equality. Existing numeric, artwork and uncertainty suites remain unchanged.

Per-file row-marker regressions in `test_existing_values.py` cover existing/missing/blank values, typed/dropdown equivalence, multiple-field unions and restoration, direct multi-selection, Cancel/Discard/new contexts, successful and uncertain saves, and artwork/immediate-verification unions. Marker assertions use file identity in a filename-sorted table, including clearing after Save. `test_editing_rules.py` directly covers per-target scalar comparisons and missing baselines without Qt.

`tests/ui/test_filename_sorting.py` covers ascending/descending filename stability through per-file dropdown/typed edits, Empty, multiple fields, Discard, Save, Refresh and all three uncertainty marker sources. It checks path/title identity and directly tests the filename comparator, including case folding, different parent directories and literal asterisks in filenames. Sorted-loading and Enter-editor identity suites remain required regression coverage.


## Filesystem navigator

`tests/ui/test_folder_navigator.py` adds 23 cases for no-root/root presentation, synthetic Books, direct-only MP3/M4B loading, filesystem identity, keyboard and mouse navigation, guarded Save/Discard/Cancel, invalid numeric input, all three uncertainty states, root switching/failure, isolated persistence across windows, missing/unreadable remembered roots, Open Folder and Refresh. Enumeration spies prove that root setup never scans children and expansion scans only the expanded directory. Additional cases cover hidden/symlink omission, arbitrary nesting and case-insensitive ordering, atomic partial-enumeration failure/retry, and directory disappearance between preflight and loading. Existing DirectoryTree tests now expect Books and rejection of an unreadable root.

The autouse `isolated_settings` fixture replaces the application settings factory with a distinct temporary INI file for every test. Tests never read or overwrite developer/user application settings. Mutable MP3/M4B test inputs remain copies of the tracked fixture masters.

Run navigator tests alongside directory transitions, selection synchronization, effective dirty, dropdowns, sorted loading, Filename sorting, Enter-editor identity, immediate writer failure and single/multi uncertainty suites, then the full offscreen suite and `git diff --check`.

Manual checks: choose a real root and inspect its basename/full path; expand/collapse nested book/edition folders; select an edition and verify direct audio files; select its parent and verify no recursive aggregation; cancel navigation with pending edits and verify the old node is restored; save and navigate; restart and verify remembered-root restoration; temporarily make the root unavailable and verify no-root presentation without forgetting it; confirm Open Folder still opens an arbitrary directory without changing the remembered root.

Refresh-context regressions in `test_folder_navigator.py` cover root/book/edition contexts, stable tree item identity and expansion without navigation emissions, external Open Folder locations and unchanged root settings, added/removed audio files and external metadata changes, nested Save/Discard/Cancel, invalid numeric input and missing-directory failure without root fallback. The directory-transition child Refresh tests now require staying in the accepted child directory for both Discard and Cancel. Existing uncertainty suites retain their Refresh guards.

### Generate Text regressions

`tests/unit/test_text_template.py` tests every variable, literal/repeated text, brace escaping, numeric padding/minimum width/100-character limit, exact-name validation, missing numeric values, empty text and rejection of unsupported formatting or expressions without Qt widgets or media. Run `.venv/bin/python -m pytest -q tests/unit/test_text_template.py` first.

`tests/ui/test_generate_text.py` tests target choices, live preview/error gating, Cancel, visual-order indexing, atomic Apply, per-file markers and table/panel presentation, single/multi generation, regeneration, field-specific precedence, accepted template sources, stable sorting/save path order, and navigation/Refresh/close guards. Temporary MP3/M4B copies verify independent Title/Series/Artist persistence, unrelated fields and artwork preservation, before/after-write failures, readback/final-read failures, changed-value retry, uncertainty transfers, failed/successful Discard and immediate-write verification overlap. No fixture master or real application settings are used.

Run these with editing rules, initial multi-selection, dropdowns, effective dirty, panel uncertainty, immediate writer failures, Auto-number, Paste, directory transitions, FolderNavigator/Refresh, sorted loading, Filename sorting and Enter identity, then the full offscreen suite and `git diff --check`.

`tests/ui/test_generate_text_settings.py` uses the existing per-test isolated QSettings store to cover first-use defaults, successful Apply persistence, same-window reopening, restoration through a new MainWindow/settings instance, Cancel and invalid Apply protection, stale-target fallback, invalid stored-template preview and preservation of an explicitly empty template. Existing Generate Text tests retain pending/save behavior coverage.


### Copy Down / Copy Up regressions

`tests/unit/test_editing_rules.py` tests pure visual-order target selection, discontinuous selections, both directions, absent sources and no targets. `tests/ui/test_copy_cells.py` uses temporary MP3/M4B copies for actions/shortcuts, middle sources, effective/repeated copying, clean matching targets, common/mixed presentation, unsupported columns, transient editors, ascending/descending metadata sorting and stable paths. It covers Generate/common-edit precedence, retained unrelated fields, Save and artwork/pair preservation, writer/readback failures and retry, uncertainty transfer, failed/successful Discard, navigation/Refresh/close Cancel and subsequent immediate Enter-save.

Run Copy tests with Generate Text and remembered settings, editing rules, dirty/uncertainty, table Enter/identity, sorted loading/Filename sorting, FolderNavigator, directory transitions, Auto-number and Paste regressions, followed by the full offscreen suite and `git diff --check`. Generate tests use the shared neutral `_per_file_edits` / `_unresolved_per_file_fields` state names.


### MP3 version preservation

`tests/integration/test_mp3_versions.py` uses temporary copies of the public silence fixture and explicitly creates v2.3/v2.4 tags. Title-only writes compare all unrelated parsed frames, including v2.3 TSIZ and legacy date components, scalar/custom multi-value text, comments, artwork and both number/total pairs. Additional cases protect version-aware date replacement/clearing, full-write behavior, other filtered fields and explicit artwork. The initial regression reproduced v2.3 becoming v2.4 with TSIZ removed (4 failures, 4 passes before the writer fix). These tests assert supported semantic preservation, not arbitrary unknown raw-frame survival. Run with existing field-isolation, panel preservation, Enter, Auto-number, Paste, Generate Text and Copy suites, then the full offscreen suite.


### Date safety regressions

`tests/unit/test_date.py` covers grammar, whitespace, calendar/time validity, format precision and readback equivalence without Qt/Mutagen. `tests/integration/test_date_writes.py` exercises actual v2.3/v2.4/M4B roundtrips, blank removal, invalid full/filtered writes preserving all bytes, midnight/zero-minute legacy conversion and unrelated-field isolation. `tests/ui/test_date_save.py` covers real single/multi/generated/pasted saves, batch preflight, normalization, simulated per-file/final-read mismatches and retry, pending retention/focus, and selection/Refresh/close Save/Discard/Cancel. The initial six real-save regressions failed before production changes, including the audited false-success MP3 behavior. Existing B1, panel uncertainty, Generate, Copy and Paste tests remain required coverage. No Date table/Copy feature is added.


### Untagged MP3 writes

`tests/integration/test_untagged_mp3.py` removes ID3 from temporary public fixture copies, verifies empty reads are non-mutating, and exercises isolated fields, artwork, full writes, empty/removal no-ops, Date rejection, corrupt/disguised inputs and save failure. New tags are v2.4; MPEG properties and the complete original payload after the new header remain unchanged. The initial Title regression failed with ID3NoHeaderError before the fix. `tests/ui/test_untagged_save.py` covers selection, panel/Enter/artwork/generated/Date saves, invalid Date pending state, and write-then-raise/readback failure with retry. The former B1 test asserting untagged writes were unsupported was replaced by this explicit feature coverage; B1/B2 regressions remain required.


### MP3 Comment identities

`tests/integration/test_mp3_comments.py` reproduces described-comment resurrection and covers canonical change/clear, uneditable described/non-English values, reversed frame ordering, language selection, bidirectional ID3v1 Comment isolation, v2.3/v2.4, legacy TSIZ, artwork, pairs, custom TXXX and untagged creation. The initial eight cases failed before production changes. `tests/ui/test_comment_save.py` covers single/multi panel change/clear for both fields and readback-failure retry. Field-isolation/full-write expectations now protect non-English ordinary frames rather than treating them as requested edits. No raw unknown-frame preservation guarantee is added.


`tests/ui/test_artwork_read_errors.py` covers disappearance after selection, permission errors on open, I/O errors during read, and chooser cancellation. Single/multi selections with accepted artwork, pending replacement or pending removal retain their complete editing state, preview and disk bytes; writer spies verify no metadata writes. Existing Paste/artwork and panel-preservation tests retain successful selection and explicit-save coverage.


### Simulated keyboard modifiers

The Ctrl-click deselection test in `test_directory_transitions.py` uses an explicit Control key press and a `finally` key release around the modified mouse click. Supplying ControlModifier to QTest.mouseClick alone left Qt's global keyboard state reporting Ctrl held, causing ten subsequent sorted-loading selection cases to extend selection. Keep modifier gestures balanced even when an interaction/assertion raises; do not mask state by patching keyboardModifiers or changing production behavior. Two regression cases verify normal/exception cleanup and selection replacement in a subsequent independent widget. Run directory transitions followed by sorted loading, also in reverse order, alongside selection/editor/navigation tests.
