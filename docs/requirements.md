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

Each table editor is associated with its file and logical column before committing. Sorting caused by the commit must not change the save target. After a verified save, advance to the row after the saved file in the post-save/post-sort visual order, in the same column; stop if the saved file is last. Invalid numeric Enter leaves the accepted cell unchanged, keeps the invalid input focused and selected, and neither writes nor advances. Automatically opened editors follow the same rules as mouse-opened editors.

Merely entering, selecting, or navigating through table cells must not write metadata.

### Metadata Panel

Changes made in the metadata panel remain pending until explicitly saved.

Metadata-panel save actions include:

* the Save Changes button; and
* choosing Save from an Unsaved Changes prompt.

Navigation between metadata-panel fields must not implicitly save metadata.

Save Changes writes only fields differing from the saved baseline for one file, or explicitly selected/edited fields for multiple files. Track/disc numbers and totals are independent: changing or clearing one component preserves the other. Unchanged artwork is omitted from the write; choosing or pasting artwork explicitly requests replacement, and removing artwork (including pasting a clipboard with no artwork) requests removal. Explicit replacement applies even when its bytes match the displayed first cover, because a file may contain additional covers. Successful saves synchronize from disk readback.

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

Remove Artwork is a no-op for files with no saved artwork. It cancels a pending artwork addition on such files without leaving artwork-related dirty state. In a mixed selection, only files with saved artwork acquire pending removal; unrelated pending field edits remain intact. Artwork-only saves skip files where removal is a no-op.

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

Filename sorting uses the actual filename, case-insensitively, in either direction. Adding or removing a dirty asterisk must not change row order; the marker is presentation only. Other metadata-column sorting remains unchanged.

Every column automatically grows or shrinks to fit the wider of its complete header and widest displayed cell, including Qt style padding. Sizing considers all rows, including rows outside the viewport, and updates after loading a file set or changing displayed metadata. Empty tables and columns retain enough width for their headers.

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

During multi-selection, single-line scalar text editors offer an editable existing-values dropdown: Title, Artist, Album, Album Artist, Genre, Date, Composer, Comment, ID3v1 Comment, Publisher, Copyright, Narrator, Series and Series Number. Choices contain Empty (the actual empty string) followed by distinct accepted values in first-occurrence selected-file order, preserving case and whitespace. A literal existing value `Empty` is displayed quoted to distinguish it from clearing. Mixed values remain a placeholder, never a choice. Opening, navigating or dismissing the menu creates no intent; activating a value uses the same pending multi-edit rules as typing and never writes automatically. Users can continue typing arbitrary values or edit a chosen value. Common-value restoration remains clean unless persistence is unresolved.

Choices refresh from accepted baselines after context changes, Save, Discard and verification, without replacing pending text or creating edit signals. Cancel retains the old context and choices. Values whose accepted baseline is unavailable after a failed write are not offered as known values. Single-file and empty contexts hide the dropdown. Existing format restrictions remain in force. Description retains its multiline editor in this checkpoint; numeric fields and artwork have no dropdowns.

Selecting multiple files directly from an empty editing context must work without a preceding single-file selection. Closing with pending multi-file edits prompts for Save / Discard / Cancel using the selected-file count, never a previous single-file name. Save uses the existing multi-file save workflow; failed Save and Cancel prevent close and preserve pending state. Discard closes without writing pending edits.

Remove Artwork in a multi-selection derives removal intent from the selected files, without requiring a single-file baseline. It remains pending until explicitly saved; repeated removal is stable, files without artwork remain clean for artwork-only removal, and Undo/Discard restore the saved presentation through the existing workflows.

ID3v1 Comment is enabled only for a nonempty selection containing exclusively MP3 files. It is disabled for M4B-only and mixed MP3/M4B selections, independent of prior selection. Multi-edit applies a chosen field to all selected targets, while the M4B writer does not support ID3v1 Comment; disabling mixed-format editing avoids offering an edit that cannot apply to every target. This controls the panel editor; Paste Metadata and writer semantics are unchanged.

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

Pending state represents effective unresolved edits. Restoring a multi-file field to its original common value removes that field's pending intent without affecting other edits. For genuinely mixed values, explicitly entering a value (including blank) remains pending if any selected target differs; Save still applies that intended field across the selection. `series_number` remains a string.

