from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit


class AutoNumberDialog(QDialog):
    """Collect a validated starting track number without performing any work."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accepted_number = None
        self.setWindowTitle("Auto-number Tracks")
        layout = QFormLayout(self)
        self._number_edit = QLineEdit("1", self)
        self._number_edit.setValidator(QIntValidator(1, 2147483647, self._number_edit))
        layout.addRow("Starting track number", self._number_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addRow(buttons)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._number_edit.textChanged.connect(
            lambda: ok_button.setEnabled(self._number_edit.hasAcceptableInput())
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._number_edit.selectAll()

    def accept(self):
        if not self._number_edit.hasAcceptableInput():
            return
        self._accepted_number = self._number_edit.validator().locale().toInt(
            self._number_edit.text()
        )[0]
        super().accept()

    @property
    def starting_number(self) -> int | None:
        """The accepted integer, or None before acceptance or after rejection."""
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        return self._accepted_number
