"""A text editor with optional, commit-only existing-value choices."""
from PySide6.QtCore import QPoint, Qt, QSignalBlocker
from PySide6.QtWidgets import QLineEdit, QMenu, QStyle


MIXED_PLACEHOLDER = "<multiple values — edit to apply to all>"


class ExistingValuesEdit(QLineEdit):
    """Keep ordinary line editing; only activating a menu item chooses a value."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._menu = QMenu(self)
        self._menu.triggered.connect(self._choose_value)
        self._dropdown = self.addAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._dropdown.setText("Existing values")
        self._dropdown.setToolTip("Choose an existing value (Alt+Down)")
        self._dropdown.triggered.connect(self.show_existing_values)
        self._dropdown.setVisible(False)

    def set_existing_values(self, values=None):
        """Replace accepted choices silently, preserving text and placeholder.

        None disables the dropdown outside a multi-file editing context.
        Empty is a label for the empty string, never the value of that action.
        """
        self._menu.hide()
        self._menu.clear()
        self._dropdown.setVisible(values is not None)
        if values is None:
            return
        for value in dict.fromkeys(["", *values]):
            if value == MIXED_PLACEHOLDER:
                continue
            label = 'Empty' if value == '' else '"Empty"' if value == 'Empty' else value
            action = self._menu.addAction(label.replace('&', '&&'))
            action.setData(value)
            action.setToolTip(value)

    def show_existing_values(self):
        if self.isEnabled() and self._dropdown.isVisible():
            self._menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Down and event.modifiers() == Qt.KeyboardModifier.AltModifier:
            if self._dropdown.isVisible():
                self.show_existing_values()
                event.accept()
                return
        super().keyPressEvent(event)

    def _choose_value(self, action):
        if not self.isEnabled():
            return
        value = action.data()
        with QSignalBlocker(self):
            self.setText(value)
            self.setPlaceholderText("")
        # Match QLineEdit's user-edit ordering, including an explicit blank
        # choice when mixed presentation already has empty editor text.
        self.textEdited.emit(value)
        self.textChanged.emit(value)
        self.setFocus()
        self.selectAll()
