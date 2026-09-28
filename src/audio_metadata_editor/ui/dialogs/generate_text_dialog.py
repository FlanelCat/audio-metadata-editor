from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHeaderView, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
)
from ...text_template import TemplateError, parse_template, evaluate_template

TARGETS = {
    'title': 'Title', 'artist': 'Artist', 'album': 'Album', 'album_artist': 'Album Artist',
    'genre': 'Genre', 'date': 'Date', 'composer': 'Composer', 'publisher': 'Publisher',
    'copyright': 'Copyright', 'narrator': 'Narrator', 'series': 'Series', 'series_number': 'Series Number',
}


class GenerateTextDialog(QDialog):
    """Preview immutable accepted contexts; expose values only after Apply."""

    def __init__(self, targets, parent=None, *, initial_field='title',
                 initial_template='Chapter {track:02}'):
        super().__init__(parent)
        self.targets = tuple((path, dict(context)) for path, context in targets)
        self.generated = None
        self.setWindowTitle('Generate Text')
        self.resize(650, 420)
        layout = QFormLayout(self)
        self.field = QComboBox()
        for name, label in TARGETS.items():
            self.field.addItem(label, name)
        self.field.setCurrentIndex(self.field.findData(initial_field if initial_field in TARGETS else 'title'))
        self.template = QLineEdit(initial_template)
        layout.addRow('Field', self.field)
        layout.addRow('Template', self.template)
        help_text = QLabel('Variables: index, track, disc, title, artist, album, album_artist, narrator, '
                           'series, series_number, date, filename. Use {track:02} for padding; {{ and }} for literal braces. '
                           'Apply creates pending edits; Save Changes writes them. Hover a filename to inspect pending fields without table columns.')
        help_text.setWordWrap(True)
        layout.addRow(help_text)
        self.preview = QTableWidget(len(self.targets), 2)
        self.preview.setHorizontalHeaderLabels(['Filename', 'Generated value / error'])
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addRow(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        self.apply_button = buttons.button(QDialogButtonBox.Apply)
        self.apply_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.field.currentIndexChanged.connect(self._update_preview)
        self.template.textChanged.connect(self._update_preview)
        self._update_preview()

    def _update_preview(self):
        self._values = {}
        error = None
        try:
            tokens = parse_template(self.template.text())
        except TemplateError as exc:
            error = str(exc)
        for row, (path, context) in enumerate(self.targets):
            self.preview.setItem(row, 0, QTableWidgetItem(path.name))
            try:
                if error:
                    raise TemplateError(error)
                value = evaluate_template(tokens, context)
                self._values[path] = value
            except TemplateError as exc:
                value = f'ERROR: {exc}'
            self.preview.setItem(row, 1, QTableWidgetItem(value))
        self.apply_button.setEnabled(bool(self.targets) and self.field.currentData() in TARGETS
                                     and len(self._values) == len(self.targets))

    def accept(self):
        self._update_preview()
        if not self.apply_button.isEnabled():
            return
        self.generated = (self.field.currentData(), dict(self._values))
        super().accept()
