import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QPushButton

from audio_metadata_editor.ui.dialogs.paste_fields_dialog import PasteFieldsDialog


FIELDS = {'title': 'Title', 'disc_number': 'Disc', 'artwork': 'Artwork'}


def create(qtbot, initial):
    dialog = PasteFieldsDialog(FIELDS, initial)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def click(dialog, qtbot, text):
    button = next(button for button in dialog.findChildren(QPushButton) if button.text() == text)
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)


@pytest.mark.parametrize('initial', [set(), {'disc_number'}, {'title', 'artwork'}])
def test_initial_order_and_identifiers(qtbot, initial):
    dialog = create(qtbot, initial)
    assert dialog.selected_fields is None
    boxes = dialog.findChildren(QCheckBox)
    assert [box.text() for box in boxes] == list(FIELDS.values())
    assert [box.isChecked() for box in boxes] == [field in initial for field in FIELDS]
    click(dialog, qtbot, 'Paste')
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_fields == initial


def test_select_all(qtbot):
    dialog = create(qtbot, set())
    click(dialog, qtbot, 'Select All')
    click(dialog, qtbot, 'Paste')
    assert dialog.selected_fields == set(FIELDS)


def test_clear_all_accepts_empty(qtbot):
    dialog = create(qtbot, set(FIELDS))
    click(dialog, qtbot, 'Clear All')
    click(dialog, qtbot, 'Paste')
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_fields == set()


def test_cancel_does_not_mutate_input(qtbot):
    initial = {'title', 'artwork'}
    dialog = create(qtbot, initial)
    click(dialog, qtbot, 'Clear All')
    click(dialog, qtbot, 'Cancel')
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.selected_fields is None
    assert initial == {'title', 'artwork'}


def test_accepted_selection_is_independent(qtbot):
    initial = {'title'}
    dialog = create(qtbot, initial)
    click(dialog, qtbot, 'Select All')
    click(dialog, qtbot, 'Paste')
    selected = dialog.selected_fields
    assert selected == set(FIELDS)
    selected.remove('artwork')
    assert initial == {'title'}
    assert dialog.selected_fields == set(FIELDS)
    initial.clear()
    assert dialog.selected_fields == set(FIELDS)


def test_artwork_is_an_ordinary_selectable_field(qtbot):
    dialog = create(qtbot, set())
    artwork = next(box for box in dialog.findChildren(QCheckBox) if box.text() == 'Artwork')
    artwork.setChecked(True)
    click(dialog, qtbot, 'Paste')
    assert dialog.selected_fields == {'artwork'}


def test_repeated_construction_uses_supplied_selection(qtbot):
    for initial in ({'artwork'}, set(), {'disc_number'}):
        dialog = create(qtbot, initial)
        click(dialog, qtbot, 'Paste')
        assert dialog.selected_fields == initial
