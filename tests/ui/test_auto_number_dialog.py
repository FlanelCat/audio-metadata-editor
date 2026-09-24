import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit

from audio_metadata_editor.ui.dialogs.auto_number_dialog import AutoNumberDialog


@pytest.fixture
def dialog(qtbot):
    dialog = AutoNumberDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_default(dialog, qtbot):
    assert dialog.starting_number is None
    assert dialog.findChild(QLineEdit).text() == '1'
    buttons = dialog.findChild(QDialogButtonBox)
    qtbot.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.starting_number == 1


@pytest.mark.parametrize('value', ['5', '2147483647'])
def test_accept_positive(dialog, qtbot, value):
    dialog.findChild(QLineEdit).setText(value)
    buttons = dialog.findChild(QDialogButtonBox)
    qtbot.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.starting_number == int(value)


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'abc', '', '2147483648'])
def test_invalid_cannot_be_accepted(dialog, qtbot, value):
    editor = dialog.findChild(QLineEdit)
    editor.setText(value)
    button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    assert not button.isEnabled()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    dialog.accept()
    assert dialog.isVisible()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.starting_number is None


@pytest.mark.parametrize('key', [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_keyboard_accept(dialog, qtbot, key):
    editor = dialog.findChild(QLineEdit)
    editor.setText('8')
    editor.setFocus()
    qtbot.keyClick(editor, key)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.starting_number == 8


@pytest.mark.parametrize('method', ['cancel', 'escape', 'reject'])
def test_rejection_has_no_number(dialog, qtbot, method):
    editor = dialog.findChild(QLineEdit)
    editor.setText('8')
    if method == 'cancel':
        button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel)
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    elif method == 'escape':
        qtbot.keyClick(editor, Qt.Key.Key_Escape)
    else:
        dialog.reject()
    assert not dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.starting_number is None


def test_repeated_construction_resets_default(qtbot):
    for value in ('8', '12'):
        dialog = AutoNumberDialog()
        qtbot.addWidget(dialog)
        assert dialog.starting_number is None
        editor = dialog.findChild(QLineEdit)
        assert editor.text() == '1'
        editor.setText(value)
        dialog.accept()
        assert dialog.starting_number == int(value)
