from dataclasses import fields as metadata_fields
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QSignalBlocker,
    QItemSelectionModel,
    QPersistentModelIndex,
)
from PySide6.QtGui import (
    QImage,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
)

from ..metadata.writer import write_metadata
from .dialogs.auto_number_dialog import AutoNumberDialog
from .dialogs.paste_fields_dialog import PasteFieldsDialog
from .file_list import FileList
from .metadata_panel import MetadataPanel
from ..metadata import (
    read_metadata,
    write_mp3_metadata,
    write_m4b_metadata,
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Audio Metadata Editor")
        self.resize(1200, 700)

        self.root_path = None
        self.current_file = None
        self.selected_files = []
        self._context_index = QPersistentModelIndex()
        self.multi_edit_fields = set()
        self.current_metadata = None
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

    def _create_main_layout(self):
        splitter = QSplitter()

        # Directory tree
        self.directory_tree = QTreeWidget()
        self.directory_tree.setHeaderLabel("Folders")
        self.directory_tree.itemExpanded.connect(self._populate_directory)
        self.directory_tree.itemClicked.connect(self._directory_selected)

        splitter.addWidget(self.directory_tree)

        # File list
        self.file_list = FileList()
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

        splitter.addWidget(self.metadata_panel)

        splitter.setSizes([250, 600, 350])

        self.setCentralWidget(splitter)
        self._connect_multi_edit_tracking()

    def _files_selected(self, paths):
        if set(paths) == set(self.selected_files):
            return True
        if not self._guard_selection_change():
            return False
        if len(paths) == 1:
            self._load_single_file(paths[0])
        elif paths:
            self.selected_files = list(paths)
            self.multi_edit_artwork = False
            self.artwork_edited = False
            self.pending_artwork = None
            self.pending_artwork_mime = ""
            self._show_common_metadata([read_metadata(Path(path)) for path in paths])
        self._context_index = QPersistentModelIndex(self.file_list.currentIndex())
        return True

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
            return True
        with QSignalBlocker(self.file_list):
            self.file_list.select_files(self.selected_files)
            if self._context_index.isValid():
                self.file_list.setCurrentCell(
                    self._context_index.row(), self._context_index.column(),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
        return False

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
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Audiobook Folder",
        )

        if not directory:
            return

        self.root_path = Path(directory)

        self._populate_root()

        self.status_label.setText(str(self.root_path))

    def _populate_root(self):
        self.directory_tree.clear()

        root_item = QTreeWidgetItem(
            [self.root_path.name or str(self.root_path)]
        )

        root_item.setData(0, 256, str(self.root_path))

        self.directory_tree.addTopLevelItem(root_item)

        self._add_placeholder(root_item)

        root_item.setExpanded(True)

        self.directory_tree.setCurrentItem(root_item)
        root_item.setSelected(True)

        self._directory_selected(root_item, 0)

    def _populate_directory(self, item):
        path = Path(item.data(0, 256))

        if not path.is_dir():
            return

        # Remove the placeholder item.
        while item.childCount():
            child = item.takeChild(0)

            if child.data(0, 256) is not None:
                item.addChild(child)
                break

        # Don't repopulate an already populated directory.
        if item.childCount() > 0:
            return

        try:
            directories = sorted(
                (
                    entry
                    for entry in path.iterdir()
                    if entry.is_dir() and not entry.name.startswith(".")
                ),
                key=lambda entry: entry.name.lower(),
            )
        except OSError:
            return

        for directory in directories:
            child = QTreeWidgetItem([directory.name])
            child.setData(0, 256, str(directory))

            if self._contains_directory(directory):
                self._add_placeholder(child)

            item.addChild(child)

    def _add_placeholder(self, item):
        placeholder = QTreeWidgetItem([""])
        item.addChild(placeholder)

    def _contains_directory(self, path):
        try:
            return any(
                entry.is_dir() and not entry.name.startswith(".")
                for entry in path.iterdir()
            )
        except OSError:
            return False

    def _directory_selected(self, item, column):
        path = item.data(0, 256)

        if not path:
            return

        directory = Path(path)

        self.status_label.setText(str(directory))

        self.file_list.load_directory(directory)

    def _refresh_tree(self):
        if self.root_path is not None:
            self._populate_root()

    def _show_metadata(self, metadata):
        self.metadata_panel.set_metadata(metadata)
        self._show_artwork_preview(metadata.artwork)
        self.id3v1_comment_edit.setEnabled(
            self.current_file is not None
            and self.current_file.suffix.lower() == ".mp3"
        )

    def _file_selected(self, path):
        # Retain the direct single-file entry point used by explicit reloads.
        if set(self.selected_files) != {path} and not self._guard_selection_change():
            return
        self._load_single_file(path)

    def _load_single_file(self, path):
        new_file = Path(path)
        self.selected_files = [path]
        self.current_file = new_file
        self._context_index = QPersistentModelIndex(self.file_list.currentIndex())

        metadata = read_metadata(new_file)
        self.current_metadata = metadata
        self.pending_artwork = metadata.artwork
        self.pending_artwork_mime = metadata.artwork_mime
        self.artwork_edited = False

        self.multi_edit_fields.clear()
        self.multi_edit_artwork = False

        self._show_metadata(metadata)
        self._update_multi_edit_visuals()

    def _get_edited_metadata(self):
        metadata = self.metadata_panel.collect_metadata()
        metadata.artwork = self.pending_artwork
        metadata.artwork_mime = self.pending_artwork_mime
        return metadata

    def _save_changes(self):
        if not self._validate_numeric_fields():
            return

        if not self.selected_files:
            QMessageBox.warning(
                self,
                "No Files Selected",
                "No files are selected.",
            )
            return

        # Multi-file editing
        if len(self.selected_files) > 1:
            if not self.multi_edit_fields and not self.multi_edit_artwork:
                QMessageBox.information(
                    self,
                    "No Changes",
                    "No metadata fields or artwork have been changed.",
                )
                return

            edited_metadata = self._get_edited_metadata()

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

                    artwork_options = {}
                    if self.multi_edit_artwork and (
                        self.pending_artwork is not None or metadata.artwork is not None
                    ):
                        artwork_options = {
                            "artwork": self.pending_artwork,
                            "artwork_mime": self.pending_artwork_mime,
                        }

                    if not self.multi_edit_fields and not artwork_options:
                        continue

                    suffix = path.suffix.lower()

                    if suffix == ".mp3":
                        write_mp3_metadata(
                            path,
                            metadata,
                            fields=self.multi_edit_fields,
                            **artwork_options,
                        )
                    elif suffix == ".m4b":
                        write_m4b_metadata(
                            path,
                            metadata,
                            fields=self.multi_edit_fields,
                            **artwork_options,
                        )

                    metadata = read_metadata(path)
                    if self.current_file == path:
                        self.current_metadata = metadata
                    self.file_list.update_file_metadata(
                        path,
                        metadata,
                    )

            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Could not save the selected files:\n\n{exc}",
                )
                return

            self.multi_edit_fields.clear()
            self.multi_edit_artwork = False
            self.artwork_edited = False

            QMessageBox.information(
                self,
                "Saved",
                f"Saved changes to {len(self.selected_files)} files.",
            )

            # Refresh the multi-file display.
            metadatas = [
                read_metadata(Path(path))
                for path in self.selected_files
            ]

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
        changed_fields = {
            field.name for field in metadata_fields(metadata)
            if field.name not in {"artwork", "artwork_mime"}
            and getattr(metadata, field.name) != getattr(self.current_metadata, field.name)
        }
        artwork_options = {}
        if (
            self.artwork_edited
            or self.pending_artwork != self.current_metadata.artwork
            or self.pending_artwork_mime != self.current_metadata.artwork_mime
        ):
            artwork_options = {
                "artwork": self.pending_artwork,
                "artwork_mime": self.pending_artwork_mime,
            }

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

            metadata = read_metadata(self.current_file)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save the file:\n\n{exc}",
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

        self._update_dirty_indicators()

        QMessageBox.information(
            self,
            "Saved",
            f"Saved changes to {self.current_file.name}.",
        )

    def _has_unsaved_changes(self):
        if len(self.selected_files) > 1:
            return bool(
                self.multi_edit_fields
                or self.multi_edit_artwork
            )

        if self.current_metadata is None:
            return False

        edited = self._get_edited_metadata()
        loaded = self.current_metadata

        return (
            self.artwork_edited
            or edited.title != loaded.title
            or edited.artist != loaded.artist
            or edited.album != loaded.album
            or edited.album_artist != loaded.album_artist
            or edited.genre != loaded.genre
            or edited.track_number != loaded.track_number
            or edited.track_total != loaded.track_total
            or edited.disc_number != loaded.disc_number
            or edited.disc_total != loaded.disc_total
            or edited.date != loaded.date
            or edited.composer != loaded.composer
            or edited.comment != loaded.comment
            or edited.id3v1_comment != loaded.id3v1_comment
            or edited.copyright != loaded.copyright
            or edited.description != loaded.description
            or edited.publisher != loaded.publisher
            or edited.narrator != loaded.narrator
            or edited.series != loaded.series
            or edited.series_number != loaded.series_number
            or self.pending_artwork != loaded.artwork
            or self.pending_artwork_mime != loaded.artwork_mime
        )

    def _undo_changes(self):
        if not self._has_unsaved_changes():
            self.statusBar().showMessage("No Changes")
            return

        if len(self.selected_files) > 1:
            metadatas = [
                read_metadata(Path(path))
                for path in self.selected_files
            ]

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

            self.current_metadata = read_metadata(path)

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

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"You have unsaved changes to:\n\n"
            f"{self.current_file.name}\n\n"
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
            image = QImage.fromData(artwork)
            if not image.isNull():
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

        with open(path, "rb") as file:
            artwork = file.read()

        image = QImage.fromData(artwork)

        if image.isNull():
            QMessageBox.warning(
                self,
                "Invalid Artwork",
                "The selected file is not a valid image.",
            )
            return

        self.pending_artwork = artwork
        self.artwork_edited = True

        if path.lower().endswith(".png"):
            self.pending_artwork_mime = "image/png"
        else:
            self.pending_artwork_mime = "image/jpeg"

        self._show_artwork_preview(artwork)

        if len(self.selected_files) > 1:
            self.multi_edit_artwork = True
            self._update_multi_edit_visuals()
        self._update_dirty_indicators()

    def _remove_artwork(self):
        if self.current_metadata is None:
            return

        self.pending_artwork = None
        self.pending_artwork_mime = ""

        if len(self.selected_files) > 1:
            self.multi_edit_artwork = any(
                read_metadata(Path(path)).artwork is not None
                for path in self.selected_files
            )
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
        self.metadata_panel.values_changed.connect(self._update_dirty_indicators)

    def _metadata_field_edited(self, field):
        if len(self.selected_files) > 1:
            self.multi_edit_fields.add(field)
            self._update_multi_edit_visuals()

    def _update_multi_edit_visuals(self):
        self.metadata_panel.set_highlighted_fields(self.multi_edit_fields)

        if len(self.selected_files) > 1:
            field_count = len(self.multi_edit_fields)

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

    def _validate_numeric_fields(self):
        fields = {
            "Track": self.track_edit,
            "Track Total": self.track_total_edit,
            "Disc": self.disc_edit,
            "Disc Total": self.disc_total_edit,
        }

        for name, widget in fields.items():
            text = widget.text().strip()

            if not text:
                continue

            try:
                value = int(text)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid Number",
                    f"{name} must be a whole number.",
                )
                widget.setFocus()
                widget.selectAll()
                return False

            if value < 0:
                QMessageBox.warning(
                    self,
                    "Invalid Number",
                    f"{name} cannot be negative.",
                )
                widget.setFocus()
                widget.selectAll()
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

        self.metadata_clipboard = read_metadata(
            Path(self.selected_files[0])
        )

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

        if "artwork" in selected_fields:
            self.artwork_edited = True
            self.pending_artwork = self.metadata_clipboard.artwork
            self.pending_artwork_mime = (
                self.metadata_clipboard.artwork_mime
            )
            if len(self.selected_files) > 1:
                self.multi_edit_artwork = True

            # Preview pending artwork without saving or repopulating text edits.
            self._show_artwork_preview(self.pending_artwork)

            selected_fields.remove("artwork")

        if len(self.selected_files) > 1:
            self.multi_edit_fields.update(selected_fields)

        self._show_pasted_metadata(selected_fields)

        for path_string in self.selected_files:
            path = Path(path_string)
            metadata = read_metadata(path)

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
            if self.multi_edit_fields:
                dirty_paths = self.selected_files.copy()
            elif self.multi_edit_artwork:
                dirty_paths = [
                    path for path in self.selected_files
                    if self.pending_artwork is not None
                    or read_metadata(Path(path)).artwork is not None
                ]

        elif self.current_file is not None and self._has_unsaved_changes():
            dirty_paths = [self.current_file]

        self.file_list.set_dirty_files(dirty_paths)

    def _save_table_cell(self, path_string, column, value):
        self.file_list.cell_save_succeeded = False
        path = Path(path_string)

        fields = {
            1: "track_number",
            2: "title",
            3: "artist",
            4: "album",
            5: "series",
            6: "series_number",
            7: "narrator",
        }

        field = fields.get(column)
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

    def _save_metadata_field(self, path, field, value):
        """Persist one field and synchronize only its panel baseline."""
        metadata = read_metadata(path)
        if getattr(metadata, field) != value:
            setattr(metadata, field, value)
            write_metadata(path, metadata, fields={field})
        metadata = read_metadata(path)
        saved_value = getattr(metadata, field)
        if self.current_file == path and self.current_metadata is not None:
            setattr(self.current_metadata, field, saved_value)
            if len(self.selected_files) == 1:
                self.metadata_panel.set_field_values({field: saved_value})
        self.file_list.update_file_metadata(path, metadata)
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
                        f"{saved} file(s) saved. Remaining files were not processed.",
                    )
                    return
            if len(self.selected_files) > 1:
                self.multi_edit_fields.discard("track_number")
                self._refresh_selected_tracks()
                self._update_multi_edit_visuals()
            self.statusBar().showMessage(f"Auto-numbered {saved} file(s).")
        finally:
            self.file_list.setSortingEnabled(sorting)

    def _refresh_selected_tracks(self):
        metadatas = [read_metadata(Path(path)) for path in self.selected_files]
        value, common = self._common_metadata_value(metadatas, "track_number")
        self.metadata_panel.set_field_values(
            {"track_number": value},
            mixed_fields=() if common else {"track_number"},
        )