Multi-file row asterisks reflect each file's effective pending changes across all intended fields and applicable artwork operations. A file already matching every intended scalar value remains unmarked even when the selection has pending intent. Missing accepted values cannot prove equality. Invalid numeric input and unresolved multi-file Save state conservatively mark the selection; the latter is tracked by field across the selection, not per file. These indicators do not alter which targets Save writes.

Nonblank invalid numeric input is pending even before successful validation, including when the saved number is blank. Save uses the existing validation messages and focuses/selects the invalid input without writing. Save / Discard / Cancel guards protect this input during selection changes, directory changes, Refresh and close; Discard reloads saved values when continuing to edit, and correction/restoration recalculates pending state.

Pasting absent artwork creates no artwork intent when every target is already artwork-free, and cancels a pending addition on those targets. With mixed or all-present saved artwork it requests removal only where artwork exists. Explicit replacement, including identical cover bytes, retains its replacement semantics.

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

A successfully read file with no supported tags returns valid empty metadata. An operational opening/parsing failure is an explicit metadata read error, never an empty saved baseline. Directory scans skip unreadable files and report them while loading readable files. Failed selection reads restore the accepted selection (or leave no selection initially) without replacing its baseline, pending values or artwork. Required reads for Undo/Discard, Paste, Copy and artwork inspection must complete before those operations replace state; failed discard reloads prevent navigation. Optional artwork dirty-indicator reads keep existing markers and report through status rather than opening a dialog.

A write followed by failed readback is not reported as a completed save. The error identifies the file and explains that the write may have succeeded; no automatic rollback occurs. Panel values and pending intent remain available. Multi-file saving stops on a required read failure; earlier writes remain on disk and selection-wide intent is retained for retry. A failure during final common-display readback must not clear intent or announce success.

Unresolved multi-file Save intent takes precedence over ordinary effective-dirty comparison. Editing/restoring unrelated fields, restoring the failed field to a cached value, clearing a field, or pasting absent artwork cannot silently erase unresolved intent. It remains pending until a selection-wide Save completes, including final reads, or Discard successfully reloads current disk metadata. Failed Discard and Cancel preserve the context; close retains its existing Save / Discard / Cancel behavior without rolling back completed writes. Successfully verified Auto-number keeps its existing behavior of resolving pending Track intent, while unrelated unresolved intent remains protected.

Save again reapplies the current pending values to the entire selected set, including files already verified on an earlier attempt. Changed pending values therefore also reach those files. Artwork replacement retains explicit same-cover semantics; artwork-only removal skips files currently without artwork. Retrying an intended field may overwrite a newer external change to that field; unrelated external fields remain protected by field-specific writes. General external-change conflict detection is not provided. Failure messages identify the path, count writes completed and read back in that attempt, explain that earlier writes remain and later files were not attempted after a loop failure, and explain selection-wide retry. A writer exception never establishes that its file was unchanged.

Single-file panel Save tracks attempted logical fields (including artwork) as unresolved before invoking the writer. Writer exceptions, including failures after modification, and failed readback leave that uncertainty pending even if the user restores cached pre-save values. Save reapplies the current panel values for those fields, preserving untouched fields and numeric-pair components; invalid numeric input still blocks writing. Artwork uncertainty survives preview changes, with existing explicit same-cover replacement semantics. Uncertainty clears after verified Save and presentation synchronization, or successful Discard/reload accepting current disk truth, never by cached equality alone. Failed Discard and Cancel preserve context. Selection, directory and Refresh guards require conclusive Save or successful Discard; close retains its existing Discard behavior of exiting without a reload or rollback. A verified explicit table edit or Auto-number supersedes only its affected field; verification-only recovery does not erase unresolved panel intent.

Immediate field saves establish verification uncertainty when invoking a writer. If it raises, recovery reads current disk metadata and reconciles the affected file through the existing verification-only policy, preserving pending panel intent. A known pre-write, requested, or different persisted field value is reported distinctly; an unreadable outcome remains marked and guarded until verification or successful reload. The writer exception is always reported: Enter does not advance, and Auto-number stops at that file even if recovery finds the requested value. Earlier verified files remain saved, later files are not attempted, and no rollback or automatic write replay occurs.

