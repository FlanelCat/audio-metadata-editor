from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from ..metadata.reader import read_metadata

AUDIO_EXTENSIONS = {".mp3", ".m4b"}


class FileList(QTableWidget):
    file_selected = Signal(str)

    def __init__(self):
        super().__init__()

        self.setColumnCount(8)
        self.setHorizontalHeaderLabels(
            [
                "Filename",
                "Track",
                "Title",
                "Artist",
                "Album",
                "Series",
                "Series #",
                "Narrator",
            ]
        )

        self.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        self.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )

        self.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )

        header = self.horizontalHeader()

        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)    

        self.itemSelectionChanged.connect(self._selection_changed)

    def load_directory(self, directory: Path):
        self.setRowCount(0)

        try:
            files = sorted(
                (
                    entry
                    for entry in directory.iterdir()
                    if entry.is_file()
                    and entry.suffix.lower() in AUDIO_EXTENSIONS
                ),
                key=lambda entry: entry.name.lower(),
            )
        except OSError:
            return

        for row, file_path in enumerate(files):
            self.insertRow(row)

            self.setItem(
                row,
                0,
                QTableWidgetItem(file_path.name),
            )

            metadata = read_metadata(file_path)

            track = ""
            if metadata.track_number is not None:
                track = str(metadata.track_number)

            self.setItem(
                row,
                1,
                QTableWidgetItem(track),
            )

            self.setItem(
                row,
                2,
                QTableWidgetItem(metadata.title),
            )

            self.setItem(
                row,
                3,
                QTableWidgetItem(metadata.artist),
            )

            self.setItem(
                row,
                4,
                QTableWidgetItem(metadata.album),
            )

            self.setItem(
                row,
                5,
                QTableWidgetItem(metadata.series),
            )

            self.setItem(
                row,
                6,
                QTableWidgetItem(metadata.series_number),
            )

            self.setItem(
                row,
                7,
                QTableWidgetItem(metadata.narrator),
            )

            self.item(row, 0).setData(
                256,
                str(file_path),
            )

    def _selection_changed(self):
        rows = self.selectionModel().selectedRows()

        if not rows:
            return

        item = self.item(rows[0].row(), 0)

        if item is None:
            return

        path = item.data(256)

        if path:
            self.file_selected.emit(path)

    def select_file(self, path):
        for row in range(self.rowCount()):
            item = self.item(row, 0)

            if item is None:
                continue

            if item.data(256) == str(path):
                with QSignalBlocker(self):
                    self.clearSelection()
                    self.selectRow(row)
                return