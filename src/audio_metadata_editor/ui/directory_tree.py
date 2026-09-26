from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator


class DirectoryTree(QTreeWidget):
    """Directory presentation and requests; the caller decides navigation policy."""

    directory_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accepted_item = None
        self.setHeaderLabel("Folders")
        self.itemExpanded.connect(self._populate_directory)
        self.itemClicked.connect(self._request_directory)

    def set_root(self, path):
        """Rebuild and select a root without requesting navigation."""
        path = Path(path)
        self._accepted_item = None
        self.clear()
        root_item = QTreeWidgetItem([path.name or str(path)])
        root_item.setData(0, 256, str(path))
        self.addTopLevelItem(root_item)
        self._add_placeholder(root_item)
        root_item.setExpanded(True)
        self.setCurrentItem(root_item)
        root_item.setSelected(True)

    def set_current_directory(self, path):
        """Remember an accepted, displayed directory without requesting navigation."""
        path = str(path)
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value() is not None:
            item = iterator.value()
            if item.data(0, 256) == path:
                self._accepted_item = item
                with QSignalBlocker(self):
                    self.setCurrentItem(item)
                return
            iterator += 1

    def restore_current_directory(self):
        """Restore presentation after the caller rejects a directory request."""
        if self._accepted_item is not None:
            with QSignalBlocker(self):
                self.setCurrentItem(self._accepted_item)

    def _request_directory(self, item, column):
        path = item.data(0, 256)
        if path:
            self.directory_requested.emit(path)

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

