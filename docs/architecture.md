# Audio Metadata Editor — Architecture

## 1. Purpose

This document describes the architecture of Audio Metadata Editor and the intended boundaries between its major components.

The architecture should support:

* safe metadata editing;
* explicit control over writes to disk;
* MP3 and M4B support through a common metadata representation;
* automated testing of core behavior without requiring the GUI;
* future support for additional metadata fields and audio formats;
* incremental development without unnecessary large-scale refactoring.

The architecture described here reflects both the current implementation and the intended direction of the project.

## 2. High-Level Architecture

The application is divided conceptually into four areas:

```text
┌──────────────────────────────────────┐
│                 UI                   │
│                                      │
│ MainWindow            FileList       │
│ Qt widgets            table editing  │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│        Application / Editing State   │
│                                      │
│ current file                         │
│ loaded metadata                      │
│ pending edits                        │
│ selection state                      │
│ dirty state                          │
│ multi-file edit state                │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│          Metadata Interface          │
│                                      │
│ Metadata model                       │
│ reader                               │
│ writer                               │
└──────────────────┬───────────────────┘
                   │
             ┌─────┴─────┐
             ▼           ▼
┌────────────────┐ ┌────────────────┐
│      MP3       │ │      M4B       │
│ ID3 / Mutagen  │ │ MP4 / Mutagen  │
└───────┬────────┘ └────────┬───────┘
        │                   │
        └─────────┬─────────┘
                  ▼
             Audio files
```

The current implementation does not yet contain a separate application-state module. Much of that responsibility currently resides in `MainWindow`.

This should be improved incrementally when doing so simplifies behavior or testing. A large rewrite solely to introduce architectural layers is not required.

## 3. Source Layout

The current primary source structure is:

```text
src/audio_metadata_editor/
├── __init__.py
├── main.py
├── metadata/
│   ├── __init__.py
│   ├── model.py
│   ├── reader.py
│   ├── writer.py
│   ├── mp3.py
│   └── m4b.py
└── ui/
    ├── __init__.py
    ├── directory_tree.py
    ├── file_list.py
    ├── metadata_panel.py
    └── main_window.py
```

The `metadata` package owns metadata representation and format-specific translation.

The `ui` package owns graphical presentation and user interaction.

## 4. Metadata Model

`metadata/model.py` defines the format-independent `Metadata` model.

The rest of the application should work with logical fields such as:

* title;
* artist;
* album;
* album artist;
* genre;
* track and disc information;
* narrator;
* series;
* publisher;
* comments;
* description;
* artwork.

The UI should not need to know whether a field is represented internally as an ID3 frame, an MP4 atom, or another format-specific structure.

The metadata model forms the boundary between general application behavior and format-specific metadata handling.

## 5. Metadata Reading

`metadata/reader.py` provides the general metadata-reading entry point.

It determines the appropriate format handler based on the audio file type and delegates parsing to the corresponding implementation.

Currently:

```text
read_metadata()
      │
      ├── .mp3 ──► read_mp3_metadata()
      │
      └── .m4b ──► read_m4b_metadata()
```

Format-specific parsing must remain outside the UI.

Adding another supported audio format should normally require extending metadata handling rather than teaching UI widgets about the new format.

## 6. Metadata Writing

`metadata/writer.py` provides the general metadata-writing entry point.

Format-specific writers are responsible for translating the common `Metadata` representation back into the appropriate file metadata format.

Metadata writers must prioritize preservation.

Changing one supported field must not unnecessarily destroy unrelated or unsupported metadata.

Artwork must remain unchanged unless an artwork modification is explicitly requested.

Disk writes are considered destructive operations compared with normal browsing and editing and therefore must occur only following an explicit user action.

## 7. MP3 Metadata

`metadata/mp3.py` owns ID3-specific behavior.

It is responsible for translating between ID3 frames and the common `Metadata` model.

Examples include:

```text
TIT2       → title
TPE1       → artist
TALB       → album
TPE2       → album artist
TCON       → genre
TRCK       → track
TPOS       → disc
TXXX       → application-supported custom fields
APIC       → artwork
```

ID3-specific frame names and behavior should not leak into general UI code.

The writer should preserve unrelated ID3 frames whenever technically possible.

## 8. M4B Metadata

`metadata/m4b.py` owns MP4/M4B-specific metadata behavior.

