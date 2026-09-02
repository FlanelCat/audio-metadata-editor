from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from ..metadata.reader import read_metadata

AUDIO_EXTENSIONS = {".mp3", ".m4b"}


class FileList(QTableWidget):
    file_selected = Signal(str)

    def __init__(self):
        super().__init__()

        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(
            ["Filename", "Title", "Artist", "Album"]
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

        self.horizontalHeader().setStretchLastSection(True)

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

            self.setItem(
                row,
                1,
                QTableWidgetItem(metadata.get("title", "")),
            )

            self.setItem(
                row,
                2,
                QTableWidgetItem(metadata.get("artist", "")),
            )

            self.setItem(
                row,
                3,
                QTableWidgetItem(metadata.get("album", "")),
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
