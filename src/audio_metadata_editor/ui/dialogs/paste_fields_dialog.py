from collections.abc import Collection, Mapping

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class PasteFieldsDialog(QDialog):
    """Select logical fields in the supplied order without applying any values."""

    def __init__(self, fields: Mapping[str, str], initial_selection: Collection[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paste Metadata")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select the fields to paste into the selected files:"))

        self._checkboxes = {}
        for field, label in fields.items():
            checkbox = QCheckBox(label)
            checkbox.setChecked(field in initial_selection)
            self._checkboxes[field] = checkbox
            layout.addWidget(checkbox)

        selection_layout = QHBoxLayout()
        select_all_button = QPushButton("Select All")
        clear_all_button = QPushButton("Clear All")
        selection_layout.addWidget(select_all_button)
        selection_layout.addWidget(clear_all_button)
        layout.addLayout(selection_layout)
        select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        clear_all_button.clicked.connect(lambda: self._set_all_checked(False))

        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        paste_button = QPushButton("Paste")
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(paste_button)
        layout.addLayout(button_layout)
        cancel_button.clicked.connect(self.reject)
        paste_button.clicked.connect(self.accept)

    def _set_all_checked(self, checked):
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(checked)

    @property
    def selected_fields(self) -> set[str] | None:
        """A fresh set after acceptance (possibly empty), otherwise None."""
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        return {field for field, checkbox in self._checkboxes.items() if checkbox.isChecked()}