It translates MP4 atoms and freeform metadata into the same common `Metadata` representation used for MP3 files.

MP4-specific atom names and Mutagen behavior should remain isolated inside the metadata layer.

The rest of the application should not need separate MP3 and M4B editing workflows.

## 9. Main Window

`ui/main_window.py` currently acts as the application's main coordinator.

Its current responsibilities include:

* constructing the main interface;
* directory navigation;
* coordinating file selection;
* displaying metadata;
* collecting edited metadata;
* managing artwork changes;
* managing multi-file editing;
* validation;
* copy/paste operations;
* detecting unsaved changes;
* coordinating metadata writes;
* handling unsaved-change dialogs.

This concentration of responsibilities is acceptable during the current stage of development, but new non-visual application logic should not automatically be added to `MainWindow`.

Logic that can be expressed independently of Qt widgets should preferably move toward testable application/model components as the project evolves.

Refactoring should be incremental and driven by concrete requirements or testing benefits.

`ui/dialogs/paste_fields_dialog.py` owns only the supplied field checkboxes and selection controls. `MainWindow` retains remembered choices, clipboard data, pending metadata/artwork application, previews, and saving. Rejection is distinct from accepting an empty selection.

`ui/metadata_panel.py` constructs the editing controls and provides `set_metadata`, `collect_metadata`, `clear_metadata`, and partial `set_field_values` presentation methods. These methods cover editor values only: population suppresses widget signals, numeric collection preserves the existing blank/invalid-to-None conversion, and series numbers remain strings. MainWindow supplies common/mixed decisions and attaches pending artwork to collected metadata. MetadataPanel also forwards editor signals and renders supplied field highlights; MainWindow owns edit intent, dirty-state decisions, and status counts. MetadataPanel exposes raw numeric text and owns invalid-field focus/selection and ID3v1 Comment editor enablement. MainWindow retains numeric validation rules and warnings, decides field availability, and owns artwork rendering/intent, editing state, saved baselines, coordination, and persistence. Control attributes remain available for those responsibilities and existing integration tests. This is an incremental presentation extraction, not editing-state ownership. Save Changes remains in the toolbar.

`ui/existing_values_edit.py` preserves QLineEdit editing and adds a trailing-button/Alt+Down menu for accepted multi-file values. Only action activation emits the existing text-edit signals; menu navigation is presentation-only. MetadataPanel's `set_existing_values(baselines)` silently builds choices from ordered scalar baseline mappings without owning intent or persistence. MainWindow supplies its accepted multi-file baselines after context acceptance and readback/recovery; rebuilding choices does not replace pending editor text. Single-file population clears the choices. Description remains multiline, and numeric/artwork controls are unchanged.

`ui/folder_navigator.py` composes the root heading, full path, Choose Root button and DirectoryTree. It emits root-choice intent and contains no metadata or save policy. `ui/directory_tree.py` presents a synthetic Books root and lazy directory nodes, omitting hidden and symlinked child directories. It installs children only after a complete successful enumeration, with unconditional placeholders avoiding child-directory probing. Clicks and keyboard navigation emit `directory_requested(path)`; accepted selection and restoration are silent. Expansion errors emit a status message and retain a retryable unloaded node.

MainWindow owns root choice, the existing transition guard, FileList loading and accepted `current_directory`, distinct from the navigator's `root_path`. A root is installed only after accepted directory loading. Open Folder navigates without changing the persistent root; an undisplayed destination clears tree selection. Refresh passes only the accepted `current_directory` to the existing guarded directory loader. It does not rebuild the tree or modify the configured root/settings; selection restoration is silent and expansion state is preserved. FileList enumerates before replacing rows and preserves its old model on directory enumeration failure; MainWindow also preflights before the guard. Metadata reads still occur after any explicit Save/Discard.

`settings.py` creates QSettings with organization/application identifiers `AudioMetadataEditor` / `AudioMetadataEditor`, using Qt's platform-native user settings storage. `navigator/rootPath` is written after an accepted Choose Root. MainWindow also reads `generateText/lastField` and `generateText/lastTemplate` when opening Generate Text and writes them only after successful Apply installs pending edits. The dialog accepts initial values, validates target support and renders normal preview without owning settings. Startup restoration never deletes an unavailable remembered path or substitutes a fallback. Tests replace this factory with a per-test temporary INI store, including tests that construct MainWindow indirectly. There is no database, filesystem index or metadata cache.

