from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..metadata.model import Metadata


class MetadataPanel(QWidget):
    """Present and collect editor values; editing state belongs to MainWindow."""

    field_edited = Signal(str)
    values_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        metadata_layout = QVBoxLayout(self)

        title = QLabel("Metadata")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")

        metadata_layout.addWidget(title)

        self.artwork_label = QLabel()
        self.artwork_label.setFixedSize(250, 250)
        self.artwork_label.setScaledContents(False)
        self.artwork_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        metadata_layout.addWidget(self.artwork_label)

        self.choose_artwork_button = QPushButton("Choose Artwork")
        self.remove_artwork_button = QPushButton("Remove Artwork")

        metadata_layout.addWidget(self.choose_artwork_button)
        metadata_layout.addWidget(self.remove_artwork_button)

        form = QFormLayout()

        self.title_edit = QLineEdit()
        self.artist_edit = QLineEdit()
        self.album_edit = QLineEdit()
        self.album_artist_edit = QLineEdit()
        self.genre_edit = QLineEdit()
        self.track_edit = QLineEdit()
        self.track_total_edit = QLineEdit()
        self.disc_edit = QLineEdit()
        self.disc_total_edit = QLineEdit()
        self.narrator_edit = QLineEdit()
        self.series_edit = QLineEdit()
        self.series_number_edit = QLineEdit()
        self.publisher_edit = QLineEdit()
        self.date_edit = QLineEdit()
        self.composer_edit = QLineEdit()
        self.comment_edit = QLineEdit()
        self.id3v1_comment_edit = QLineEdit()
        self.copyright_edit = QLineEdit()
        self.description_edit = QPlainTextEdit()
        self.description_edit.setMaximumHeight(120)

        form.addRow("Title", self.title_edit)
        form.addRow("Artist", self.artist_edit)
        form.addRow("Album", self.album_edit)
        form.addRow("Album Artist", self.album_artist_edit)
        form.addRow("Genre", self.genre_edit)
        form.addRow("Track", self.track_edit)
        form.addRow("Track Total", self.track_total_edit)
        form.addRow("Disc", self.disc_edit)
        form.addRow("Disc Total", self.disc_total_edit)
        form.addRow("Narrator", self.narrator_edit)
        form.addRow("Series", self.series_edit)
        form.addRow("Series Number", self.series_number_edit)
        form.addRow("Publisher", self.publisher_edit)
        form.addRow("Date", self.date_edit)
        form.addRow("Composer", self.composer_edit)
        form.addRow("Comment", self.comment_edit)
        form.addRow("ID3v1 Comment", self.id3v1_comment_edit)
        form.addRow("Copyright", self.copyright_edit)
        form.addRow("Description", self.description_edit)

        metadata_layout.addLayout(form)
        metadata_layout.addStretch()

        self._editors = {
            "title": self.title_edit,
            "artist": self.artist_edit,
            "album": self.album_edit,
            "album_artist": self.album_artist_edit,
            "genre": self.genre_edit,
            "track_number": self.track_edit,
            "track_total": self.track_total_edit,
            "disc_number": self.disc_edit,
            "disc_total": self.disc_total_edit,
            "narrator": self.narrator_edit,
            "series": self.series_edit,
            "series_number": self.series_number_edit,
            "publisher": self.publisher_edit,
            "date": self.date_edit,
            "composer": self.composer_edit,
            "comment": self.comment_edit,
            "id3v1_comment": self.id3v1_comment_edit,
            "copyright": self.copyright_edit,
            "description": self.description_edit,
        }

        for field, widget in self._editors.items():
            if isinstance(widget, QPlainTextEdit):
                # Description retains its existing textChanged tracking semantics.
                widget.textChanged.connect(
                    lambda field=field: self.field_edited.emit(field)
                )
            else:
                widget.textEdited.connect(
                    lambda text, field=field: self.field_edited.emit(field)
                )
            # Connect after edit forwarding so intent precedes visual refresh.
            widget.textChanged.connect(lambda *args: self.values_changed.emit())

    def set_highlighted_fields(self, fields):
        """Render supplied edit intent without owning or changing it."""
        for field, widget in self._editors.items():
            widget.setStyleSheet(
                "background-color: #fff3cd; color: black;" if field in fields else ""
            )

    @property
    def field_names(self):
        return tuple(self._editors)

    def set_metadata(self, metadata):
        """Display editor values only; artwork and capabilities stay with the caller."""
        self.set_field_values({field: getattr(metadata, field) for field in self._editors})

    def set_field_values(self, values, *, mixed_fields=()):
        """Update supplied fields silently; mixed fields display an empty placeholder."""
        for field, value in values.items():
            widget = self._editors.get(field)
            if widget is None:
                continue
            mixed = field in mixed_fields
            text = "" if mixed or value is None else str(value)
            with QSignalBlocker(widget):
                widget.setPlaceholderText(
                    "<multiple values — edit to apply to all>" if mixed else ""
                )
                if isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(text)
                else:
                    widget.setText(text)

    def collect_metadata(self):
        """Collect editor values without validation or artwork/pending-state ownership."""
        values = {}
        for field, widget in self._editors.items():
            text = widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()
            if field in {"track_number", "track_total", "disc_number", "disc_total"}:
                try:
                    values[field] = int(text.strip()) if text.strip() else None
                except ValueError:
                    values[field] = None
            else:
                values[field] = text
        return Metadata(**values)

    def clear_metadata(self):
        """Reset editor values/placeholders only, without changing artwork or edit state."""
        self.set_metadata(Metadata())
