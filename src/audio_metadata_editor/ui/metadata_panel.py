from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..metadata.model import Metadata
from .existing_values_edit import ExistingValuesEdit, MIXED_PLACEHOLDER
from .metadata_line_edit import MetadataLineEdit


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

        self.title_edit = ExistingValuesEdit()
        self.artist_edit = ExistingValuesEdit()
        self.album_edit = ExistingValuesEdit()
        self.album_artist_edit = ExistingValuesEdit()
        self.genre_edit = ExistingValuesEdit()
        self.track_edit = MetadataLineEdit()
        self.track_total_edit = MetadataLineEdit()
        self.disc_edit = MetadataLineEdit()
        self.disc_total_edit = MetadataLineEdit()
        self.narrator_edit = ExistingValuesEdit()
        self.series_edit = ExistingValuesEdit()
        self.series_number_edit = ExistingValuesEdit()
        self.publisher_edit = ExistingValuesEdit()
        self.date_edit = ExistingValuesEdit()
        self.composer_edit = ExistingValuesEdit()
        self.comment_edit = ExistingValuesEdit()
        self.id3v1_comment_edit = ExistingValuesEdit()
        self.copyright_edit = ExistingValuesEdit()
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

    def numeric_field_texts(self):
        """Return raw numeric text in validation order, keyed by display name."""
        return {
            "Track": self.track_edit.value_text(),
            "Track Total": self.track_total_edit.value_text(),
            "Disc": self.disc_edit.value_text(),
            "Disc Total": self.disc_total_edit.value_text(),
        }

    def focus_numeric_field(self, name):
        """Focus and select an invalid numeric value after its warning closes."""
        widget = {
            "Track": self.track_edit,
            "Track Total": self.track_total_edit,
            "Disc": self.disc_edit,
            "Disc Total": self.disc_total_edit,
        }[name]
        widget.setFocus()
        widget.selectAll()

    def focus_date_field(self):
        """Select the attempted Date after a validation warning."""
        self.date_edit.setFocus()
        self.date_edit.selectAll()

    def focus_field(self, field):
        widget = self._editors[field]
        widget.setFocus()
        widget.selectAll()

    def set_id3v1_comment_enabled(self, enabled):
        """Apply the caller's ID3v1 Comment availability decision."""
        self.id3v1_comment_edit.setEnabled(enabled)

    def set_highlighted_fields(self, fields):
        """Render supplied edit intent without owning or changing it."""
        for field, widget in self._editors.items():
            widget.setStyleSheet(
                "background-color: #fff3cd; color: black;" if field in fields else ""
            )

    @property
    def field_names(self):
        return tuple(self._editors)

    def set_existing_values(self, baselines):
        """Present ordered accepted multi-file values without changing edit intent."""
        for field, widget in self._editors.items():
            if isinstance(widget, ExistingValuesEdit):
                widget.set_existing_values(
                    [baseline[field] for baseline in baselines if field in baseline]
                    if len(baselines) > 1 else None
                )

    def set_metadata(self, metadata):
        """Display editor values only; artwork and capabilities stay with the caller."""
        self.set_existing_values(())
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
                    MIXED_PLACEHOLDER if mixed else ""
                )
                if isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(text)
                else:
                    widget.setText(text)

    def collect_metadata(self):
        """Collect editor values without validation or artwork/pending-state ownership."""
        values = {}
        for field, widget in self._editors.items():
            text = widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.value_text()
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