`editing_rules.py` contains stateless scalar decisions: `changed_scalar_fields(accepted, edited)` compares the immutable scalar catalogue exactly, and `effective_multi_fields(intended_fields, edited, baselines, *, invalid_fields, unresolved_fields)` retains effective intent without mutating inputs. MainWindow collects values and invalid logical field names, supplies accepted baselines and unresolved scalar names, then updates its state and presentation. Artwork stays separate. Single-panel uncertainty is explicitly unioned with ordinary changed fields by MainWindow; all three uncertainty lifecycles, persistence, readback, navigation and dialogs remain there. The pure module has no Qt or filesystem operations. `effective_fields_for_target(intended_fields, edited, baseline)` compares one accepted scalar baseline for row presentation, conservatively retaining missing values. MainWindow unions this with artwork applicability and existing uncertainty/invalid-input markers; selection-wide intent and persistence policy remain independent.

MainWindow keeps `_unresolved_single_fields` for the current single-file panel context: logical scalar names plus optional `artwork`. Ordinary pending state compares panel values with the accepted baseline; this separate set records attempted persistence whose acceptance remains unresolved. It is established immediately before the writer, survives writer/readback failures and cached-value restoration, and extends the next panel write's field set using current panel values. It clears after verified Save and synchronization, successful Discard/reload, or guarded context replacement. A verified explicit immediate field save resolves only that field. `_unverified_fields` remains distinct: it retries immediate-write verification without rewriting; verification must preserve overlapping unresolved panel values. Neither state is a persistent metadata store.

MainWindow keeps `_unresolved_multi_fields`, a set of logical scalar fields and optionally `artwork`, for multi-panel Save uncertainty. After validation and before the first preservation read, the current save intent is added to this set. Cached comparisons cannot remove these fields from pending intent; current panel values still determine what the next Save applies selection-wide. The set survives pre-write reads failing, writer exceptions, per-file readback failures and final common/mixed read failures. It clears after a complete Save including final reads, or a successful Discard reload; accepting a new editing context resets it after the existing guard. Failed reload and Cancel preserve it. Successful Auto-number retains its existing Track-intent reset: only after all immediate writes/readbacks and the final common-track read succeed does it also resolve `track_number` in this set; other unresolved fields remain. Unresolved selections remain visibly dirty. This is distinct from `_unverified_fields`, which supports verification-only retry of immediate field saves; it contains no completed-file list or value snapshot and does not change Enter-save or Auto-number policy.

## 10. File List

`ui/file_list.py` owns the central file table and its direct interaction behavior.

Its responsibilities include:

* displaying files;
* displaying selected metadata columns;
* sorting;
* row selection;
* table-cell editing;
* keyboard navigation within the table;
* communicating edits and selection changes through Qt signals;
* displaying dirty-file indicators.

`FileList` should communicate editing and save intent to the application through signals. Pressing Enter after editing a metadata cell represents an explicit request to save that field. FileList should not itself implement MP3 or M4B persistence; the application handles the save request through the metadata layer.

In particular, keyboard navigation and committing an editor value are conceptually separate from writing metadata to disk.

`FilenameTableWidgetItem` stores the full path and undecorated basename separately from visible status text. Its comparator uses the case-folded basename; metadata columns retain `SortableTableWidgetItem` comparison behavior. Directory loading still constructs complete rows with sorting disabled before restoring the previous sort state.

## 11. Editing Model

The application provides two deliberately different metadata-editing workflows.

### 11.1 Center-Panel Table Editing

The center file table is designed for fast field-by-field editing across multiple files.

Editing a table cell creates a temporary editor for that cell.

Pressing Enter explicitly confirms and saves that field.

Conceptually:

```text
audio file
    │
    ▼
center-panel cell
    │
    │ user edits value
    ▼
temporary edited value
    │
    │ Enter
    ▼
commit cell value
    │
    ├── write the edited field to the audio file
    │
    └── move to the same field in the next row
```

For center-panel editing, **pressing Enter is an explicit save action**.

After a successful Enter-save:

* the edited field must be written to the corresponding audio file;
* the application's loaded/current metadata state must reflect the saved value;
* the center-panel display must reflect the saved value;
* the file must not remain dirty solely because of the value that was just saved;
* moving to another file must not produce an unsaved-changes warning for the successfully saved center-panel edit.

Center-panel Enter-save should modify only the field being edited. Other metadata must be preserved.

