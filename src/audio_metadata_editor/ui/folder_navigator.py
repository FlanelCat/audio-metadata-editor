from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from .directory_tree import DirectoryTree


class FolderNavigator(QWidget):
    """Read-only root presentation and navigation intent; no metadata policy."""

    choose_root_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.heading = QLabel("No audiobook root selected")
        self.heading.setTextFormat(Qt.PlainText)
        self.heading.setWordWrap(True)
        font = self.heading.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self.heading.setFont(font)
        self.path_label = QLabel()
        self.path_label.setTextFormat(Qt.PlainText)
        self.path_label.setWordWrap(True)
        self.path_label.setForegroundRole(self.palette().ColorRole.PlaceholderText)
        self.choose_button = QPushButton("Choose Root…")
        self.choose_button.clicked.connect(self.choose_root_requested)
        self.tree = DirectoryTree()
        layout.addWidget(self.heading)
        layout.addWidget(self.path_label)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.tree)

    def set_root(self, path, directories):
        self.tree.set_root(path, directories)
        self.heading.setText(path.name or str(path))
        self.path_label.setText(str(path))
