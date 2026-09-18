from pathlib import Path

from PySide6.QtCore import (
    QItemSelectionModel,
    QSignalBlocker,
    Signal,
    QUrl,
    Qt,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from ..metadata.reader import read_metadata

AUDIO_EXTENSIONS = {".mp3", ".m4b"}

class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        column = self.column()

        if column in (1, 6):
            left = self.text().strip()
            right = other.text().strip()

            left_empty = not left
            right_empty = not right

            if left_empty or right_empty:
                if left_empty and right_empty:
                    return False

                order = (
                    self.tableWidget()
                    .horizontalHeader()
                    .sortIndicatorOrder()
                )

                if order == Qt.SortOrder.AscendingOrder:
                    return not left_empty

                return left_empty

            try:
                return float(left) < float(right)
            except ValueError:
                return left.casefold() < right.casefold()

        return self.text().casefold() < other.text().casefold()

class FileList(QTableWidget):
    file_selected = Signal(str)
    files_selected = Signal(list)
    metadata_cell_edited = Signal(str, int, str)

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

        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicatorShown(True)

        self.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        self.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )

        self.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
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
        self.itemDoubleClicked.connect(self._item_double_clicked)
        self.itemChanged.connect(self._item_changed)
        self._editing_previous_value = ""

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
                SortableTableWidgetItem(file_path.name),
            )

            metadata = read_metadata(file_path)

            track = ""
            if metadata.track_number is not None:
                track = str(metadata.track_number)

            self.setItem(
                row,
                1,
                SortableTableWidgetItem(track),
            )

            self.setItem(
                row,
                2,
                SortableTableWidgetItem(metadata.title),
            )

            self.setItem(
                row,
                3,
                SortableTableWidgetItem(metadata.artist),
            )

            self.setItem(
                row,
                4,
                SortableTableWidgetItem(metadata.album),
            )

            self.setItem(
                row,
                5,
                SortableTableWidgetItem(metadata.series),
            )

            self.setItem(
                row,
                6,
                SortableTableWidgetItem(metadata.series_number),
            )

            self.setItem(
                row,
                7,
                SortableTableWidgetItem(metadata.narrator),
            )

            self.item(row, 0).setData(
                256,
                str(file_path),
            )

            for column in range(1, self.columnCount()):
                item = self.item(row, column)

                if item is not None:
                    item.setFlags(
                        item.flags()
                        | Qt.ItemFlag.ItemIsEditable
                    )

    def _selection_changed(self):
        rows = self.selectionModel().selectedRows()

        paths = []

        for index in rows:
            item = self.item(index.row(), 0)

            if item is None:
                continue

            path = item.data(256)

            if path:
                paths.append(path)

        if not paths:
            return

        self.files_selected.emit(paths)

        if len(paths) == 1:
            self.file_selected.emit(paths[0])

    def update_file_metadata(self, path, metadata):
        for row in range(self.rowCount()):
            item = self.item(row, 0)

            if item is None:
                continue

            if item.data(256) != str(path):
                continue

            track = ""
            if metadata.track_number is not None:
                track = str(metadata.track_number)

            with QSignalBlocker(self):
                self.item(row, 1).setText(track)
                self.item(row, 2).setText(metadata.title)
                self.item(row, 3).setText(metadata.artist)
                self.item(row, 4).setText(metadata.album)
                self.item(row, 5).setText(metadata.series)
                self.item(row, 6).setText(metadata.series_number)
                self.item(row, 7).setText(metadata.narrator)

            return

    def _item_changed(self, item):
        column = item.column()

        if column == 0:
            return

        filename_item = self.item(item.row(), 0)
        if filename_item is None:
            return

        path = filename_item.data(256)
        if not path:
            return

        value = item.text().strip()

        # Track number must be a positive integer.
        if column == 1 and value:
            try:
                number = int(value)
                if number < 1:
                    raise ValueError
            except ValueError:
                with QSignalBlocker(self):
                    item.setText(self._editing_previous_value)
                return

        # Series number must be a positive number.
        if column == 6 and value:
            try:
                number = float(value)
                if number < 1:
                    raise ValueError
            except ValueError:
                with QSignalBlocker(self):
                    item.setText(self._editing_previous_value)
                return

        self.metadata_cell_edited.emit(
            path,
            column,
            value,
        )

    def _item_double_clicked(self, item):
        column = item.column()

        if column == 0:
            path = item.data(256)
            if not path:
                return

            QDesktopServices.openUrl(
                QUrl.fromLocalFile(path)
            )
            return

        self._editing_previous_value = item.text()

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

    def select_files(self, paths):
        paths = {str(path) for path in paths}

        with QSignalBlocker(self):
            self.clearSelection()

            selection_model = self.selectionModel()

            for row in range(self.rowCount()):
                item = self.item(row, 0)

                if item is None:
                    continue

                path = item.data(256)

                if path not in paths:
                    continue

                index = self.model().index(row, 0)

                selection_model.select(
                    index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

        rows = self.selectionModel().selectedRows()

        restored_paths = []

        for index in rows:
            item = self.item(index.row(), 0)

            if item is None:
                continue

            path = item.data(256)

            if path:
                restored_paths.append(path)

        self.files_selected.emit(restored_paths)