### 11.2 Metadata-Panel Editing

The metadata panel uses a pending-edit workflow.

Changes made in the metadata panel remain in memory until explicitly saved.

Conceptually:

```text
audio file
    │
    │ read
    ▼
loaded metadata
    │
    │ edit metadata panel
    ▼
pending metadata
    │
    ├── Save Changes
    │       │
    │       ▼
    │   audio file
    │
    └── switch/close
            │
            ▼
      Unsaved Changes prompt
```

Metadata-panel changes may be saved through:

* the **Save Changes** button; or
* choosing **Save** when presented with an Unsaved Changes prompt.

They may also be discarded or cancelled through the Unsaved Changes workflow where applicable.

Editing a metadata-panel field or pressing Enter while editing a metadata-panel field does not itself write metadata to disk.

### 11.3 Separation of the Two Workflows

The two workflows must remain distinct.

| Action                      | Center-panel table                   | Metadata panel                  |
| --------------------------- | ------------------------------------ | ------------------------------- |
| Edit field                  | Temporary cell edit                  | Pending metadata change         |
| Press Enter                 | **Save edited field**                | Does not save metadata          |
| Save Changes button         | Not required for an Enter-saved cell | **Save pending changes**        |
| Dirty after successful save | No                                   | No                              |
| Unsaved Changes prompt      | Only for genuinely pending changes   | Yes, when pending changes exist |

Both workflows ultimately use the same metadata-reading and metadata-writing infrastructure, but their user interaction and save semantics are intentionally different.


### 11.4 Auto-number Tracks

`ui/dialogs/auto_number_dialog.py` owns only starting-number presentation and validation. `MainWindow` invokes the dialog and retains selection, sequencing, persistence, state synchronization, and notifications.

The toolbar action snapshots selected file paths in visual table row order. Dialog OK explicitly saves consecutive track numbers through the same single-field save helper as table Enter-save. The common writer forwards the requested field set to the format-specific writer. Sorting is temporarily suspended during row updates. Each successful save refreshes disk-backed table data and the affected panel baseline while preserving unrelated pending edits. Processing stops on the first failure without rolling back previous saves. This extends the explicit-save model without changing either existing editing workflow.

## 12. Dirty State

Dirty state represents an actual difference between pending metadata and the saved/loaded state.

It must not merely represent that an editor emitted a Qt signal.

For a single file:

```text
pending metadata != loaded metadata
                │
                ▼
              dirty
```

If the user restores all values to their accepted state, the file should become clean again, provided no persistence uncertainty remains.

Entering a field, leaving a field, pressing Enter, selecting another cell, or otherwise navigating the UI must not by itself create dirty state.

Scalar comparison and effective multi-field intent are directly testable application rules; MainWindow combines their results with raw-input validation, artwork and persistence uncertainty.

## 13. Multi-File Editing

Multi-file editing differs from single-file editing.

When multiple files are selected, fields may contain different original values.

The application therefore tracks which fields the user explicitly intends to apply to all selected files.

Only those fields should be written.

Conceptually:

```text
selected files
     │
     ▼
common/mixed metadata display
     │
     │ user explicitly edits field
     ▼
field marked for multi-edit
     │
     │ explicit Save
     ▼
apply that field to selected files
```

Selecting multiple files alone must never modify metadata.

## 14. Artwork

Artwork is part of the metadata model but requires special handling because it contains binary data and because preserving existing artwork is important.

Reading a file may populate:

* artwork bytes;
* artwork MIME type.

Choosing or removing artwork changes pending state only.

Artwork must not be changed on disk until an explicit save.

When unrelated metadata is edited, existing artwork must be preserved.

## 15. UI and Persistence Boundary

Metadata writes must occur only as the result of an explicit save action.

The application has two editing workflows with different definitions of an explicit save action.

### Center-Panel Table

The center-panel table is intended for fast field-by-field editing.

When a user edits a metadata cell and presses **Enter**, pressing Enter is considered an explicit save action.

The application must:

1. commit the edited cell value;
2. write that field to the corresponding audio file;
3. preserve all unrelated metadata;
4. update the application's in-memory state to reflect the newly saved value;
5. clear any dirty state caused by that edit; and
6. move editing to the same column in the next row, when one exists.

After a successful Enter-save, the saved edit must not cause an Unsaved Changes prompt.

