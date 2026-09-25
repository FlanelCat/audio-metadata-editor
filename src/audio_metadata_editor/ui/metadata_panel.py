from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MetadataPanel(QWidget):
    """Construct the metadata controls; editing behavior belongs to MainWindow."""

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
