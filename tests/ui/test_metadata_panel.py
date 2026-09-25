from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLineEdit, QPlainTextEdit, QPushButton

from audio_metadata_editor.ui.metadata_panel import MetadataPanel
from audio_metadata_editor.ui.main_window import MainWindow


FIELDS = [
    ('title_edit', 'Title'), ('artist_edit', 'Artist'), ('album_edit', 'Album'),
    ('album_artist_edit', 'Album Artist'), ('genre_edit', 'Genre'),
    ('track_edit', 'Track'), ('track_total_edit', 'Track Total'),
    ('disc_edit', 'Disc'), ('disc_total_edit', 'Disc Total'),
    ('narrator_edit', 'Narrator'), ('series_edit', 'Series'),
    ('series_number_edit', 'Series Number'), ('publisher_edit', 'Publisher'),
    ('date_edit', 'Date'), ('composer_edit', 'Composer'), ('comment_edit', 'Comment'),
    ('id3v1_comment_edit', 'ID3v1 Comment'), ('copyright_edit', 'Copyright'),
    ('description_edit', 'Description'),
]


def test_controls_and_initial_state(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    form = panel.findChild(QFormLayout)
    assert form.rowCount() == len(FIELDS)
    for row, (name, label) in enumerate(FIELDS):
        widget = getattr(panel, name)
        assert form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget() is widget
        assert form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget().text() == label
        assert widget.parentWidget() is panel
        assert widget.isEnabled()
        assert widget.placeholderText() == ''
        assert widget.toolTip() == ''
        if name == 'description_edit':
            assert isinstance(widget, QPlainTextEdit)
            assert widget.toPlainText() == ''
            assert widget.maximumHeight() == 120
        else:
            assert isinstance(widget, QLineEdit)
            assert widget.text() == ''
            assert widget.validator() is None
    assert panel.choose_artwork_button.text() == 'Choose Artwork'
    assert panel.remove_artwork_button.text() == 'Remove Artwork'
    assert len(panel.findChildren(QPushButton)) == 2
    assert panel.artwork_label.width() == panel.artwork_label.height() == 250
    assert not panel.artwork_label.hasScaledContents()
    assert panel.artwork_label.alignment() == Qt.AlignmentFlag.AlignCenter
    assert panel.artwork_label.pixmap().isNull()
    assert panel.artwork_label.text() == ''
    layout = panel.layout()
    assert layout.itemAt(0).widget().text() == 'Metadata'
    assert layout.itemAt(1).widget() is panel.artwork_label
    assert layout.itemAt(2).widget() is panel.choose_artwork_button
    assert layout.itemAt(3).widget() is panel.remove_artwork_button
    assert layout.itemAt(4).layout() is form
    assert layout.itemAt(5).spacerItem() is not None


def test_tab_order(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.show()
    expected = [panel.choose_artwork_button, panel.remove_artwork_button]
    expected += [getattr(panel, name) for name, _ in FIELDS]
    expected[0].setFocus()
    for current, following in zip(expected, expected[1:]):
        qtbot.keyClick(current, Qt.Key.Key_Tab)
        assert panel.focusWidget() is following


def test_main_window_uses_panel_controls(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    panel = window.metadata_panel
    assert window.centralWidget().widget(2) is panel
    for name, _ in FIELDS:
        assert getattr(window, name) is getattr(panel, name)
    for name in ('artwork_label', 'choose_artwork_button', 'remove_artwork_button'):
        assert getattr(window, name) is getattr(panel, name)