Immediate field-save/Auto-number readback failures keep the prior baseline and track which fields still require verification. These unresolved files remain marked and protected by the existing transition guard; the mark means verification is pending, not that the disk write was rolled back. Enter does not advance and Auto-number stops. Save Changes retries verification without repeating the immediate write and preserves subsequent panel edits; successful explicit reload/Undo also resolves verification state. Auto-number failure counts distinguish saved-and-verified files from the potentially written file whose readback failed.


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

### Selection transitions and Enter navigation

Pending metadata-panel edits are protected by Save / Discard / Cancel when changing between single-file and multi-file editing contexts, including when the old file remains selected. Cancel restores the previous selection and current cell; a failed Save keeps the pending context. Discard restores saved table values before loading the requested context.

After a successful center-table Enter-save, advancing to the next row selects that file and displays its disk-backed metadata in the panel. If this would replace unrelated pending panel edits, the existing Unsaved Changes prompt runs after the field save: Save or Discard permits the advance, while Cancel keeps the previous context and stops the advance. The completed field save remains saved. Failed field saves do not advance; the final row does not wrap.

Center-table text remains transient until Enter requests the immediate save. Abandoning its editor through focus loss, another cell/selection, Tab, Escape, directory navigation, Refresh or close discards that text and retains accepted table presentation. Qt's automatic editor commits must not make it appear saved or turn it into pending metadata-panel edits. Existing guards still protect unrelated panel edits.

Directory changes, Open Folder, and Refresh protect pending panel edits with the same Save / Discard / Cancel guard before replacing rows or rebuilding the tree. Failed Save and Cancel retain the old directory, selection and pending presentation. Refresh reloads the currently accepted directory without rebuilding the navigator or restoring file selection. Accepted tree selection and expansion state remain intact. Accepted reloads and clearing the table selection clear the file editing target, baseline, panel values, artwork, intent and dirty indicators; clipboard metadata remains available. A populated table with no selected row has no active metadata-panel target.


### Filesystem folder navigator

The left panel is a read-only filesystem navigator, not a library index. It shows the chosen root's basename prominently and its full path below, with a **Choose Root…** button. A synthetic **Books** node represents that root; its children are the root's direct subdirectories. Directory names have no author, book, year, edition or narrator parsing semantics. Audio and other files are never tree nodes.

Directory discovery is lazy: setup enumerates only the root level, and expansion enumerates only that node's direct children. Siblings use case-insensitive filename ordering. Dot-directories and symlinked child directories are omitted; no recursive symlink traversal or filesystem modification is provided. Failed expansion reports a status message, installs no partial children and can be retried by collapsing and expanding.

Selecting Books loads files directly inside the root. Selecting another folder loads only its direct audio files through FileList; it never aggregates descendants. Tree navigation and root changes reuse the existing Save / Discard / Cancel guard, including invalid numeric input and all persistence-uncertainty states. Cancel or failed navigation restores the accepted tree selection and retains the accepted table context. Directory enumeration is checked before prompting and again before replacing rows, so an unavailable destination does not destroy the old table.

Choose Root installs and remembers only a successfully accepted root using QSettings. Startup restores a readable remembered root and loads its direct files. A missing or unreadable remembered root leaves a clear “No audiobook root selected” state, keeps Choose Root available and retains the setting for a temporarily unavailable mount. There is no fallback directory, database or metadata cache.

Open Folder remains available for arbitrary directories and does not redefine or persist the navigator root. If its directory has no displayed tree node, the tree selection is cleared. Refresh reloads the currently accepted directory, including arbitrary Open Folder locations. The configured navigator root changes navigation only when explicitly selected/used. An unavailable current directory is reported without falling back to the root or replacing the accepted context. No file selection is restored.

### Generate Text

**Generate Text…** previews per-file pending values for Title, Artist, Album, Album Artist, Genre, Date, Composer, Publisher, Copyright, Narrator, Series or Series Number. Numeric fields, artwork, Comment, ID3v1 Comment and Description are not targets. Preview and Cancel do not modify files or editing state. Apply is available only after every selected target evaluates successfully and creates pending values; Save Changes is required for persistence.

Templates copy literal text and accept exact lowercase variables `{index}`, `{track}`, `{disc}`, `{title}`, `{artist}`, `{album}`, `{album_artist}`, `{narrator}`, `{series}`, `{series_number}`, `{date}` and `{filename}`. Text comes from each file's accepted metadata, not pending edits. Filename is the actual basename including extension, never the decorated table text. Index is one-based current visual selected-row order captured when opening the dialog; Track and Disc use accepted number components, never totals. Missing numeric or unavailable accepted values are errors; empty text expands to empty text.

