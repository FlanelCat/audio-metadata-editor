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
    ├── file_list.py
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

If the user restores all values to their original state, the file should become clean again.

Entering a field, leaving a field, pressing Enter, selecting another cell, or otherwise navigating the UI must not by itself create dirty state.

Dirty-state calculation should increasingly be expressed as ordinary testable application logic rather than being dependent on widget events.

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

Format-specific read/write failures originate in the metadata layer.

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
