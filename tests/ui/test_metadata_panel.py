import pytest

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
    assert window.centralWidget().widget(2).widget() is panel
    for name, _ in FIELDS:
        assert getattr(window, name) is getattr(panel, name)
    for name in ('artwork_label', 'choose_artwork_button', 'remove_artwork_button'):
        assert getattr(window, name) is getattr(panel, name)


def test_metadata_round_trip_and_silent_population(qtbot):
    from dataclasses import fields
    from audio_metadata_editor.metadata.model import Metadata
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    expected = Metadata()
    numeric = {'track_number': 0, 'track_total': 17, 'disc_number': 2, 'disc_total': 5}
    for field in fields(expected):
        if field.name in ('artwork', 'artwork_mime'):
            continue
        setattr(expected, field.name, numeric.get(field.name, f'  {field.name} value  '))
    expected.series_number = '01.50 / part A'
    changes = []
    for name, _ in FIELDS:
        getattr(panel, name).textChanged.connect(lambda *args: changes.append(args))
    panel.set_metadata(expected)
    assert panel.collect_metadata() == expected
    assert panel.series_number_edit.text() == '01.50 / part A'
    assert not changes
    panel.title_edit.setText('User value')
    panel.description_edit.setPlainText('New description\nsecond line')
    collected = panel.collect_metadata()
    assert collected.title == 'User value'
    assert collected.description == 'New description\nsecond line'
    assert len(changes) == 2


