from pathlib import Path
from html import escape

from PySide6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QPersistentModelIndex,
    QSignalBlocker,
    Signal,
    QUrl,
    Qt,
    QTimer,
)
from PySide6.QtGui import QAction, QDesktopServices, QFont, QKeySequence
from PySide6.QtWidgets import (
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
)
from ..editing_rules import copy_target_paths
from ..metadata.reader import read_metadata
from ..metadata.errors import MetadataReadError
from ..metadata.representation import validate_values, RepresentationError

AUDIO_EXTENSIONS = {".mp3", ".m4b"}
TABLE_FIELDS = {1: 'track_number', 2: 'title', 3: 'artist', 4: 'album',
                5: 'series', 6: 'series_number', 7: 'narrator'}
COPY_TEXT_FIELDS = {column: field for column, field in TABLE_FIELDS.items() if field != 'track_number'}

class FilenameTableWidgetItem(QTableWidgetItem):
    """Keep filename identity and sorting independent of status decoration."""

    def __init__(self, path: Path):
        super().__init__(path.name)
        self.setData(256, str(path))
        self.setData(257, path.name)

    def __lt__(self, other):
        return self.data(257).casefold() < other.data(257).casefold()


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

class EnterNavigationDelegate(QStyledItemDelegate):
    save_cell_requested = Signal(str, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enter_commit = False

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if editor is not None:
            # Established for every lifecycle, including automatic Enter advance.
            # The persistent index follows sorting; its model retains the accepted
            # value until a valid Enter commit. No table-wide previous value.
            editor._metadata_context = (
                index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole),
                QPersistentModelIndex(index),
            )
        return editor

    def setModelData(self, editor, model, index):
        # Qt also requests commits on focus loss and Tab. Those only abandon
        # the transient editor; the accepted table value must remain intact.
        if self._enter_commit:
            super().setModelData(editor, model, index)

    def eventFilter(self, editor, event):
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            view = self.parent()

            if not isinstance(view, QTableWidget):
                return super().eventFilter(editor, event)

            context = getattr(editor, "_metadata_context", None)
            if context is None or not isinstance(editor, QLineEdit):
                return super().eventFilter(editor, event)
            path, index = context
            column = index.column()
            if not path or not index.isValid() or not 1 <= column <= 7:
                return True
            value = editor.text()
            # Reject before Qt changes the accepted value or sorts the row.
            # Preserve the table's positive-number rules and blank allowance.
            if column in (1, 6) and value.strip():
                try:
                    number = int(value) if column == 1 else float(value)
                    if number < 1:
                        raise ValueError
                except ValueError:
                    editor.setFocus()
                    editor.selectAll()
                    return True

            try:
                requested = (int(value) if value.strip() else None) if column == 1 else value
                validate_values(Path(path).suffix.lower(), {TABLE_FIELDS[column]: requested})
            except RepresentationError as exc:
                QMessageBox.warning(view, "Invalid Metadata", str(exc))
                editor.setFocus()
                editor.selectAll()
                return True

            # Commit the edit before requesting an immediate disk save.
            self._enter_commit = True
            try:
                self.commitData.emit(editor)
            finally:
                self._enter_commit = False
            self.closeEditor.emit(
                editor,
                QStyledItemDelegate.EndEditHint.NoHint,
            )

            view.cell_save_succeeded = True
            self.save_cell_requested.emit(str(path), column, value)

            if not view.cell_save_succeeded:
                return True

            # Stop at the bottom; do not wrap around.
            row = next((r for r in range(view.rowCount())
                        if view.item(r, 0).data(256) == path), None)
            if row is None:
                return True
            next_row = row + 1
            if next_row < view.rowCount():
                next_path = view.item(next_row, 0).data(256)
                view.advance_allowed = True
                view.advance_requested.emit(next_path)
                if not view.advance_allowed:
                    return True
                # Saving pending panel changes may reorder the table.
                next_row = next((r for r in range(view.rowCount())
                                 if view.item(r, 0).data(256) == next_path), next_row)
                next_index = view.model().index(next_row, column)

                view.selectionModel().setCurrentIndex(
                    next_index,
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )

                # Start editing the next cell and select its contents.
                def edit_next_cell():
                    view.edit(next_index)
                    next_editor = view.focusWidget()
                    if isinstance(next_editor, QLineEdit):
                        next_editor.selectAll()

                QTimer.singleShot(0, edit_next_cell)

            return True

        return super().eventFilter(editor, event)

