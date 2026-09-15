from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QSignalBlocker,
)
from PySide6.QtGui import (
    QImage,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
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
    QVBoxLayout,
    QWidget,
)

from .file_list import FileList
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
        self.multi_edit_fields = set()
        self.current_metadata = None
        self.pending_artwork = None
        self.pending_artwork_mime = ""
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
        self.file_list.file_selected.connect(self._file_selected)
        self.file_list.files_selected.connect(self._files_selected)
        splitter.addWidget(self.file_list)

        # Metadata panel
        metadata_widget = QWidget()
        metadata_layout = QVBoxLayout(metadata_widget)

        title = QLabel("Metadata")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")

        metadata_layout.addWidget(title)

        self.artwork_label = QLabel()
        self.artwork_label.setFixedSize(250, 250)
        self.artwork_label.setScaledContents(False)
        self.artwork_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        metadata_layout.addWidget(self.artwork_label)

        self.choose_artwork_button = QPushButton("Choose Artwork")
        self.remove_artwork_button = QPushButton("Remove Artwork")

        metadata_layout.addWidget(self.choose_artwork_button)
        metadata_layout.addWidget(self.remove_artwork_button)

        self.choose_artwork_button.clicked.connect(self._choose_artwork)
        self.remove_artwork_button.clicked.connect(self._remove_artwork)

        form = QFormLayout()

        self.title_edit = QLineEdit()
        self.artist_edit = QLineEdit()
        self.album_edit = QLineEdit()
        self.album_artist_edit = QLineEdit()
        self.genre_edit = QLineEdit()
        self.track_edit = QLineEdit()
        self.track_total_edit = QLineEdit()
        self.disc_edit = QLineEdit()
        self.disc_total_edit = QLineEdit()
        self.narrator_edit = QLineEdit()
        self.series_edit = QLineEdit()
        self.series_number_edit = QLineEdit()
        self.publisher_edit = QLineEdit()
        self.date_edit = QLineEdit()
        self.composer_edit = QLineEdit()
        self.comment_edit = QLineEdit()
        self.id3v1_comment_edit = QLineEdit()
        self.copyright_edit = QLineEdit()
        self.description_edit = QPlainTextEdit()
        self.description_edit.setMaximumHeight(120)

        form.addRow("Title", self.title_edit)
        form.addRow("Artist", self.artist_edit)
        form.addRow("Album", self.album_edit)
        form.addRow("Album Artist", self.album_artist_edit)
        form.addRow("Genre", self.genre_edit)
        form.addRow("Track", self.track_edit)
        form.addRow("Track Total", self.track_total_edit)
        form.addRow("Disc", self.disc_edit)
        form.addRow("Disc Total", self.disc_total_edit)
        form.addRow("Narrator", self.narrator_edit)
        form.addRow("Series", self.series_edit)
        form.addRow("Series Number", self.series_number_edit)
        form.addRow("Publisher", self.publisher_edit)
        form.addRow("Date", self.date_edit)
        form.addRow("Composer", self.composer_edit)
        form.addRow("Comment", self.comment_edit)
        form.addRow("ID3v1 Comment", self.id3v1_comment_edit)
        form.addRow("Copyright", self.copyright_edit)
        form.addRow("Description", self.description_edit)

        metadata_layout.addLayout(form)
        metadata_layout.addStretch()

        splitter.addWidget(metadata_widget)

        splitter.setSizes([250, 600, 350])

        self.setCentralWidget(splitter)
        self._connect_multi_edit_tracking()

    def _files_selected(self, paths):
        if len(paths) <= 1:
            self.statusBar().clearMessage()
            return

        self.selected_files = paths

        metadatas = [
            read_metadata(Path(path))
            for path in paths
        ]

        self.statusBar().showMessage(
            f"{len(paths)} files selected"
        )

        self._show_common_metadata(metadatas)

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
        widgets = (
            self.title_edit,
            self.artist_edit,
            self.album_edit,
            self.album_artist_edit,
            self.genre_edit,
            self.track_edit,
            self.track_total_edit,
            self.disc_edit,
            self.disc_total_edit,
            self.narrator_edit,
            self.series_edit,
            self.series_number_edit,
            self.publisher_edit,
            self.date_edit,
            self.composer_edit,
            self.comment_edit,
            self.id3v1_comment_edit,
            self.copyright_edit,
            self.description_edit,
        )

        blockers = [
            QSignalBlocker(widget)
            for widget in widgets
        ]

        for widget in widgets:
            widget.setPlaceholderText("")

        if metadata.artwork:
            image = QImage.fromData(metadata.artwork)

            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                self.artwork_label.setPixmap(
                    pixmap.scaled(
                        self.artwork_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self.artwork_label.clear()
        else:
            self.artwork_label.clear()

        self.title_edit.setText(metadata.title)
        self.artist_edit.setText(metadata.artist)
        self.album_edit.setText(metadata.album)
        self.album_artist_edit.setText(metadata.album_artist)
        self.genre_edit.setText(metadata.genre)

        self.track_edit.setText(
            str(metadata.track_number)
            if metadata.track_number is not None
            else ""
        )

        self.track_total_edit.setText(
            str(metadata.track_total)
            if metadata.track_total is not None
            else ""
        )

        self.disc_edit.setText(
            str(metadata.disc_number)
            if metadata.disc_number is not None
            else ""
        )

        self.disc_total_edit.setText(
            str(metadata.disc_total)
            if metadata.disc_total is not None
            else ""
        )

        self.narrator_edit.setText(metadata.narrator)
        self.series_edit.setText(metadata.series)
        self.series_number_edit.setText(metadata.series_number)
        self.publisher_edit.setText(metadata.publisher)
        self.date_edit.setText(metadata.date)
        self.composer_edit.setText(metadata.composer)
        self.comment_edit.setText(metadata.comment)
        self.id3v1_comment_edit.setText(metadata.id3v1_comment)

        self.id3v1_comment_edit.setEnabled(
            self.current_file is not None
            and self.current_file.suffix.lower() == ".mp3"
        )

        self.copyright_edit.setText(metadata.copyright)
        self.description_edit.setPlainText(metadata.description)

    def _file_selected(self, path):
        previous_selection = self.selected_files.copy()

        new_file = Path(path)
        if (
            self.current_file is not None
            and new_file != self.current_file
        ):
            if self._has_unsaved_changes():
                if len(self.selected_files) > 1:
                    field_names = self._multi_edit_field_names()

                    message = (
                        f"You have unsaved changes to "
                        f"{len(self.selected_files)} selected files.\n\n"
                        f"Fields to be changed: {', '.join(field_names)}.\n\n"
                        "Do you want to save them before switching files?"
                    )
                else:
                    message = (
                        f"You have unsaved changes to:\n\n"
                        f"{self.current_file.name}\n\n"
                        "Do you want to save them before switching files?"
                    )

                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    message,
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                )

                if reply == QMessageBox.StandardButton.Save:
                    self._save_changes()

                    if self._has_unsaved_changes():
                        return

                elif reply == QMessageBox.StandardButton.Cancel:
                    self.file_list.select_files(previous_selection)
                    self.selected_files = previous_selection.copy()
                    return

        self.selected_files = [path]
        self.current_file = new_file

        metadata = read_metadata(new_file)
        self.current_metadata = metadata
        self.pending_artwork = metadata.artwork
        self.pending_artwork_mime = metadata.artwork_mime

        self.multi_edit_fields.clear()
        self.multi_edit_artwork = False
        self._update_multi_edit_visuals()

        self._show_metadata(metadata)

    def _get_edited_metadata(self):
        from audio_metadata_editor.metadata import Metadata

        def get_number(text):
            text = text.strip()

            if not text:
                return None

            try:
                return int(text)
            except ValueError:
                return None

        return Metadata(
            title=self.title_edit.text(),
            artist=self.artist_edit.text(),
            album=self.album_edit.text(),
            album_artist=self.album_artist_edit.text(),
            genre=self.genre_edit.text(),
            track_number=get_number(self.track_edit.text()),
            track_total=get_number(self.track_total_edit.text()),
            disc_number=get_number(self.disc_edit.text()),
            disc_total=get_number(self.disc_total_edit.text()),
            narrator=self.narrator_edit.text(),
            series=self.series_edit.text(),
            series_number=self.series_number_edit.text(),
            publisher=self.publisher_edit.text(),
            date=self.date_edit.text(),
            composer=self.composer_edit.text(),
            comment=self.comment_edit.text(),
            id3v1_comment=self.id3v1_comment_edit.text(),
            copyright=self.copyright_edit.text(),
            description=self.description_edit.toPlainText(),
            artwork=self.pending_artwork,
            artwork_mime=self.pending_artwork_mime,
        )

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

                    if self.multi_edit_artwork:
                        artwork = self.pending_artwork
                        artwork_mime = self.pending_artwork_mime
                    else:
                        artwork = metadata.artwork
                        artwork_mime = metadata.artwork_mime

                    suffix = path.suffix.lower()

                    if suffix == ".mp3":
                        write_mp3_metadata(
                            path,
                            metadata,
                            artwork,
                            artwork_mime,
                        )
                    elif suffix == ".m4b":
                        write_m4b_metadata(
                            path,
                            metadata,
                            artwork,
                            artwork_mime,
                        )

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

        try:
            suffix = self.current_file.suffix.lower()

            if suffix == ".mp3":
                write_mp3_metadata(
                    self.current_file,
                    metadata,
                    self.pending_artwork,
                    self.pending_artwork_mime,
                )

            elif suffix == ".m4b":
                write_m4b_metadata(
                    self.current_file,
                    metadata,
                    self.pending_artwork,
                    self.pending_artwork_mime,
                )

            else:
                raise ValueError(
                    f"Unsupported file type: {self.current_file.suffix}"
                )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save the file:\n\n{exc}",
            )
            return

        self.current_metadata = metadata

        self.file_list.update_file_metadata(
            self.current_file,
            metadata,
        )

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
            edited.title != loaded.title
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

            self.statusBar().showMessage("Changes undone")
            return

        if len(self.selected_files) == 1:
            path = Path(self.selected_files[0])

            self.current_metadata = read_metadata(path)

            self.multi_edit_fields.clear()
            self.multi_edit_artwork = False

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

        if path.lower().endswith(".png"):
            self.pending_artwork_mime = "image/png"
        else:
            self.pending_artwork_mime = "image/jpeg"

        if len(self.selected_files) > 1:
            self.multi_edit_artwork = True

        pixmap = QPixmap.fromImage(image)

        self.artwork_label.setPixmap(
            pixmap.scaled(
                self.artwork_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _remove_artwork(self):
        if self.current_metadata is None:
            return

        self.pending_artwork = None
        self.pending_artwork_mime = ""

        if len(self.selected_files) > 1:
            self.multi_edit_artwork = True

        self.artwork_label.clear()

        if len(self.selected_files) > 1:
            self.artwork_label.setText("No artwork")


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

        fields = {
            "title": self.title_edit,
            "artist": self.artist_edit,
            "album": self.album_edit,
            "album_artist": self.album_artist_edit,
            "genre": self.genre_edit,
            "track_number": self.track_edit,
            "track_total": self.track_total_edit,
            "disc_number": self.disc_edit,
            "disc_total": self.disc_total_edit,
            "narrator": self.narrator_edit,
            "series": self.series_edit,
            "series_number": self.series_number_edit,
            "publisher": self.publisher_edit,
            "date": self.date_edit,
            "composer": self.composer_edit,
            "comment": self.comment_edit,
            "id3v1_comment": self.id3v1_comment_edit,
            "copyright": self.copyright_edit,
            "description": self.description_edit,
        }

        for field, widget in fields.items():
            value, is_common = self._common_metadata_value(
                metadatas,
                field,
            )

            widget.blockSignals(True)

            if is_common:
                text = "" if value is None else str(value)

                if isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(text)
                else:
                    widget.setText(text)

                widget.setPlaceholderText("")
            else:
                if isinstance(widget, QPlainTextEdit):
                    widget.setPlainText("")
                else:
                    widget.setText("")

                widget.setPlaceholderText("<multiple values>")

            widget.blockSignals(False)

        self.artwork_label.clear()
        self.artwork_label.setText("Multiple files selected")

    def _connect_multi_edit_tracking(self):
        fields = {
            "title": self.title_edit,
            "artist": self.artist_edit,
            "album": self.album_edit,
            "album_artist": self.album_artist_edit,
            "genre": self.genre_edit,
            "track_number": self.track_edit,
            "track_total": self.track_total_edit,
            "disc_number": self.disc_edit,
            "disc_total": self.disc_total_edit,
            "narrator": self.narrator_edit,
            "series": self.series_edit,
            "series_number": self.series_number_edit,
            "publisher": self.publisher_edit,
            "date": self.date_edit,
            "composer": self.composer_edit,
            "comment": self.comment_edit,
            "id3v1_comment": self.id3v1_comment_edit,
            "copyright": self.copyright_edit,
            "description": self.description_edit,
        }

        for field, widget in fields.items():
            if isinstance(widget, QPlainTextEdit):
                widget.textChanged.connect(
                    lambda field=field: (
                        self.multi_edit_fields.add(field),
                        self._update_multi_edit_visuals(),
                    )
                    if len(self.selected_files) > 1
                    else None
                )
            else:
                widget.textEdited.connect(
                    lambda text, field=field: (
                        self.multi_edit_fields.add(field),
                        self._update_multi_edit_visuals(),
                    )
                    if len(self.selected_files) > 1
                    else None
                )

    def _update_multi_edit_visuals(self):
        fields = {
            "title": self.title_edit,
            "artist": self.artist_edit,
            "album": self.album_edit,
            "album_artist": self.album_artist_edit,
            "genre": self.genre_edit,
            "track_number": self.track_edit,
            "track_total": self.track_total_edit,
            "disc_number": self.disc_edit,
            "disc_total": self.disc_total_edit,
            "narrator": self.narrator_edit,
            "series": self.series_edit,
            "series_number": self.series_number_edit,
            "publisher": self.publisher_edit,
            "date": self.date_edit,
            "composer": self.composer_edit,
            "comment": self.comment_edit,
            "id3v1_comment": self.id3v1_comment_edit,
            "copyright": self.copyright_edit,
            "description": self.description_edit,
        }

        for field, widget in fields.items():
            if field in self.multi_edit_fields:
                widget.setStyleSheet(
                    "background-color: #fff3cd; color: black;"
                )
            else:
                widget.setStyleSheet("")

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

        dialog = QDialog(self)
        dialog.setWindowTitle("Paste Metadata")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        layout.addWidget(
            QLabel(
                "Select the fields to paste into the selected files:"
            )
        )

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
        }

        checkboxes = {}

        for field, label in fields.items():
            checkbox = QCheckBox(label)
            checkbox.setChecked(
                field in self.paste_metadata_fields
            )
            checkboxes[field] = checkbox
            layout.addWidget(checkbox)

        artwork_checkbox = QCheckBox("Artwork")
        artwork_checkbox.setChecked(
            "artwork" in self.paste_metadata_fields
        )
        checkboxes["artwork"] = artwork_checkbox
        layout.addWidget(artwork_checkbox)

        selection_layout = QHBoxLayout()

        select_all_button = QPushButton("Select All")
        clear_all_button = QPushButton("Clear All")

        selection_layout.addWidget(select_all_button)
        selection_layout.addWidget(clear_all_button)

        layout.addLayout(selection_layout)

        select_all_button.clicked.connect(
            lambda: [
                checkbox.setChecked(True)
                for checkbox in checkboxes.values()
            ]
        )

        clear_all_button.clicked.connect(
            lambda: [
                checkbox.setChecked(False)
                for checkbox in checkboxes.values()
            ]
        )

        button_layout = QHBoxLayout()

        cancel_button = QPushButton("Cancel")
        paste_button = QPushButton("Paste")

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(paste_button)

        layout.addLayout(button_layout)

        cancel_button.clicked.connect(dialog.reject)
        paste_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_fields = {
            field
            for field, checkbox in checkboxes.items()
            if checkbox.isChecked()
        }

        self.paste_metadata_fields = selected_fields.copy()

        if not selected_fields:
            QMessageBox.information(
                self,
                "Paste Metadata",
                "No fields were selected.",
            )
            return

        if "artwork" in selected_fields:
            self.pending_artwork = self.metadata_clipboard.artwork
            self.pending_artwork_mime = (
                self.metadata_clipboard.artwork_mime
            )
            if len(self.selected_files) > 1:
                self.multi_edit_artwork = True

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
        fields = {
            "title": self.title_edit,
            "artist": self.artist_edit,
            "album": self.album_edit,
            "album_artist": self.album_artist_edit,
            "genre": self.genre_edit,
            "track_number": self.track_edit,
            "track_total": self.track_total_edit,
            "disc_number": self.disc_edit,
            "disc_total": self.disc_total_edit,
            "narrator": self.narrator_edit,
            "series": self.series_edit,
            "series_number": self.series_number_edit,
            "publisher": self.publisher_edit,
            "date": self.date_edit,
            "composer": self.composer_edit,
            "comment": self.comment_edit,
            "id3v1_comment": self.id3v1_comment_edit,
            "copyright": self.copyright_edit,
            "description": self.description_edit,
        }

        for field in selected_fields:
            widget = fields.get(field)

            if widget is None:
                continue

            value = getattr(
                self.metadata_clipboard,
                field,
            )

            widget.blockSignals(True)

            widget.setPlaceholderText("")

            if isinstance(widget, QPlainTextEdit):
                widget.setPlainText(
                    "" if value is None else str(value)
                )
            else:
                widget.setText(
                    "" if value is None else str(value)
                )

            widget.blockSignals(False)

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

        QShortcut(
            QKeySequence("Delete"),
            self,
        ).activated.connect(self._remove_artwork)

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

        super().keyPressEvent(event)