Numeric variables alone accept `:0WIDTH`, where WIDTH is a positive decimal integer without leading zeros, at most 100: for example `{track:02}`, `{index:010}`. Padding uses a minimum width without truncation. `{{` and `}}` escape literal braces. Unknown variables, malformed braces, conversions, expressions and other format specifications are errors shown per preview row. No partial Apply is allowed.

Generated fields coexist per file and appear as pending values in existing table columns and common/mixed values in MetadataPanel. Filename row tooltips list all generated pending fields, including targets without a table column, so their per-file values remain inspectable after Apply. Dirty markers compare each target against its accepted baseline, including uncertainty; already-matching values alone are clean. Later explicit action wins for the same field: regeneration replaces that field's generated values, a common panel edit or Paste supersedes generated values for that field, and generation supersedes common intent for its target field. Unrelated pending fields remain intact. A verified explicit Enter-save supersedes generated intent only for its saved file/field; verification-only recovery preserves pending generated intent.

Save uses the existing accepted selection path order, independently of row movements caused by generated-value sorting. It writes field-specific changes through the existing writers and accepts saved values only after disk readback. Generated fields already matching accepted values are omitted unless unresolved. Failed or partially completed saves retain current per-file values for retry without rollback; attempted generated fields remain protected until complete verified Save or successful Discard/reload. Retry reapplies current intent, including changes to values since the failure. Discard reloads current disk truth without rollback writes; a failed reload preserves pending intent. Generated differences participate in the existing selection, tree, Open Folder, Choose Root, Refresh and close guards.

Generate Text remembers only the last successfully applied target field and template across launches. Cancel, unapplied edits and invalid templates do not update these preferences. First use defaults to Title / `Chapter {track:02}`. An unsupported stored target falls back to Title; stored template text is restored verbatim and validated by the normal live preview. No history or presets are maintained.


### Copy Down / Copy Up

The center-table context menu provides **Copy Down** (Ctrl+D) and **Copy Up** (Ctrl+Shift+D) for Title, Artist, Album, Series, Series Number and Narrator. Filename and numeric Track are excluded; numeric copying is deferred to preserve typed validation and pair semantics. Actions require an eligible active cell and a selected target on the requested side.

Copy uses the active cell's effective model value, including pending generated or previously copied values, without rereading disk. Unconfirmed editor text is abandoned without committing. Only selected rows strictly below/above the source in current visual order are targets; the source and other rows retain their intent. No qualifying target is a clean no-op. Stable target paths are captured before updates can cause sorting; dirty asterisks never affect Filename sorting.

Copy creates pending per-file text edits without invoking a writer. Target cells update immediately, the MetadataPanel uses effective common/mixed presentation, and only real differences or unresolved writes are dirty. Repeated Copy operations can use previous results before Save. Generate Text and Copy share pending state: the later explicit action wins for its field and targets, preserving other fields and non-target intent. A partial override of a common panel edit preserves that edit for the other files; a later common edit supersedes per-file values for that field.

Save Changes uses the existing field-specific write/readback path, preserving unrelated tags and artwork. Failures retain per-file intent and uncertainty for retry with current values, without rollback. Successful Discard reloads disk truth; failed reload preserves intent. Existing selection, folder, root, Refresh and close Save/Discard/Cancel guards apply. Direct table editing plus Enter retains its immediate single-field save behavior.


### MP3 tag-version preservation

MP3 writes preserve an existing ID3v2.3 or ID3v2.4 major version, including full writes. Field-specific edits preserve unrelated Mutagen-supported frames valid for that version, including v2.3-only frames such as TSIZ, custom TXXX values, comments, artwork and unrequested Track/Disc components. Full writes retain their existing supported-field replacement semantics. This is semantic preservation, not byte-identical tag serialization; Mutagen may change encoding/padding. Existing multi-valued v2.3 text is retained using null separators rather than merged with slashes (a nonstandard v2.3 convention). Arbitrary malformed, unparsed or incompatible frames have no blanket preservation guarantee. Older tag versions retain the existing upgrade behavior; creating tags on untagged MP3s remains unsupported.
