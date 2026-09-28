from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Signal, Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator


class DirectoryTree(QTreeWidget):
    """Lazy directory presentation; the caller decides navigation policy."""

    directory_requested = Signal(str)
    enumeration_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accepted_item = None
        self.setHeaderLabel("Folders")
        self.setHeaderHidden(True)
        self.itemExpanded.connect(self._populate_directory)
        self.itemClicked.connect(self._request_directory)

    @staticmethod
    def child_directories(path):
        """Enumerate only this level, omitting hidden and symlink directories."""
        return sorted(
            (entry for entry in Path(path).iterdir()
             if not entry.name.startswith('.') and not entry.is_symlink() and entry.is_dir()),
            key=lambda entry: (entry.name.casefold(), entry.name),
        )

    def set_root(self, path, directories=None):
        """Rebuild an already readable root without requesting navigation."""
        path = Path(path)
        if directories is None:
            try:
                directories = self.child_directories(path)
            except OSError as exc:
                self.enumeration_failed.emit(f"Cannot list {path}: {exc}")
                return False
        with QSignalBlocker(self):
            self._accepted_item = None
            self.clear()
            root = QTreeWidgetItem(["Books"])
            root.setData(0, 256, str(path))
            self.addTopLevelItem(root)
            self._install_children(root, directories)
            root.setExpanded(True)
            self.setCurrentItem(root)
            self._accepted_item = root
        return True

    def set_current_directory(self, path):
        """Accept a displayed directory, or clear selection for an outside folder."""
        self._accepted_item = None
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value() is not None:
            item = iterator.value()
            if item.data(0, 256) == str(path):
                self._accepted_item = item
                break
            iterator += 1
        self.restore_current_directory()

    def restore_current_directory(self):
        with QSignalBlocker(self):
            self.clearSelection()
            self.setCurrentItem(self._accepted_item)

    def _request_directory(self, item, column):
        path = item.data(0, 256)
        if path:
            self.directory_requested.emit(path)

    def keyPressEvent(self, event):
        previous = self.currentItem()
        super().keyPressEvent(event)
        item = self.currentItem()
        if item is not None and (item is not previous or event.key() in (Qt.Key_Return, Qt.Key_Enter)):
            self._request_directory(item, 0)

    def _install_children(self, item, directories):
        item.takeChildren()
        for directory in directories:
            child = QTreeWidgetItem([directory.name])
            child.setData(0, 256, str(directory))
            # Show an expansion affordance without probing this child's contents.
            child.addChild(QTreeWidgetItem([""]))
            item.addChild(child)
        item.setData(0, 257, True)

    def _populate_directory(self, item):
        if item.data(0, 257):
            return
        path = Path(item.data(0, 256))
        try:
            directories = self.child_directories(path)
        except OSError as exc:
            # Keep the placeholder and unloaded state so collapse/expand retries.
            self.enumeration_failed.emit(f"Cannot list {path}: {exc}")
            return
        self._install_children(item, directories)
