from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QSignalBlocker,
    QItemSelectionModel,
    QPersistentModelIndex,
)
from PySide6.QtGui import (
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QScrollArea,
    QToolBar,
)

from ..editing_rules import changed_scalar_fields, effective_multi_fields, effective_fields_for_target
from ..metadata.writer import write_metadata, validate_date_for_file
from ..metadata.date import verify_date, DateVerificationError
from .dialogs.auto_number_dialog import AutoNumberDialog
from .dialogs.generate_text_dialog import GenerateTextDialog, TARGETS
from .dialogs.paste_fields_dialog import PasteFieldsDialog
from .folder_navigator import FolderNavigator
from .. import settings
from .file_list import FileList, TABLE_FIELDS
from .metadata_panel import MetadataPanel
from .artwork import decode_artwork
from ..metadata import (
    read_metadata,
    MetadataReadError,
    write_mp3_metadata,
    write_m4b_metadata,
)


def _numeric_validation_error(text):
    """Use the same raw-input rules for pending state and explicit validation."""
    text = text.strip()
    if text:
        try:
            value = int(text)
        except ValueError:
            return "must be a whole number."
        if value < 0:
            return "cannot be negative."
    return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Audio Metadata Editor")
        self.resize(1200, 700)

        self.settings = settings.create_settings()
        self.current_directory = None
        self.root_path = None
        self.current_file = None
        self.selected_files = []
        self._context_index = QPersistentModelIndex()
        self._per_file_edits: dict[Path, dict[str, str]] = {}
        self._unresolved_per_file_fields: dict[Path, set[str]] = {}
        self.multi_edit_fields = set()
        self._multi_field_baselines = {}
        # Unresolved selection-wide intent cannot be dropped by cached comparison.
        self._unresolved_multi_fields = set()
        # Current single-panel intent whose attempted persistence is unresolved.
        # Unlike immediate-write verification, Save reapplies current values.
        self._unresolved_single_fields = set()
        self.current_metadata = None
        # Immediate writes awaiting a successful readback, not new panel edits.
        self._unverified_fields = {}
        self.pending_artwork = None
        self.pending_artwork_mime = ""
        # Replacement/removal intent cannot be inferred from the first cover alone.
        self.artwork_edited = False
        self.multi_edit_artwork = False
        self.metadata_clipboard = None
        self.paste_metadata_fields = set()

        self._create_toolbar()
        self._create_main_layout()
        self._create_status_bar()
        self._create_shortcuts()
        remembered = self.settings.value(settings.ROOT_KEY, "", type=str)
        if remembered:
            self._install_root(Path(remembered))


    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        open_button = QPushButton("Open Folder")
        open_button.clicked.connect(self._open_folder)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_tree)

        save_button = QPushButton("Save Changes")
        save_button.clicked.connect(self._save_changes)

        undo_button = QPushButton("Undo Changes")
        undo_button.clicked.connect(self._undo_changes)

        copy_button = QPushButton("Copy Metadata")
        copy_button.clicked.connect(self._copy_metadata)

        paste_button = QPushButton("Paste Metadata")
        paste_button.clicked.connect(self._paste_metadata)

        toolbar.addWidget(open_button)
        toolbar.addWidget(refresh_button)

        toolbar.addSeparator()

        toolbar.addWidget(save_button)
        toolbar.addWidget(undo_button)
        toolbar.addWidget(copy_button)
        toolbar.addWidget(paste_button)
        toolbar.addAction("Auto-number Tracks…", self._auto_number_tracks)
        toolbar.addAction("Generate Text…", self._generate_text)

    def _create_main_layout(self):
        splitter = QSplitter()

        # Directory tree
        self.folder_navigator = FolderNavigator()
        self.directory_tree = self.folder_navigator.tree
        self.directory_tree.directory_requested.connect(self._directory_selected)
        self.directory_tree.enumeration_failed.connect(self.statusBar().showMessage)
        self.folder_navigator.choose_root_requested.connect(self._choose_root)

        splitter.addWidget(self.folder_navigator)

        # File list
        self.file_list = FileList()
        self.file_list.copy_values_requested.connect(self._copy_table_values)
        self.file_list.save_cell_requested.connect(
            self._save_table_cell
        )
        self.file_list.metadata_cell_edited.connect(
            self._metadata_cell_edited
        )
        self.file_list.advance_requested.connect(self._advance_table_row)
        self.file_list.files_selected.connect(self._files_selected)
        splitter.addWidget(self.file_list)

        # Metadata panel
        self.metadata_panel = MetadataPanel()
        # Keep existing behavior methods and tests using the same control objects.
        # Qt ownership belongs to MetadataPanel; these references hold no edit state.
        self.artwork_label = self.metadata_panel.artwork_label
        self.choose_artwork_button = self.metadata_panel.choose_artwork_button
        self.remove_artwork_button = self.metadata_panel.remove_artwork_button
        self.title_edit = self.metadata_panel.title_edit
        self.artist_edit = self.metadata_panel.artist_edit
        self.album_edit = self.metadata_panel.album_edit
        self.album_artist_edit = self.metadata_panel.album_artist_edit
        self.genre_edit = self.metadata_panel.genre_edit
        self.track_edit = self.metadata_panel.track_edit
        self.track_total_edit = self.metadata_panel.track_total_edit
        self.disc_edit = self.metadata_panel.disc_edit
        self.disc_total_edit = self.metadata_panel.disc_total_edit
        self.narrator_edit = self.metadata_panel.narrator_edit
        self.series_edit = self.metadata_panel.series_edit
        self.series_number_edit = self.metadata_panel.series_number_edit
        self.publisher_edit = self.metadata_panel.publisher_edit
        self.date_edit = self.metadata_panel.date_edit
        self.composer_edit = self.metadata_panel.composer_edit
        self.comment_edit = self.metadata_panel.comment_edit
        self.id3v1_comment_edit = self.metadata_panel.id3v1_comment_edit
        self.copyright_edit = self.metadata_panel.copyright_edit
        self.description_edit = self.metadata_panel.description_edit

        self.choose_artwork_button.clicked.connect(self._choose_artwork)
        self.remove_artwork_button.clicked.connect(self._remove_artwork)

        self.metadata_scroll = metadata_scroll = QScrollArea()
        metadata_scroll.setWidgetResizable(True)
        metadata_scroll.setFrameShape(QScrollArea.NoFrame)
        metadata_scroll.setWidget(self.metadata_panel)
        splitter.addWidget(metadata_scroll)
        QApplication.instance().focusChanged.connect(self._reveal_metadata_focus)

        splitter.setSizes([250, 600, 350])

        self.setCentralWidget(splitter)
        self._connect_multi_edit_tracking()

    def _reveal_metadata_focus(self, previous, current):
        # Include programmatic validation focus, not only Tab traversal.
        if current is not None and self.metadata_panel.isAncestorOf(current):
            self.metadata_scroll.ensureWidgetVisible(current)

    def _files_selected(self, paths):
        if set(paths) == set(self.selected_files):
            return True
        try:
            metadatas = [read_metadata(Path(path)) for path in paths]
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Read Failed", str(exc))
            self._restore_file_selection()
            return False
        if not self._guard_selection_change():
            return False
        # Saving the old context can change files shared with the requested context.
        try:
            metadatas = [read_metadata(Path(path)) for path in paths]
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Read Failed", str(exc))
            self._restore_file_selection()
            return False
        if len(paths) == 1:
            self._load_single_file(paths[0], metadatas[0])
        elif paths:
            self.selected_files = list(paths)
            self.multi_edit_artwork = False
            self.artwork_edited = False
            self.pending_artwork = None
            self.pending_artwork_mime = ""
            self._show_common_metadata(metadatas)
        else:
            self._clear_editing_context()
        self._context_index = QPersistentModelIndex(self.file_list.currentIndex())
        return True

    def _clear_editing_context(self):
        self._per_file_edits.clear()
        self._unresolved_per_file_fields.clear()
        self._unresolved_single_fields.clear()
        self._unresolved_multi_fields.clear()
        self._unverified_fields.clear()
        self._multi_field_baselines.clear()
        self.current_file = None
        self.selected_files = []
        self.current_metadata = None
        self._context_index = QPersistentModelIndex()
        self.multi_edit_fields.clear()
        self.multi_edit_artwork = False
        self.artwork_edited = False
        self.pending_artwork = None
        self.pending_artwork_mime = ""
        self.metadata_panel.clear_metadata()
        self._show_artwork_preview(None)
        self.metadata_panel.set_id3v1_comment_enabled(False)
        self._update_multi_edit_visuals()
        self.statusBar().clearMessage()

    def _guard_selection_change(self):
        if not self._has_unsaved_changes():
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes to the selected files.\n\n"
            "Do you want to save them before switching files?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Save:
            self._save_changes()
            if not self._has_unsaved_changes():
                return True
        elif reply == QMessageBox.StandardButton.Discard:
            self._undo_changes()
            if not self._has_unsaved_changes():
                return True
        self._restore_file_selection()
        return False

    def _restore_file_selection(self):
        with QSignalBlocker(self.file_list):
            self.file_list.select_files(self.selected_files)
            if self._context_index.isValid():
                self.file_list.setCurrentCell(
                    self._context_index.row(), self._context_index.column(),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )

    def _advance_table_row(self, path):
        self.file_list.advance_allowed = self._files_selected([path])
        if self.file_list.advance_allowed:
            with QSignalBlocker(self.file_list):
                self.file_list.select_files([path])
                row = next(r for r in range(self.file_list.rowCount())
                           if self.file_list.item(r, 0).data(256) == path)
                self._context_index = QPersistentModelIndex(
                    self.file_list.model().index(row, self.file_list.currentColumn()))

    def _create_status_bar(self):
        self.status_label = QLabel("No folder selected")
        self.statusBar().addPermanentWidget(self.status_label)

    def _open_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Audiobook Folder")
        if directory:
            self._directory_selected(directory)

    def _choose_root(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose Audiobook Root")
        if directory and self._install_root(Path(directory)):
            self.settings.setValue(settings.ROOT_KEY, str(self.root_path))
            self.settings.sync()

    def _install_root(self, path):
        path = path.absolute()
        try:
            directories = self.directory_tree.child_directories(path)
        except OSError as exc:
            self.statusBar().showMessage(f"Cannot list {path}: {exc}")
            return False
        if not self._directory_selected(path):
            return False
        self.root_path = path
        self.folder_navigator.set_root(path, directories)
        return True

    def _populate_root(self):
        if self.root_path is not None:
            return self._install_root(self.root_path)
        return False

    def _directory_selected(self, path):
        if not path:
            return False
        directory = Path(path)
        try:
            self.file_list.directory_files(directory)
        except OSError as exc:
            self.directory_tree.restore_current_directory()
            self.statusBar().showMessage(f"Cannot list {directory}: {exc}")
            return False
        if not self._guard_selection_change():
            self.directory_tree.restore_current_directory()
            return False
        # Recheck enumeration after the guard before replacing rows. Metadata is
        # read after Save/Discard, so shared files reflect any completed writes.
        with QSignalBlocker(self.file_list):
            errors = self.file_list.load_directory(directory)
        if errors is None:
            self.directory_tree.restore_current_directory()
            self.statusBar().showMessage(f"Cannot list {directory}: {self.file_list.directory_error}")
            return False
        self._clear_editing_context()
        self.current_directory = directory
        self.directory_tree.set_current_directory(directory)
        self.status_label.setText(str(directory))
        if errors:
            QMessageBox.critical(
                self, "Read Failed", "Skipped unreadable files:\n\n" + "\n".join(map(str, errors))
            )
        return True

    def _refresh_tree(self):
        if self.current_directory is not None:
            self._directory_selected(self.current_directory)

    def _show_metadata(self, metadata):
        self.metadata_panel.set_metadata(metadata)
        self._show_artwork_preview(metadata.artwork)
        self.metadata_panel.set_id3v1_comment_enabled(
            self.current_file is not None
            and self.current_file.suffix.lower() == ".mp3"
        )

    def _file_selected(self, path):
        # Explicit reloads must also finish reading before replacing panel state.
        if set(self.selected_files) != {path}:
            return self._files_selected([path])
        try:
            metadata = read_metadata(Path(path))
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Read Failed", str(exc))
            return False
        self.file_list.update_file_metadata(Path(path), metadata)
        self._load_single_file(path, metadata)
        return True

    def _load_single_file(self, path, metadata):
        self._per_file_edits.clear()
        self._unresolved_per_file_fields.clear()
        self._unresolved_single_fields.clear()
        self._unresolved_multi_fields.clear()
        self._multi_field_baselines.clear()
        new_file = Path(path)
        self._unverified_fields.pop(new_file, None)
        self.selected_files = [path]
        self.current_file = new_file
        self._context_index = QPersistentModelIndex(self.file_list.currentIndex())

        self.current_metadata = metadata
        self.pending_artwork = metadata.artwork
        self.pending_artwork_mime = metadata.artwork_mime
        self.artwork_edited = False

        self.multi_edit_fields.clear()
        self.multi_edit_artwork = False

        self._show_metadata(metadata)
        self._update_multi_edit_visuals()

    def _accepted_scalars(self, path):
        if len(self.selected_files) > 1:
            return self._multi_field_baselines.get(path, {})
        if self.current_metadata is not None and path == self.current_file:
            return {field: getattr(self.current_metadata, field)
                    for field in self.metadata_panel.field_names}
        return {}

    def _per_file_changes(self, path):
        baseline = self._accepted_scalars(path)
        return {field for field, value in self._per_file_edits.get(path, {}).items()
                if field not in baseline or baseline[field] != value} | self._unresolved_per_file_fields.get(path, set())

    def _generate_text(self):
        paths = [Path(path) for path in self.file_list.selected_paths_in_row_order()]
        if not paths:
            QMessageBox.information(self, "Generate Text", "Select at least one file.")
            return
        targets = []
        for index, path in enumerate(paths, 1):
            accepted = dict(self._accepted_scalars(path))
            for field in (self._unverified_fields.get(path, set())
                          | self._unresolved_per_file_fields.get(path, set())
                          | self._unresolved_single_fields | self._unresolved_multi_fields):
                accepted.pop(field, None)
            context = dict(accepted, index=index, filename=path.name,
                           track=accepted.get('track_number'), disc=accepted.get('disc_number'))
            targets.append((path, context))
        dialog = GenerateTextDialog(
            targets, self,
            initial_field=self.settings.value(settings.GENERATE_TEXT_FIELD_KEY, 'title', type=str),
            initial_template=self.settings.value(
                settings.GENERATE_TEXT_TEMPLATE_KEY, 'Chapter {track:02}', type=str),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.generated is not None:
            self._apply_generated(*dialog.generated)
            self.settings.setValue(settings.GENERATE_TEXT_FIELD_KEY, dialog.generated[0])
            self.settings.setValue(settings.GENERATE_TEXT_TEMPLATE_KEY, dialog.template.text())
            self.settings.sync()

    def _apply_generated(self, field, values):
        # Validate the complete result before changing any application state.
        if field not in TARGETS or set(values) != {Path(p) for p in self.selected_files} or not all(isinstance(v, str) for v in values.values()):
            raise ValueError("Invalid generated targets")
        self._apply_per_file_values(field, values)

    def _copy_table_values(self, field, values):
        self._apply_per_file_values(field, {Path(path): value for path, value in values.items()})

    def _apply_per_file_values(self, field, values):
        selected = {Path(path) for path in self.selected_files}
        if not values or field not in TARGETS or not set(values) <= selected or not all(isinstance(value, str) for value in values.values()):
            return
        # A subset override splits common intent into equivalent per-file values.
        # Non-targets retain their prior effective intent, including uncertainty.
        common_pending = field in self.multi_edit_fields or field in self._unresolved_multi_fields
        common_unresolved = field in self._unresolved_multi_fields or field in self._unresolved_single_fields
        if common_pending:
            common_value = getattr(self._get_edited_metadata(), field)
            for path in selected - values.keys():
                self._per_file_edits.setdefault(path, {})[field] = common_value
        if common_unresolved:
            for path in selected:
                self._unresolved_per_file_fields.setdefault(path, set()).add(field)
        self.multi_edit_fields.discard(field)
        self._unresolved_multi_fields.discard(field)
        self._unresolved_single_fields.discard(field)
        for path, value in values.items():
            self._per_file_edits.setdefault(path, {})[field] = value
        self._render_per_file_edits()
        self._update_multi_edit_visuals()

    def _render_per_file_edits(self):
        fields = set().union(*(set(values) for values in self._per_file_edits.values()))
        for path, values in self._per_file_edits.items():
            self.file_list.show_pending_fields(path, values)
        updates, mixed = {}, set()
        for field in fields:
            values = [self._per_file_edits.get(Path(p), {}).get(field, self._accepted_scalars(Path(p)).get(field))
                      for p in self.selected_files]
            if values:
                updates[field] = values[0]
                if any(value != values[0] for value in values):
                    mixed.add(field)
        self.metadata_panel.set_field_values(updates, mixed_fields=mixed)
        effective = set().union(*(self._per_file_changes(Path(p)) for p in self.selected_files))
        self.metadata_panel.set_highlighted_fields(self.multi_edit_fields | effective)

    def _supersede_per_file(self, field):
        for path, values in list(self._per_file_edits.items()):
            if field not in values:
                continue
            del values[field]
            if not values:
                del self._per_file_edits[path]
            self.file_list.show_pending_fields(path, {field: self._accepted_scalars(path).get(field)})
            unresolved = self._unresolved_per_file_fields.get(path, set())
            if field in unresolved:
                unresolved.remove(field)
                if len(self.selected_files) > 1:
                    self._unresolved_multi_fields.add(field)
                else:
                    self._unresolved_single_fields.add(field)
            if not unresolved:
                self._unresolved_per_file_fields.pop(path, None)

    def _get_edited_metadata(self):
        metadata = self.metadata_panel.collect_metadata()
        metadata.artwork = self.pending_artwork
        metadata.artwork_mime = self.pending_artwork_mime
        return metadata

    def _pending_dates(self):
        """Only validate Date when this save intends to write it."""
        edited = self._get_edited_metadata()
        if len(self.selected_files) == 1:
            if (edited.date != self.current_metadata.date or 'date' in self._unresolved_single_fields
                    or 'date' in self._per_file_changes(self.current_file)):
                return {self.current_file: edited.date}
            return {}
        return {Path(p): self._per_file_edits.get(Path(p), {}).get('date', edited.date)
                for p in self.selected_files
                if 'date' in self.multi_edit_fields or 'date' in self._per_file_changes(Path(p))}

    def _save_changes(self):
        # Retry verification without rewriting a field that may already be saved.
        try:
            self._verify_field_saves()
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Readback Failed", str(exc))
            return
        if not self._validate_numeric_fields():
            return

        if not self.selected_files:
            QMessageBox.warning(
                self,
                "No Files Selected",
                "No files are selected.",
            )
            return

        date_intent = self._pending_dates()
        try:
            for path, value in date_intent.items():
                validate_date_for_file(path, value)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Date", f"Cannot save Date for {path.name}: {exc}")
            self.metadata_panel.focus_date_field()
            return

        # Multi-file editing
        if len(self.selected_files) > 1:
            if not self.multi_edit_fields and not self.multi_edit_artwork and not any(self._per_file_changes(Path(p)) for p in self.selected_files):
                QMessageBox.information(
                    self,
                    "No Changes",
                    "No metadata fields or artwork have been changed.",
                )
                return

            edited_metadata = self._get_edited_metadata()
            self._unresolved_multi_fields.update(self.multi_edit_fields)
            if self.multi_edit_artwork:
                self._unresolved_multi_fields.add("artwork")
            verified_writes = 0

            try:
                for path_string in self.selected_files:
                    path = Path(path_string)

                    metadata = read_metadata(path)

                    for field in self.multi_edit_fields:
                        setattr(
                            metadata,
                            field,
                            getattr(edited_metadata, field),
                        )

                    pending = self._per_file_edits.get(path, {})
                    fields = self.multi_edit_fields | self._per_file_changes(path)
                    for field, value in pending.items():
                        setattr(metadata, field, value)
                    artwork_options = {}
                    if self.multi_edit_artwork and (
                        self.pending_artwork is not None or metadata.artwork is not None
                    ):
                        artwork_options = {
                            "artwork": self.pending_artwork,
                            "artwork_mime": self.pending_artwork_mime,
                        }

                    if not fields and not artwork_options:
                        continue

                    suffix = path.suffix.lower()

                    # An attempted write can invalidate the old comparison
                    # baseline even if the write or its readback later fails.
                    baseline = self._multi_field_baselines[path]
                    per_file_fields = fields & pending.keys()
                    if per_file_fields:
                        self._unresolved_per_file_fields.setdefault(path, set()).update(per_file_fields)
                    for field in fields:
                        baseline.pop(field, None)

                    if suffix == ".mp3":
                        write_mp3_metadata(
                            path,
                            metadata,
                            fields=fields,
                            **artwork_options,
                        )
                    elif suffix == ".m4b":
                        write_m4b_metadata(
                            path,
                            metadata,
                            fields=fields,
                            **artwork_options,
                        )

                    metadata = self._read_after_write(path)
                    if path in date_intent:
                        verify_date(date_intent[path], metadata.date)
                    verified_writes += 1
                    for field in fields:
                        baseline[field] = getattr(metadata, field)
                    if self.current_file == path:
                        self.current_metadata = metadata
                    self.file_list.update_file_metadata(
                        path,
                        metadata,
                    )

            except Exception as exc:
                self.metadata_panel.set_existing_values(tuple(self._multi_field_baselines.values()))
                self._render_per_file_edits()
                self._update_dirty_indicators()
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Could not complete saving {path}:\n\n{exc}\n\n"
                    f"Writes completed and verified: {verified_writes}.\n"
                    "Earlier writes remain saved; no rollback was attempted.\n"
                    "If writing started, the failing file may have been changed.\n"
                    "Files later in the save order were not attempted.\n"
                    "Save again reapplies the current pending changes to the selected files.",
                )
                return

            try:
                metadatas = [self._read_after_write(Path(path)) for path in self.selected_files]
                for path, metadata in zip(self.selected_files, metadatas):
                    if Path(path) in date_intent:
                        verify_date(date_intent[Path(path)], metadata.date)
            except (MetadataReadError, DateVerificationError) as exc:
                self.metadata_panel.set_existing_values(tuple(self._multi_field_baselines.values()))
                self._render_per_file_edits()
                self._update_dirty_indicators()
                QMessageBox.critical(
                    self, "Readback Failed",
                    f"{exc}\n\nWrites completed and verified: {verified_writes}.\n"
                    "Could not reload the selected files after saving.\n"
                    "Completed writes remain saved; no rollback was attempted.\n"
                    "Save again reapplies the current pending changes to the selected files.",
                )
                return

            self._unresolved_multi_fields.clear()
            self.multi_edit_fields.clear()
            self.multi_edit_artwork = False
            self.artwork_edited = False

            QMessageBox.information(
                self,
                "Saved",
                f"Saved changes to {len(self.selected_files)} files.",
            )

            self._show_common_metadata(metadatas)

            return

        # Single-file editing
        if self.current_file is None:
            QMessageBox.warning(
                self,
                "No File Selected",
                "No file is selected.",
            )
            return

        if not self._has_unsaved_changes():
            QMessageBox.information(
                self,
                "No Changes",
                "No metadata fields or artwork have been changed.",
            )
            return

        metadata = self._get_edited_metadata()
        changed_fields = changed_scalar_fields(self.current_metadata, metadata)
        changed_fields.update(self._unresolved_single_fields - {"artwork"})
        per_file_fields = set(self._per_file_edits.get(self.current_file, {}))
        changed_fields.update(self._per_file_changes(self.current_file))
        artwork_options = {}
        if (
            "artwork" in self._unresolved_single_fields
            or self.artwork_edited
            or self.pending_artwork != self.current_metadata.artwork
            or self.pending_artwork_mime != self.current_metadata.artwork_mime
        ):
            artwork_options = {
                "artwork": self.pending_artwork,
                "artwork_mime": self.pending_artwork_mime,
            }

        # A writer can modify the file and then raise. Stale baseline equality
        # must not discard any attempted logical field, even on writer failure.
        self._unresolved_single_fields.update(changed_fields - per_file_fields)
        if changed_fields & per_file_fields:
            self._unresolved_per_file_fields.setdefault(self.current_file, set()).update(changed_fields & per_file_fields)
        if artwork_options:
            self._unresolved_single_fields.add("artwork")

        try:
            suffix = self.current_file.suffix.lower()

            if suffix == ".mp3":
                write_mp3_metadata(
                    self.current_file,
                    metadata,
                    fields=changed_fields,
                    **artwork_options,
                )

            elif suffix == ".m4b":
                write_m4b_metadata(
                    self.current_file,
                    metadata,
                    fields=changed_fields,
                    **artwork_options,
                )

            else:
                raise ValueError(
                    f"Unsupported file type: {self.current_file.suffix}"
                )

            metadata = self._read_after_write(self.current_file)
            if self.current_file in date_intent:
                verify_date(date_intent[self.current_file], metadata.date)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save the file:\n\n{exc}\n\n"
                "The file may have changed; its metadata state could not be confirmed.\n"
                "No rollback was attempted. Save again reapplies the current panel values.",
            )
            return

        self.current_metadata = metadata
        self.pending_artwork = metadata.artwork
        self.pending_artwork_mime = metadata.artwork_mime
        self.artwork_edited = False
        self._show_metadata(metadata)

        self.file_list.update_file_metadata(
            self.current_file,
            metadata,
        )

        self._unresolved_single_fields.difference_update(changed_fields)
        if artwork_options:
            self._unresolved_single_fields.discard("artwork")
        self._per_file_edits.clear()
        self._unresolved_per_file_fields.clear()
        self._update_multi_edit_visuals()

        QMessageBox.information(
            self,
            "Saved",
            f"Saved changes to {self.current_file.name}.",
        )

    def _has_unsaved_changes(self):
        if any(self._per_file_changes(Path(path)) for path in self.selected_files):
            return True
        if self.selected_files and self._numeric_errors():
            return True
        if any(Path(path) in self._unverified_fields for path in self.selected_files):
            return True
        if len(self.selected_files) > 1:
            return bool(
                self.multi_edit_fields
                or self.multi_edit_artwork
                or self._unresolved_multi_fields
            )

        if self._unresolved_single_fields:
            return True
        if self.current_metadata is None:
            return False

        edited = self._get_edited_metadata()
        loaded = self.current_metadata

        return (
            self.artwork_edited
            or bool(changed_scalar_fields(loaded, edited))
            or self.pending_artwork != loaded.artwork
            or self.pending_artwork_mime != loaded.artwork_mime
        )

    def _undo_changes(self):
        if not self._has_unsaved_changes():
            self.statusBar().showMessage("No Changes")
            return

        try:
            metadatas = [read_metadata(Path(path)) for path in self.selected_files]
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Undo Failed", str(exc))
            return

        self._per_file_edits.clear()
        self._unresolved_per_file_fields.clear()
        for path in self.selected_files:
            self._unverified_fields.pop(Path(path), None)
        if len(self.selected_files) > 1:
            self.multi_edit_fields.clear()
            self.multi_edit_artwork = False
            self.artwork_edited = False
            self.pending_artwork = None
            self.pending_artwork_mime = ""

            self._show_common_metadata(metadatas)

            for path_string, metadata in zip(
                self.selected_files,
                metadatas,
            ):
                self.file_list.update_file_metadata(
                    Path(path_string),
                    metadata,
                )

            self._update_multi_edit_visuals()
            return

        if len(self.selected_files) == 1:
            path = Path(self.selected_files[0])

            self._unresolved_single_fields.clear()
            self.current_metadata = metadatas[0]

            self.multi_edit_fields.clear()
            self.multi_edit_artwork = False
            self.artwork_edited = False

            self.pending_artwork = self.current_metadata.artwork
            self.pending_artwork_mime = self.current_metadata.artwork_mime

            self._show_metadata(self.current_metadata)

            self.file_list.update_file_metadata(
                path,
                self.current_metadata,
            )

            self._update_multi_edit_visuals()

            self.statusBar().showMessage("Changes undone")

    def closeEvent(self, event):
        if not self._has_unsaved_changes():
            event.accept()
            return

        target = (
            f"{len(self.selected_files)} files"
            if len(self.selected_files) > 1 else self.current_file.name
        )
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"You have unsaved changes to:\n\n"
            f"{target}\n\n"
            "Do you want to save them before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if reply == QMessageBox.StandardButton.Save:
            self._save_changes()

            if self._has_unsaved_changes():
                event.ignore()
            else:
                event.accept()

        elif reply == QMessageBox.StandardButton.Discard:
            event.accept()

        else:
            event.ignore()

    def _show_artwork_preview(self, artwork):
        """Render artwork bytes, or clear the preview for absent/invalid artwork."""
        self.artwork_label.clear()
        if artwork:
            decoded = decode_artwork(artwork)
            if decoded is not None:
                image, _ = decoded
                self.artwork_label.setPixmap(
                    QPixmap.fromImage(image).scaled(
                        self.artwork_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

    def _choose_artwork(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Artwork",
            "",
            "Images (*.jpg *.jpeg *.png)",
        )

        if not path:
            return

        try:
            with open(path, "rb") as file:
                artwork = file.read()
        except OSError as exc:
            QMessageBox.critical(
                self, "Artwork Read Failed",
                f"Could not read the selected artwork file:\n{path}\n\n{exc}",
            )
            return

        decoded = decode_artwork(artwork)

        if decoded is None:
            QMessageBox.warning(
                self,
                "Invalid Artwork",
                f"The selected file is not a valid JPEG or PNG image:\n{path}",
            )
            return

        self.pending_artwork = artwork
        self.artwork_edited = True

        self.pending_artwork_mime = decoded[1]

        self._show_artwork_preview(artwork)

        if len(self.selected_files) > 1:
            self.multi_edit_artwork = True
            self._update_multi_edit_visuals()
        self._update_dirty_indicators()

    def _remove_artwork(self):
        if len(self.selected_files) <= 1 and self.current_metadata is None:
            return

        if len(self.selected_files) > 1:
            try:
                metadatas = [read_metadata(Path(path)) for path in self.selected_files]
            except MetadataReadError as exc:
                QMessageBox.critical(self, "Read Failed", str(exc))
                return

        self.pending_artwork = None
        self.pending_artwork_mime = ""

        if len(self.selected_files) > 1:
            self.multi_edit_artwork = any(metadata.artwork is not None for metadata in metadatas)
            self.artwork_edited = self.multi_edit_artwork
        else:
            self.artwork_edited = self.current_metadata.artwork is not None
        self._show_artwork_preview(None)
        self._update_multi_edit_visuals()

    def _common_metadata_value(self, metadatas, attribute):
        if not metadatas:
            return None, False

        values = [
            getattr(metadata, attribute)
            for metadata in metadatas
        ]

        if all(value == values[0] for value in values):
            return values[0], True

        return None, False

    def _show_common_metadata(self, metadatas):
        self._per_file_edits.clear()
        self._unresolved_per_file_fields.clear()
        # Only called with successfully loaded metadata for an accepted context.
        self._unresolved_single_fields.clear()
        self._unresolved_multi_fields.clear()
        # Accepted scalar values only: no disk reads while the user edits.
        # A missing field means an attempted save has not been verified.
        self._multi_field_baselines = {
            Path(path): {field: getattr(metadata, field)
                         for field in self.metadata_panel.field_names}
            for path, metadata in zip(self.selected_files, metadatas)
        }
        self.metadata_panel.set_existing_values(tuple(self._multi_field_baselines.values()))
        self.metadata_panel.set_id3v1_comment_enabled(
            bool(self.selected_files)
            and all(Path(path).suffix.lower() == ".mp3" for path in self.selected_files)
        )
        self.multi_edit_fields.clear()
        self._update_multi_edit_visuals()

        values = {}
        mixed_fields = set()
        for field in self.metadata_panel.field_names:
            value, is_common = self._common_metadata_value(metadatas, field)
            values[field] = value
            if not is_common:
                mixed_fields.add(field)
        self.metadata_panel.set_field_values(values, mixed_fields=mixed_fields)

        artwork_values = [
            metadata.artwork
            for metadata in metadatas
        ]

        if all(artwork is not None for artwork in artwork_values):
            artwork_text = "Multiple artworks"
        elif all(artwork is None for artwork in artwork_values):
            artwork_text = "No artwork"
        else:
            artwork_text = "Mixed artwork"

        self.artwork_label.clear()
        self.artwork_label.setText(artwork_text)

    def _connect_multi_edit_tracking(self):
        self.metadata_panel.field_edited.connect(self._metadata_field_edited)
        self.metadata_panel.values_changed.connect(self._update_multi_edit_visuals)

    def _metadata_field_edited(self, field):
        self._supersede_per_file(field)
        if len(self.selected_files) > 1:
            self.multi_edit_fields.add(field)
            self._update_multi_edit_visuals()

    def _update_multi_edit_visuals(self):
        unresolved_scalars = self._unresolved_multi_fields - {"artwork"}
        if "artwork" in self._unresolved_multi_fields:
            self.multi_edit_artwork = self.artwork_edited = True
        if self.multi_edit_fields or unresolved_scalars:
            effective = effective_multi_fields(
                self.multi_edit_fields,
                self._get_edited_metadata(),
                tuple(self._multi_field_baselines.values()),
                invalid_fields=self._invalid_numeric_fields(),
                unresolved_fields=unresolved_scalars,
            )
            self.multi_edit_fields.clear()
            self.multi_edit_fields.update(effective)
        per_file_fields = set().union(*(self._per_file_changes(Path(p)) for p in self.selected_files))
        self.metadata_panel.set_highlighted_fields(self.multi_edit_fields | per_file_fields)

        if len(self.selected_files) > 1:
            field_count = len(self.multi_edit_fields | per_file_fields)

            if self.multi_edit_artwork:
                field_count += 1

            file_word = "file" if len(self.selected_files) == 1 else "files"
            field_word = "field" if field_count == 1 else "fields"

            self.statusBar().showMessage(
                f"{len(self.selected_files)} {file_word} selected — "
                f"{field_count} {field_word} will be changed"
            )
        self._update_dirty_indicators()

    def _multi_edit_field_names(self):
        names = {
            "title": "Title",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Album Artist",
            "genre": "Genre",
            "track_number": "Track",
            "track_total": "Track Total",
            "disc_number": "Disc",
            "disc_total": "Disc Total",
            "narrator": "Narrator",
            "series": "Series",
            "series_number": "Series Number",
            "publisher": "Publisher",
            "date": "Date",
            "composer": "Composer",
            "comment": "Comment",
            "id3v1_comment": "ID3v1 Comment",
            "copyright": "Copyright",
            "description": "Description",
        }

        field_names = [
            names[field]
            for field in self.multi_edit_fields
            if field in names
        ]

        if self.multi_edit_artwork:
            field_names.append("Artwork")

        return field_names

    def _numeric_errors(self):
        return {
            name: error
            for name, text in self.metadata_panel.numeric_field_texts().items()
            if (error := _numeric_validation_error(text)) is not None
        }

    def _invalid_numeric_fields(self):
        numeric_fields = {"Track": "track_number", "Track Total": "track_total",
                          "Disc": "disc_number", "Disc Total": "disc_total"}
        return {numeric_fields[name] for name in self._numeric_errors()}

    def _validate_numeric_fields(self):
        for name, error in self._numeric_errors().items():
            QMessageBox.warning(self, "Invalid Number", f"{name} {error}")
            self.metadata_panel.focus_numeric_field(name)
            return False
        return True

    def _copy_metadata(self):
        if len(self.selected_files) != 1:
            QMessageBox.information(
                self,
                "Copy Metadata",
                "Select exactly one file to copy metadata from.",
            )
            return

        try:
            metadata = read_metadata(Path(self.selected_files[0]))
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Copy Failed", str(exc))
            return
        self.metadata_clipboard = metadata

        self.statusBar().showMessage(
            f"Metadata copied from {Path(self.selected_files[0]).name}"
        )

    def _paste_metadata(self):
        if self.metadata_clipboard is None:
            QMessageBox.information(
                self,
                "Paste Metadata",
                "No metadata has been copied.",
            )
            return

        if not self.selected_files:
            QMessageBox.information(
                self,
                "Paste Metadata",
                "Select at least one target file.",
            )
            return

        fields = {
            "title": "Title",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Album Artist",
            "genre": "Genre",
            "track_number": "Track",
            "track_total": "Track Total",
            "disc_number": "Disc",
            "disc_total": "Disc Total",
            "narrator": "Narrator",
            "series": "Series",
            "series_number": "Series Number",
            "publisher": "Publisher",
            "date": "Date",
            "composer": "Composer",
            "comment": "Comment",
            "id3v1_comment": "ID3v1 Comment",
            "copyright": "Copyright",
            "description": "Description",
            "artwork": "Artwork",
        }

        dialog = PasteFieldsDialog(fields, self.paste_metadata_fields, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_fields = dialog.selected_fields

        self.paste_metadata_fields = selected_fields.copy()

        if not selected_fields:
            QMessageBox.information(
                self,
                "Paste Metadata",
                "No fields were selected.",
            )
            return

        try:
            metadatas = [read_metadata(Path(path)) for path in self.selected_files]
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Paste Failed", str(exc))
            return

        if "artwork" in selected_fields:
            self.artwork_edited = (
                self.metadata_clipboard.artwork is not None
                or any(metadata.artwork is not None for metadata in metadatas)
            )
            self.pending_artwork = self.metadata_clipboard.artwork
            self.pending_artwork_mime = (
                self.metadata_clipboard.artwork_mime if self.pending_artwork is not None else ""
            )
            if len(self.selected_files) > 1:
                self.multi_edit_artwork = self.artwork_edited

            # Preview pending artwork without saving or repopulating text edits.
            self._show_artwork_preview(self.pending_artwork)

            selected_fields.remove("artwork")

        for field in selected_fields:
            self._supersede_per_file(field)
        if len(self.selected_files) > 1:
            self.multi_edit_fields.update(selected_fields)

        self._show_pasted_metadata(selected_fields)

        for path_string, metadata in zip(self.selected_files, metadatas):
            path = Path(path_string)

            for field in selected_fields:
                setattr(
                    metadata,
                    field,
                    getattr(self.metadata_clipboard, field),
                )

            self.file_list.update_file_metadata(
                path,
                metadata,
            )

        self._render_per_file_edits()
        self._update_multi_edit_visuals()

    def _show_pasted_metadata(self, selected_fields):
        self.metadata_panel.set_field_values({
            field: getattr(self.metadata_clipboard, field)
            for field in selected_fields
            if field in self.metadata_panel.field_names
        })

    def _create_shortcuts(self):
        QShortcut(
            QKeySequence("Ctrl+S"),
            self,
        ).activated.connect(self._save_changes)

        QShortcut(
            QKeySequence("Ctrl+Shift+C"),
            self,
        ).activated.connect(self._copy_metadata)

        QShortcut(
            QKeySequence("Ctrl+Shift+V"),
            self,
        ).activated.connect(self._paste_metadata)

    def keyPressEvent(self, event):
        if (
            event.key() == Qt.Key.Key_Z
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            focused = self.focusWidget()

            text_widgets = (
                QLineEdit,
                QPlainTextEdit,
            )

            if isinstance(focused, text_widgets):
                super().keyPressEvent(event)
                return

            self._undo_changes()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Delete:
            focused = self.focusWidget()

            text_widgets = (
                QLineEdit,
                QPlainTextEdit,
            )

            if isinstance(focused, text_widgets):
                super().keyPressEvent(event)
                return

            self._remove_artwork()
            event.accept()
            return

        super().keyPressEvent(event)

    def _metadata_cell_edited(self, path, column, value):
        # Table edits are handled by the immediate-save workflow.
        # Do not copy them into the Metadata panel, because that
        # would incorrectly mark the file as having unsaved changes.
        return

    def _update_dirty_indicators(self):
        dirty_paths = []

        if len(self.selected_files) > 1:
            # Unresolved multi-save state is selection-wide, not per target.
            # Cached equality cannot establish cleanliness after an uncertain save.
            if self._numeric_errors() or self._unresolved_multi_fields:
                dirty_paths = self.selected_files.copy()
            else:
                edited = self._get_edited_metadata()
                dirty_paths = [
                    path for path in self.selected_files
                    if effective_fields_for_target(
                        self.multi_edit_fields, edited,
                        self._multi_field_baselines.get(Path(path), {}),
                    )
                ]
                if self.multi_edit_artwork:
                    try:
                        dirty_paths.extend(
                            path for path in self.selected_files
                            if self.pending_artwork is not None
                            or read_metadata(Path(path)).artwork is not None
                        )
                    except MetadataReadError as exc:
                        self.statusBar().showMessage(str(exc))
                        return

        elif self.current_file is not None and self._has_unsaved_changes():
            dirty_paths = [self.current_file]

        dirty_paths.extend(path for path in self.selected_files if self._per_file_changes(Path(path)))
        dirty_paths.extend(self._unverified_fields)
        self.file_list.set_dirty_files(dirty_paths)
        self.file_list.set_pending_previews(self._per_file_edits)

    def _save_table_cell(self, path_string, column, value):
        self.file_list.cell_save_succeeded = False
        path = Path(path_string)

        field = TABLE_FIELDS.get(column)
        if field is None:
            return

        try:
            if field == "track_number":
                value = int(value) if value.strip() else None
            self._save_metadata_field(path, field, value)
            self.file_list.cell_save_succeeded = True

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Immediate Save Failed",
                f"Could not save the metadata for:\n{path.name}\n\n{exc}",
            )

            # Restore the table display from the file on disk.
            try:
                disk_metadata = read_metadata(path)
                self.file_list.update_file_metadata(path, disk_metadata)
            except Exception:
                pass
            self._render_per_file_edits()

    def _verify_field_saves(self, paths=None):
        """Accept disk truth for immediate writes, without replaying them.

        Writer-exception recovery can restrict verification to its affected path.
        """
        paths = self._unverified_fields if paths is None else paths
        verified = {path: self._read_after_write(path) for path in paths}
        common_updates = {}
        mixed_fields = set()
        if verified and len(self.selected_files) > 1:
            metadatas = [self._read_after_write(Path(path)) for path in self.selected_files]
            fields = set().union(*(self._unverified_fields[path] for path in verified))
            for field in fields - self.multi_edit_fields - set().union(*(set(v) for v in self._per_file_edits.values())):
                value, common = self._common_metadata_value(metadatas, field)
                common_updates[field] = value
                if not common:
                    mixed_fields.add(field)
        for path, metadata in verified.items():
            fields = self._unverified_fields[path]
            if path in self._multi_field_baselines:
                for field in fields:
                    self._multi_field_baselines[path][field] = getattr(metadata, field)
            if self.current_file == path and self.current_metadata is not None:
                edited = self._get_edited_metadata()
                unchanged = {
                    field for field in fields - self._invalid_numeric_fields()
                    - self._unresolved_single_fields - set(self._per_file_edits.get(path, {}))
                    if getattr(edited, field) == getattr(self.current_metadata, field)
                }
                for field in fields:
                    setattr(self.current_metadata, field, getattr(metadata, field))
                if len(self.selected_files) == 1:
                    self.metadata_panel.set_field_values(
                        {field: getattr(metadata, field) for field in unchanged}
                    )
            self.file_list.update_file_metadata(path, metadata)
            del self._unverified_fields[path]
        if verified:
            self.metadata_panel.set_existing_values(tuple(self._multi_field_baselines.values()))
            self.metadata_panel.set_field_values(common_updates, mixed_fields=mixed_fields)
            self._render_per_file_edits()
            self._update_dirty_indicators()

        return verified

    def _read_after_write(self, path):
        try:
            return read_metadata(path)
        except MetadataReadError as exc:
            raise MetadataReadError(
                path, f"Write may have succeeded, but readback failed. "
                f"No rollback was attempted. {exc}"
            ) from exc

    def _save_metadata_field(self, path, field, value):
        """Persist one field and synchronize only its panel baseline."""
        metadata = read_metadata(path)
        previous_value = getattr(metadata, field)
        if previous_value != value:
            setattr(metadata, field, value)
            # Invocation may modify disk even if the writer subsequently raises.
            self._unverified_fields.setdefault(path, set()).add(field)
            try:
                write_metadata(path, metadata, fields={field})
            except Exception as exc:
                self._update_dirty_indicators()
                try:
                    verified = self._verify_field_saves((path,))
                except MetadataReadError as recovery_error:
                    outcome = (
                        "The file may have changed. Recovery could not verify the file; "
                        f"the field remains unresolved.\n{recovery_error}"
                    )
                else:
                    actual = getattr(verified[path], field)
                    if actual == value:
                        outcome = "Recovery read found the requested field value."
                    elif actual == previous_value:
                        outcome = "Recovery read found the pre-write field value."
                    else:
                        outcome = "Recovery read found a different field value; accepted current disk state."
                # Even a verified requested value does not turn a writer failure
                # into successful Enter navigation or further Auto-number writes.
                raise RuntimeError(
                    f"Write operation failed: {exc}\n{outcome}\nNo rollback was attempted."
                ) from exc
        try:
            metadata = self._read_after_write(path)
        except MetadataReadError:
            self._unverified_fields.setdefault(path, set()).add(field)
            self._update_dirty_indicators()
            raise
        unverified = self._unverified_fields.get(path, set())
        unverified.discard(field)
        if not unverified:
            self._unverified_fields.pop(path, None)
        saved_value = getattr(metadata, field)
        if path in self._multi_field_baselines:
            self._multi_field_baselines[path][field] = saved_value
            self.metadata_panel.set_existing_values(tuple(self._multi_field_baselines.values()))
        if self.current_file == path and self.current_metadata is not None:
            setattr(self.current_metadata, field, saved_value)
            if len(self.selected_files) == 1:
                self.metadata_panel.set_field_values({field: saved_value})
                self._unresolved_single_fields.discard(field)
        self._per_file_edits.get(path, {}).pop(field, None)
        self._unresolved_per_file_fields.get(path, set()).discard(field)
        self.file_list.update_file_metadata(path, metadata)
        self._render_per_file_edits()
        self._update_dirty_indicators()

    def _auto_number_tracks(self):
        paths = self.file_list.selected_paths_in_row_order()
        if not paths:
            QMessageBox.information(
                self, "Auto-number Tracks", "Select at least one file to number."
            )
            return

        dialog = AutoNumberDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        start = dialog.starting_number

        # Freeze sorting while rows and dirty indicators are refreshed. The path
        # snapshot also keeps numbering independent of changes to the sort column.
        sorting = self.file_list.isSortingEnabled()
        self.file_list.setSortingEnabled(False)
        saved = 0
        try:
            for number, path in enumerate(paths, start):
                try:
                    self._save_metadata_field(Path(path), "track_number", number)
                    saved += 1
                    if len(self.selected_files) > 1 and "track_number" not in self.multi_edit_fields:
                        self._refresh_selected_tracks()
                except Exception as exc:
                    QMessageBox.critical(
                        self, "Auto-number Tracks Failed",
                        f"Could not number:\n{path}\n\n{exc}\n\n"
                        f"{saved} file(s) saved and verified before this failure.\n"
                        "Current file outcome is described above; later files were not attempted.",
                    )
                    return
            if len(self.selected_files) > 1:
                self._refresh_selected_tracks()
                # Preserve Auto-number's existing successful Track-intent reset.
                self._unresolved_multi_fields.discard("track_number")
                self.multi_edit_fields.discard("track_number")
                self._update_multi_edit_visuals()
            self.statusBar().showMessage(f"Auto-numbered {saved} file(s).")
        except MetadataReadError as exc:
            QMessageBox.critical(self, "Auto-number Readback Failed",
                                 f"{saved} file(s) saved. No rollback was attempted.\n\n{exc}")
        finally:
            self.file_list.setSortingEnabled(sorting)

    def _refresh_selected_tracks(self):
        metadatas = [read_metadata(Path(path)) for path in self.selected_files]
        value, common = self._common_metadata_value(metadatas, "track_number")
        self.metadata_panel.set_field_values(
            {"track_number": value},
            mixed_fields=() if common else {"track_number"},
        )