def test_numeric_conversion_and_independence(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    for text, expected in [('', None), ('  ', None), (' 007 ', 7), ('0', 0),
                           ('-1', -1), ('1.5', None), ('invalid', None)]:
        panel.track_edit.setText(text)
        panel.track_total_edit.setText('17')
        panel.disc_edit.setText('')
        panel.disc_total_edit.setText('5')
        value = panel.collect_metadata()
        assert value.track_number == expected
        assert value.track_total == 17
        assert value.disc_number is None
        assert value.disc_total == 5
    # Collection remains separate from MainWindow's validation/save policy.
    assert panel.track_edit.text() == 'invalid'


def test_partial_and_mixed_presentation(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.artist_edit.setText('Pending artist')
    panel.set_field_values({'title': 'Common title', 'track_number': None,
                            'description': 'Ignored mixed text'},
                           mixed_fields={'track_number', 'description'})
    assert panel.title_edit.text() == 'Common title'
    assert panel.artist_edit.text() == 'Pending artist'
    assert panel.track_edit.text() == ''
    assert panel.description_edit.toPlainText() == ''
    assert panel.track_edit.placeholderText() == '<multiple values — edit to apply to all>'
    assert panel.description_edit.placeholderText() == panel.track_edit.placeholderText()
    panel.set_field_values({'track_number': 8, 'description': 'One description'})
    assert panel.track_edit.text() == '8'
    assert panel.track_edit.placeholderText() == ''
    assert panel.description_edit.placeholderText() == ''


def test_clear_resets_editors_only(qtbot):
    from audio_metadata_editor.metadata.model import Metadata
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.set_metadata(Metadata(title='Title', track_number=3, series_number='2.5'))
    panel.set_field_values({'artist': None}, mixed_fields={'artist'})
    panel.artwork_label.setText('Artwork state owned by caller')
    panel.id3v1_comment_edit.setEnabled(False)
    panel.clear_metadata()
    assert panel.collect_metadata() == Metadata()
    assert all(getattr(panel, name).placeholderText() == '' for name, _ in FIELDS)
    assert panel.artwork_label.text() == 'Artwork state owned by caller'
    assert not panel.id3v1_comment_edit.isEnabled()


def test_panel_does_not_collect_or_render_artwork(qtbot):
    from audio_metadata_editor.metadata.model import Metadata
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.artwork_label.setText('Caller preview')
    panel.set_metadata(Metadata(title='Title', artwork=b'cover', artwork_mime='image/png'))
    assert panel.artwork_label.text() == 'Caller preview'
    assert panel.collect_metadata().artwork is None
    assert panel.collect_metadata().artwork_mime == ''


# Explicit expectations protect logical identifiers independently of the panel map.
SIGNAL_FIELDS = [
    (name, {'track_edit': 'track_number', 'disc_edit': 'disc_number'}.get(
        name, name.removesuffix('_edit')))
    for name, _ in FIELDS
]


def test_all_editor_signal_identifiers_and_order(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    events = []
    panel.field_edited.connect(lambda field: events.append(('edited', field)))
    panel.values_changed.connect(lambda: events.append(('changed',)))
    for name, field in SIGNAL_FIELDS:
        events.clear()
        qtbot.keyClicks(getattr(panel, name), '7')
        assert events == [('edited', field), ('changed',)]


def test_programmatic_signal_semantics(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    events = []
    panel.field_edited.connect(lambda field: events.append(('edited', field)))
    panel.values_changed.connect(lambda: events.append(('changed',)))
    for name, _ in SIGNAL_FIELDS:
        events.clear()
        widget = getattr(panel, name)
        if isinstance(widget, QPlainTextEdit):
            widget.setPlainText('Description')
            assert events == [('edited', 'description'), ('changed',)]
        else:
            widget.setText('Programmatic value')
            assert events == [('changed',)]


def test_population_keeps_semantic_signals_silent(qtbot):
    from audio_metadata_editor.metadata.model import Metadata
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    events = []
    panel.field_edited.connect(lambda field: events.append(field))
    panel.values_changed.connect(lambda: events.append('changed'))
    panel.set_metadata(Metadata(title='Loaded', track_number=3, description='Loaded'))
    assert not events
    panel.set_field_values({'title': 'Partial', 'description': None, 'track_number': None},
                           mixed_fields={'description', 'track_number'})
    assert not events
    panel.clear_metadata()
    assert not events


def test_highlight_changes_and_reset(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    for highlighted in ({'title'}, {'track_number', 'description'}, {'artist'}, set()):
        panel.set_highlighted_fields(highlighted)
        for name, field in SIGNAL_FIELDS:
            assert getattr(panel, name).styleSheet() == (
                'background-color: #fff3cd; color: black;' if field in highlighted else '')


def test_numeric_text_and_focus_api(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.show()
    values = {'track_number': ' 007 ', 'track_total': '',
              'disc_number': '-1', 'disc_total': 'invalid',
              'series_number': '01.50 / part A'}
    panel.set_field_values(values)
    events = []
    panel.values_changed.connect(lambda: events.append('changed'))
    panel.field_edited.connect(events.append)
    assert panel.numeric_field_texts() == {
        'Track': ' 007 ', 'Track Total': '', 'Disc': '-1', 'Disc Total': 'invalid'}
    for label, editor in [('Track', panel.track_edit), ('Track Total', panel.track_total_edit),
                          ('Disc', panel.disc_edit), ('Disc Total', panel.disc_total_edit)]:
        panel.focus_numeric_field(label)
        assert panel.focusWidget() is editor
        assert editor.selectedText() == editor.text()
    assert panel.series_number_edit.text() == values['series_number']
    assert not events


def test_comment_enablement_api_is_silent(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.set_field_values({'id3v1_comment': 'Preserve'})
    events = []
    panel.values_changed.connect(lambda: events.append('changed'))
    panel.field_edited.connect(events.append)
    for enabled in (False, True, False):
        panel.set_id3v1_comment_enabled(enabled)
        assert panel.id3v1_comment_edit.isEnabled() == enabled
        assert panel.collect_metadata().id3v1_comment == 'Preserve'
        assert panel.comment_edit.isEnabled()
    assert not events


@pytest.mark.parametrize('field,label,editor_name', [
    ('track_number', 'Track', 'track_edit'),
    ('track_total', 'Track Total', 'track_total_edit'),
    ('disc_number', 'Disc', 'disc_edit'),
    ('disc_total', 'Disc Total', 'disc_total_edit'),
])
@pytest.mark.parametrize('text,error', [
    ('', None), ('  ', None), ('0', None), (' 007 ', None),
    ('-1', 'cannot be negative.'), ('1.5', 'must be a whole number.'),
    ('invalid', 'must be a whole number.'),
])
def test_window_numeric_validation(qtbot, monkeypatch, field, label, editor_name, text, error):
    from PySide6.QtWidgets import QMessageBox
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    panel = window.metadata_panel
    panel.set_field_values({'track_number': 2, 'track_total': 17,
                            'disc_number': 1, 'disc_total': 5,
                            'series_number': 'not a number', field: text})
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[1:]))
    assert window._validate_numeric_fields() == (error is None)
    if error:
        assert warnings == [('Invalid Number', f'{label} {error}')]
        editor = getattr(panel, editor_name)
        assert panel.focusWidget() is editor
        assert editor.selectedText() == text
    else:
        assert not warnings
    assert not window._has_unsaved_changes()


def test_window_format_enablement(qtbot):
    from pathlib import Path
    from audio_metadata_editor.metadata.model import Metadata
    window = MainWindow()
    qtbot.addWidget(window)
    for suffix, enabled in [('.mp3', True), ('.m4b', False), ('.MP3', True)]:
        window.current_file = Path('sample' + suffix)
        window._show_metadata(Metadata())
        assert window.metadata_panel.id3v1_comment_edit.isEnabled() == enabled
        assert not window._has_unsaved_changes()
    window._clear_editing_context()
    assert not window.metadata_panel.id3v1_comment_edit.isEnabled()
    assert not window._has_unsaved_changes()
