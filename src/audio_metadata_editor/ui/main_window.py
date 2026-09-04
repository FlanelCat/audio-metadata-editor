from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .file_list import FileList
from ..metadata.reader import read_metadata

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Audio Metadata Editor")
        self.resize(1200, 700)

        self.root_path = None

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

        form = QFormLayout()

        self.title_edit = QLineEdit()
        self.artist_edit = QLineEdit()
        self.album_edit = QLineEdit()
        self.album_artist_edit = QLineEdit()
        self.genre_edit = QLineEdit()
        self.track_edit = QLineEdit()
        self.disc_edit = QLineEdit()

        form.addRow("Title", self.title_edit)
        form.addRow("Artist", self.artist_edit)
        form.addRow("Album", self.album_edit)
        form.addRow("Album Artist", self.album_artist_edit)
        form.addRow("Genre", self.genre_edit)
        form.addRow("Track", self.track_edit)
        form.addRow("Disc", self.disc_edit)

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
        metadata = read_metadata(Path(path))

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

        self.disc_edit.setText(
            str(metadata.disc_number)
            if metadata.disc_number is not None
            else ""
        )
                    