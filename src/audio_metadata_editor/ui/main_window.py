from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
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
        self.current_metadata = None
        self.pending_artwork = None
        self.pending_artwork_mime = ""

        self._create_toolbar()
        self._create_main_layout()
        self._create_status_bar()

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        open_button = QPushButton("Open Folder")
        open_button.clicked.connect(self._open_folder)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_tree)

        save_button = QPushButton("Save Changes")
        save_button.clicked.connect(self._save_changes)

        toolbar.addWidget(open_button)
        toolbar.addWidget(refresh_button)

        toolbar.addSeparator()

        toolbar.addWidget(save_button)

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

    def _file_selected(self, path):
        new_file = Path(path)

        if self.current_file is not None and new_file != self.current_file:
            if self._has_unsaved_changes():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"You have unsaved changes to:\n\n"
                    f"{self.current_file.name}\n\n"
                    "Do you want to save them before switching files?",
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
                    self.file_list.select_file(self.current_file)
                    return

        self.current_file = new_file

        metadata = read_metadata(new_file)
        self.current_metadata = metadata
        self.pending_artwork = metadata.artwork
        self.pending_artwork_mime = metadata.artwork_mime

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
            self.current_file.suffix.lower() == ".mp3"
        )
        self.copyright_edit.setText(metadata.copyright)
        self.description_edit.setPlainText(metadata.description)

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
        if self.current_file is None:
            QMessageBox.warning(
                self,
                "No File Selected",
                "Please select a file before saving.",
            )
            return

        if not self._has_unsaved_changes():
            QMessageBox.information(
                self,
                "No Changes",
                "There are no changes to save.",
            )
            return

        metadata = self._get_edited_metadata()

        suffix = self.current_file.suffix.lower()

        try:
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
                QMessageBox.warning(
                    self,
                    "Unsupported File",
                    f"Writing {suffix} is not supported.",
                )
                return
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
            f"Metadata saved successfully:\n\n{self.current_file.name}",
        )

    def _has_unsaved_changes(self):
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

        self.artwork_label.clear()