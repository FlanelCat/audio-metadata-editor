# Audio Metadata Editor — Requirements

## 1. Purpose

Audio Metadata Editor is a desktop application for viewing and editing metadata in audiobook files.

The application is intended to provide a workflow similar to tools such as Mp3tag and Metadatics while being designed specifically around the requirements of an audiobook library.

The application does not maintain its own media database. The audio files and their embedded metadata are the source of truth. Plex is used separately for library management.

## 2. Supported Platforms

The primary development and target platform is Linux.

The application is written in Python and uses PySide6 for its graphical user interface.

Cross-platform compatibility should be preserved where practical, but Linux behavior takes priority.

## 3. Supported File Formats

The application must support:

* MP3
* M4B

Support for additional audio formats may be added later without requiring a redesign of the user interface.

## 4. File Discovery

The user must be able to select a directory containing audiobook files.

The application must be able to discover supported audio files within the selected location.

Directory structures must not be modified simply by loading them into the application.

Opening or scanning files must never modify their metadata.

## 5. Metadata Reading

The application must read metadata embedded in supported audio files.

Metadata should be presented in a consistent application-level representation even when different file formats use different underlying metadata systems.

For example, MP3 ID3 frames and MP4/M4B atoms may represent equivalent logical fields differently.

The application should hide these format-specific differences from normal editing operations.

## 6. Metadata Editing

Metadata changes are first made in application memory.

Editing behavior depends on the editing workflow.

Edits made in the metadata panel must not immediately modify the audio file on disk. They remain pending until the user explicitly saves them.

In the center-panel file table, pressing Enter after editing a metadata cell is itself an explicit save action and immediately writes that field to the audio file.

The application must clearly distinguish between:

* metadata currently stored in the file;
* metadata modified in the application but not yet saved.

Files containing unsaved changes must be visibly identifiable.

## 7. Explicit Save Model

Metadata must only be written to disk following an explicit user action.

The application provides two editing workflows with different explicit save actions, plus the explicit Auto-number Tracks operation.

### Center-Panel Table

When editing a metadata cell in the center-panel table, pressing Enter is an explicit save action.

Pressing Enter must:

* commit the edited value;
* save that field to the corresponding audio file;
* preserve unrelated metadata;
* synchronize application state with the successfully saved value;
* leave no dirty state caused solely by the saved edit; and
* continue editing in the same column of the next row when one exists.

Merely entering, selecting, or navigating through table cells must not write metadata.

### Metadata Panel

Changes made in the metadata panel remain pending until explicitly saved.

Metadata-panel save actions include:

* the Save Changes button; and
* choosing Save from an Unsaved Changes prompt.

Navigation between metadata-panel fields must not implicitly save metadata.

Closing the application, changing directories, selecting another file, or performing another operation that would discard pending metadata-panel edits must warn the user when unsaved changes exist.

### Auto-number Tracks

The main toolbar provides **Auto-number Tracks…** for the currently selected center-panel rows. The dialog asks for **Starting track number**, defaults to 1, and accepts only positive integers. Cancel makes no changes; with no selection, an informational message requests selected files.

OK explicitly saves consecutive `track_number` values in the current visual row order, without independently sorting paths. Only track numbers are written; track totals, comments, artwork, and unrelated/unknown metadata are preserved for MP3 and M4B. Each successful save updates the table and saved-state baseline without introducing dirty state or discarding unrelated pending metadata-panel edits.

Saving is sequential and stops at the first failure. Earlier successful writes remain saved and synchronized; subsequent files are not processed. The error identifies the failed file and cause and reports how many files were saved. No rollback is attempted.

## 8. Metadata Preservation

Saving edited metadata must not unnecessarily destroy or replace metadata that the application does not currently expose.

Unknown or unsupported metadata should be preserved whenever technically possible.

Editing one field must not cause unrelated metadata fields to disappear.

This requirement is particularly important because audiobook files may contain metadata written by several different applications.

## 9. Artwork

Embedded artwork must be readable and displayable.

Existing artwork must be preserved unless the user explicitly modifies or removes it.

Editing unrelated metadata must not rewrite or remove artwork.

Future versions may provide artwork replacement and management functionality.

## 10. File List

The application must provide a list of loaded audio files.

The list should allow the user to:

* select a file;
* select multiple files;
* identify files containing unsaved changes;
* navigate efficiently using the keyboard.

The file list represents files, not database records.

## 11. Single-File Editing

When one file is selected, its metadata must be available for detailed editing.

Changes should immediately update the application's in-memory representation.

The file must become marked as modified when its effective metadata differs from the metadata currently stored on disk.

Simply entering and leaving an editor without changing its value must not mark the file as modified.

## 12. Multi-File Editing

The application must support editing metadata across multiple selected files.

A field should only be changed across the selected files when the user explicitly requests that change.

Fields that are not part of a multi-file edit must remain unchanged.

Mixed values across selected files must not accidentally be replaced merely because the files were selected.

## 13. Keyboard Editing

Efficient keyboard-based metadata editing is a core requirement.

The user must be able to move through editable fields without repeatedly using the mouse.

Pressing Enter while editing a center-panel metadata cell must commit the current edit, save that field to disk, and move editing focus according to the application's navigation rules.

A successful center-panel Enter-save must not:

* leave the successfully saved field dirty;
* create a false modified state; or
* trigger an Unsaved Changes warning solely because of that saved edit.

Pressing Enter while editing a field in the metadata panel must not save metadata to disk. Metadata-panel edits remain pending until explicitly saved through the metadata-panel save workflow.

## 14. Dirty-State Tracking

The application must track whether each loaded file contains unsaved changes.

Dirty state must be based on actual metadata differences rather than merely on UI events.

A file becomes dirty when its current in-memory metadata differs from its loaded/saved state.

If the user changes a value and subsequently restores the original value, the file should no longer be considered dirty.

UI navigation alone must never change dirty state.

## 15. Safety

Metadata editing should favor preservation of user data over convenience.

Potentially destructive operations should be explicit.

The application should avoid silently:

* deleting metadata;
* replacing unsupported metadata;
* removing artwork;
* saving unintended edits;
* modifying files merely because they were opened.

## 16. Error Handling

Failure to read one file should not unnecessarily prevent other files from being loaded.

Failure to write metadata must be reported clearly to the user.

The application must not report a successful save unless the write operation actually succeeded.

Where practical, errors should identify the affected file and operation.

## 17. Architecture Constraints

The application must not introduce a separate media or audiobook database.

Metadata stored in the audio files remains authoritative.

Format-specific metadata handling should be isolated from general UI behavior.

UI components should not need detailed knowledge of ID3 frames or MP4 atoms.

The design should allow additional metadata formats and fields to be introduced without requiring large-scale changes to unrelated UI code.

## 18. Development Requirements

Changes should be small enough to review through Git diffs.

Behavioral changes should have automated tests where practical.

Bug fixes should preferably include a regression test demonstrating the corrected behavior.

Large unrelated refactoring should not be combined with feature changes.

The repository's requirements and architecture documentation should be updated when intentional design changes make existing documentation inaccurate.

## 19. Non-Goals

The application is not intended to:

* replace Plex;
* maintain a duplicate audiobook database;
* automatically reorganize the user's audiobook library;
* automatically modify metadata merely because a file was discovered;
* silently normalize or rewrite all metadata;
* act as a general-purpose audio player.

These capabilities should not be introduced indirectly as part of unrelated features.

## 20. Guiding Principle

The user remains in control of changes to their audio files.

Reading, browsing, selecting, and navigating are non-destructive operations.

Writing metadata is an explicit operation.
