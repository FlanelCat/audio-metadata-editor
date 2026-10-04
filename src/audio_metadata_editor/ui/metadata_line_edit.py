"""Keep values that cannot be represented by a bounded single-line editor."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QLineEdit, QStyle


class MetadataLineEdit(QLineEdit):
    """An oversized value is retained, never exposed as an editable prefix."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._retained_value = None
        self._normal_placeholder = ''
        self.replace_value_action = self.addAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.replace_value_action.setText('Replace value')
        self.replace_value_action.setToolTip('Replace the complete oversized value with new text')
        self.replace_value_action.setVisible(False)
        self.replace_value_action.triggered.connect(self._replace_value)

    def value_text(self):
        """Logical value for collection/validation, independent of display text."""
        return self._retained_value if self._retained_value is not None else self.text()

    def setPlaceholderText(self, text):
        self._normal_placeholder = text
        if self._retained_value is None:
            super().setPlaceholderText(text)

    def setText(self, text):
        old_value = self.value_text()
        with QSignalBlocker(self):
            # Compare the actual Qt representation, including UTF-16 length
            # limits, rather than guessing a safe metadata maximum.
            super().setText(text)
            self._retained_value = text if self.text() != text else None
            retained = self._retained_value is not None
            if retained:
                super().setText('')
            self.setReadOnly(retained)
            self.replace_value_action.setVisible(retained)
            super().setPlaceholderText(
                'Value too long to edit — use Replace value' if retained
                else self._normal_placeholder
            )
        if old_value != self.value_text():
            self.textChanged.emit(self.value_text())

    def _replace_value(self):
        if not self.isEnabled() or self._retained_value is None:
            return
        with QSignalBlocker(self):
            self.setText('')
            self.setPlaceholderText('')
        # Explicit replacement participates in the ordinary pending-edit model.
        self.textEdited.emit('')
        self.textChanged.emit('')
        self.setFocus()