Merely entering a cell, leaving a cell without an actual change, selecting another cell, or navigating the table without confirming an edit with Enter must not write metadata to disk.

### Metadata Panel

Edits made in the metadata panel are pending changes and must not be written to disk merely because a field loses focus, Enter is pressed, or the user navigates elsewhere.

Metadata-panel changes are written only when the user explicitly chooses to save them through:

* the **Save Changes** button; or
* **Save** in an Unsaved Changes prompt.

Until one of these save actions occurs, metadata-panel changes remain pending and must be represented as unsaved changes.

### Architectural Rule

The distinction is therefore:

```text
Center-panel cell:
    Edit → Enter → Save field to disk

Metadata panel:
    Edit → Pending change
              │
              ├── Save Changes → Save to disk
              │
              └── Unsaved Changes → Save → Save to disk
```

Both workflows use the same metadata layer for persistence. The UI determines when the user has requested a save; format-specific MP3 and M4B writing remains the responsibility of the metadata layer.


## 16. Validation

Input validation should occur before metadata is written.

Invalid user input must not silently become another value.

Validation rules that do not depend on Qt should preferably be implemented in testable non-UI logic as the project evolves.

The UI remains responsible for presenting validation errors and returning focus to the appropriate control.

## 17. Error Handling

Format-specific read/write failures originate in the metadata layer. Readers raise `MetadataReadError` with the affected path and chained underlying cause; valid empty metadata remains a `Metadata` value. MP3 distinguishes a missing ID3 header from invalid audio by checking the MPEG container before accepting an untagged file. M4B accepts absent tags only after successfully opening the container. Writers are unchanged.

FileList returns skipped-file read errors to MainWindow for directory-scan reporting. MainWindow stages required reads before replacing presentation/state and reports post-write verification failures separately from successful completion. Its transient `_unverified_fields` map records immediate-save fields awaiting readback, without becoming a metadata cache or changing either explicit-save workflow. Immediate writer invocation establishes this state before writing. Writer exceptions trigger verification restricted to the affected path; successful recovery accepts disk truth using the existing panel-intent protections, while failed recovery retains uncertainty. Recovery returns verified metadata for outcome reporting, but the writer exception still stops Enter navigation and Auto-number. Panel retry states remain separate.

The UI is responsible for presenting useful errors to the user.

The metadata layer should not display Qt dialogs.

The UI should not need to understand Mutagen internals in order to report that an operation failed.

## 18. Testing Boundary

The architecture should support the testing strategy defined in `docs/testing.md`.

In particular:

```text
metadata/model
metadata comparison
dirty-state logic
validation
        │
        ▼
   unit tests

MP3/M4B read/write
metadata preservation
artwork preservation
        │
        ▼
 integration tests

selection
editing
Enter navigation
dirty indicators
        │
        ▼
    UI tests
```

Core application behavior should not require a running Qt interface merely to be tested.

## 19. Dependency Direction

Dependencies should generally flow downward:

```text
UI
 │
 ▼
application/model logic
 │
 ▼
metadata interface
 │
 ▼
format-specific handlers
 │
 ▼
Mutagen / filesystem
```

Lower layers should not depend on UI classes.

In particular:

* metadata modules must not import `MainWindow` or `FileList`;
* format handlers must not display dialogs;
* the metadata model must not depend on Qt;
* UI code may use the metadata model and metadata services.

## 20. Incremental Refactoring

The project should not be rewritten merely to achieve an idealized architecture.

Architectural improvements should be incremental.

A refactor should normally have at least one concrete benefit, such as:

* fixing incorrect behavior;
* improving metadata safety;
* making important behavior testable;
* reducing duplicated logic;
* making a new feature substantially easier to implement.

Existing working behavior should be protected with tests before significant refactoring.

## 21. Current Architectural Priorities

The current implementation already has a useful separation between:

* common metadata representation;
* MP3 handling;
* M4B handling;
* UI components.

The next architectural improvements should focus on:

1. establishing automated tests around existing metadata behavior;
2. separating table editing/navigation from disk persistence;
3. making dirty-state behavior independently testable;
4. reducing application-state responsibilities in `MainWindow` when concrete changes provide an opportunity;
5. keeping MP3/M4B implementation details isolated from UI code.

These improvements should be made through small reviewed changes rather than a large rewrite.

### Per-file scalar intent