class FileList(QTableWidget):
    copy_values_requested = Signal(str, object)
    advance_requested = Signal(str)
    file_selected = Signal(str)
    files_selected = Signal(list)
    metadata_cell_edited = Signal(str, int, str)
    save_cell_requested = Signal(str, int, str)

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
        # Qt includes header labels, delegate size hints, and style padding.
        # Inspect every row, including those outside the viewport.
        header.setResizeContentsPrecision(-1)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self.itemSelectionChanged.connect(self._selection_changed)
        self.itemDoubleClicked.connect(self._item_double_clicked)
        self.itemChanged.connect(self._item_changed)
        delegate = EnterNavigationDelegate(self)
        delegate.save_cell_requested.connect(self.save_cell_requested)
        self.setItemDelegate(delegate)
        self.copy_down_action = QAction("Copy Down", self)
        self.copy_up_action = QAction("Copy Up", self)
        for action, shortcut, down in ((self.copy_down_action, "Ctrl+D", True),
                                       (self.copy_up_action, "Ctrl+Shift+D", False)):
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(lambda checked=False, down=down: self._copy_cells(down))
            self.addAction(action)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.itemSelectionChanged.connect(self._update_copy_actions)
        self.currentCellChanged.connect(self._update_copy_actions)
        self.model().layoutChanged.connect(self._update_copy_actions)
        self._update_copy_actions()

    def _copy_snapshot(self, down):
        item = self.currentItem()
        if item is None or item.column() not in COPY_TEXT_FIELDS or not item.flags() & Qt.ItemIsEditable:
            return None
        visual = [self.item(row, 0).data(256) for row in range(self.rowCount())
                  if self.item(row, 0) is not None and self.item(row, 0).data(256)]
        source = self.item(item.row(), 0).data(256)
        targets = copy_target_paths(visual, set(self.selected_paths_in_row_order()), source, down=down)
        if not targets:
            return None
        # Read the model's effective display value, never unconfirmed editor text.
        return COPY_TEXT_FIELDS[item.column()], {path: item.text() for path in targets}

    def _update_copy_actions(self):
        self.copy_down_action.setEnabled(self._copy_snapshot(True) is not None)
        self.copy_up_action.setEnabled(self._copy_snapshot(False) is not None)

    def _copy_cells(self, down):
        snapshot = self._copy_snapshot(down)
        if snapshot is None:
            return
        if self.state() == QTableWidget.State.EditingState:
            editor = self.indexWidget(self.currentIndex())
            if editor is not None:
                self.closeEditor(editor, QStyledItemDelegate.EndEditHint.NoHint)
        self.copy_values_requested.emit(*snapshot)
        self._update_copy_actions()

    def selectionChanged(self, selected, deselected):
        # Programmatic selection changes need not move keyboard focus, so Qt
        # may otherwise leave an editor visible over the previous context.
        if self.state() == QTableWidget.State.EditingState:
            editor = self.indexWidget(self.currentIndex())
            if editor is not None:
                self.closeEditor(editor, QStyledItemDelegate.EndEditHint.NoHint)
        super().selectionChanged(selected, deselected)

    @staticmethod
    def directory_files(directory: Path):
        return sorted(
            (entry for entry in directory.iterdir()
             if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS),
            key=lambda entry: entry.name.lower(),
        )

    def load_directory(self, directory: Path):
        # Enumeration failure must leave the previous rows and selection intact.
        self.directory_error = None
        try:
            files = self.directory_files(directory)
        except OSError as exc:
            self.directory_error = exc
            return None
        sorting = self.isSortingEnabled()
        header = self.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        # Populate each complete file row, including its path, before Qt may
        # move it. Numeric row positions are only stable while sorting is off.
        self.setSortingEnabled(False)
        try:
            self.setRowCount(0)
            # Qt may retain old content widths when the model becomes empty.
            self.resizeColumnsToContents()

            errors = []
            for file_path in files:
                try:
                    metadata = read_metadata(file_path)
                except MetadataReadError as exc:
                    errors.append(exc)
                    continue
                row = self.rowCount()
                self.insertRow(row)

                self.setItem(
                    row,
                    0,
                    FilenameTableWidgetItem(file_path),
                )

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

                for column in range(1, self.columnCount()):
                    item = self.item(row, column)

                    if item is not None:
                        item.setFlags(
                            item.flags()
                            | Qt.ItemFlag.ItemIsEditable
                        )

            return errors
        finally:
            header.setSortIndicator(sort_column, sort_order)
            self.setSortingEnabled(sorting)

    def selected_paths_in_row_order(self):
        rows = sorted(index.row() for index in self.selectionModel().selectedRows())
        return [self.item(row, 0).data(256) for row in rows
                if self.item(row, 0) is not None and self.item(row, 0).data(256)]

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

            sorting = self.isSortingEnabled()
            with QSignalBlocker(self):
                self.setSortingEnabled(False)
                self.item(row, 1).setText(track)
                self.item(row, 2).setText(metadata.title)
                self.item(row, 3).setText(metadata.artist)
                self.item(row, 4).setText(metadata.album)
                self.item(row, 5).setText(metadata.series)
                self.item(row, 6).setText(metadata.series_number)
                self.item(row, 7).setText(metadata.narrator)
                self.setSortingEnabled(sorting)

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

    def show_pending_fields(self, path, values):
        """Overlay scalar presentation without changing file identity or baselines."""
        columns = {field: column for column, field in TABLE_FIELDS.items()}
        item = next((self.item(row, 0) for row in range(self.rowCount())
                     if self.item(row, 0).data(256) == str(path)), None)
        if item is None:
            return
        sorting = self.isSortingEnabled()
        with QSignalBlocker(self):
            self.setSortingEnabled(False)
            try:
                for field, value in values.items():
                    if field in columns:
                        self.item(item.row(), columns[field]).setText('' if value is None else str(value))
            finally:
                self.setSortingEnabled(sorting)
        self._update_copy_actions()

    def set_pending_previews(self, edits):
        """Keep panel-only generated values inspectable on their file rows too."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is None or not item.data(256):
                continue
            values = edits.get(Path(item.data(256)), {})
            preview = '\n'.join(f"{field.replace('_', ' ').title()}: {value}"
                                for field, value in values.items())
            item.setToolTip('<pre>' + escape('Pending per-file text\n' + preview) + '</pre>'
                            if values else '')

    def set_dirty_files(self, paths):
        dirty_paths = {str(path) for path in paths}

        # Keep iteration tied to item identity, independent of row positions.
        items = [self.item(row, 0) for row in range(self.rowCount())]
        for item in items:

            if item is None:
                continue

            path = item.data(256)

            # Remember the original filename once.
            original_name = item.data(257)

            if original_name is None:
                original_name = item.text()
                item.setData(257, original_name)

            if path in dirty_paths:
                item.setText(f"* {original_name}")
            else:
                item.setText(original_name)