`text_template.py` provides pure `parse_template(text)` and `evaluate_template(tokens, context)` functions and `TemplateError`. It parses only the documented variable/escape/padding grammar over explicit scalar mappings, with no Qt, evaluation of expressions, arbitrary object formatting or filesystem operations. `GenerateTextDialog` snapshots ordered path/context pairs, renders live all-target preview, and exposes a validated field/value mapping after Apply. MainWindow builds contexts from accepted baselines; unverified/unresolved values are unavailable as template sources. No writer is involved in preview or Apply.

MainWindow owns two narrow additions: `_per_file_edits: dict[Path, dict[str, str]]` contains current per-file intent, including matching values; `_unresolved_per_file_fields: dict[Path, set[str]]` protects per-file fields whose writes were attempted without completing the whole panel Save. Ordinary single-panel values and common `multi_edit_fields` remain separate. Per-file fields never masquerade as differing values in common intent. Generation transfers superseded common/single uncertainty to the per-target set; a later explicit common edit transfers affected per-file uncertainty to the appropriate existing common/single model. This preserves protection even when the later value equals a stale baseline.

The existing Save loop merges common fields with each path's effective/unresolved per-file fields, records per-file uncertainty before invoking its writer, and updates accepted baselines from readback only. Successful earlier per-file writes remain protected through a later failure/final-read failure so retry can apply newer intent to those targets too. Complete Save or successful Discard clears per-file state. `_unverified_fields` retains its verification-only lifecycle and preserves overlapping per-file intent during reconciliation; successful explicit Enter supersedes only the corresponding per-file field. `_unresolved_single_fields` and `_unresolved_multi_fields` retain their existing ordinary panel responsibilities and artwork behavior.

`FileList.show_pending_fields` overlays supported table columns by stable file path, blocking edit signals and preserving normal sorting. These visible values do not replace accepted baselines. FileList also renders escaped filename tooltips listing per-file fields, including panel-only targets, and clears them when intent is cleared. MetadataPanel receives silent partial common/mixed presentation of per-file fields, preserving unrelated panel inputs. Apply order/index uses the dialog's visual selected-path snapshot; persistence retains the accepted `selected_files` path order. No session/controller, transaction framework, history, index or persistent metadata store was introduced.

Copy Down/Up and Generate Text share `_per_file_edits` and `_unresolved_per_file_fields`, through `_apply_per_file_values`; there is no separate Copy persistence path. FileList snapshots the active model value and visual path order, uses the pure `copy_target_paths` rule, and emits field/path/value intent. An active transient editor is closed without committing. A subset override of common panel intent materializes the non-target values and any uncertainty into per-file state before replacing target values. FileList owns table actions/shortcuts and the shared `TABLE_FIELDS` mapping; Copy excludes its numeric Track column.


### MP3 version-aware writes

The MP3 writer loads with `ID3(..., translate=False)` to avoid default v2.4 translation discarding v2.3-only frames. It retains existing v2.3/v2.4, uses the corresponding Mutagen conversion API and saves with an explicit `v2_version`. The v2.3 conversion runs after logical edits; explicitly requested Date changes first remove TYER/TDAT/TIME so old components cannot override the replacement TDRC. Unrequested legacy dates remain intact. `v23_sep=None` retains existing multi-value text. Both filtered and full writes share this policy without changing field/artwork selection or tag creation. Mutagen retains some raw unknown frames only when their stored version matches the output version; the project does not promise arbitrary unknown-frame or byte-for-byte preservation. See [Mutagen's ID3 version documentation](https://mutagen.readthedocs.io/en/latest/user/id3.html).


### Date validation and verification

`metadata/date.py` owns pure `normalize_date` and `verify_date` rules, independent of Qt and Mutagen. Both format writers validate intended Date values before modifying/saving tags; MP3 applies the existing-version precision restriction. MainWindow preflights the entire pending Date mapping through `validate_date_for_file`, so a later invalid target prevents earlier writes. MetadataPanel owns Date focus/selection. Per-file and final batch readbacks are checked before accepting/clearing intent; mismatches use the existing single/common/per-file uncertainty paths. Immediate verification-only state is unchanged because Date has no immediate table operation. Legacy v2.3 TIME uses HHMM; explicitly supplied zero hour/minute components are retained despite Mutagen conversion omitting them, and readback's added :00 seconds are treated as equivalent. B1 version preservation and unrelated legacy date components remain unchanged.
