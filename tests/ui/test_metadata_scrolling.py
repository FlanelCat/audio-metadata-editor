import shutil
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QScrollArea, QFileDialog, QMessageBox
from audio_metadata_editor.ui.main_window import MainWindow
from audio_metadata_editor.metadata import read_metadata

@pytest.fixture(params=[(1024, 600), (1200, 650)])
def window(qtbot, request):
    w = MainWindow()
    qtbot.addWidget(w, before_close_func=lambda w: w._clear_editing_context())
    w.resize(*request.param); w.show()
    QApplication.processEvents()
    assert w.width() <= request.param[0] and w.height() <= request.param[1]
    return w


def visible(scroll, widget):
    return scroll.viewport().rect().contains(widget.mapTo(scroll.viewport(), widget.rect().center()))


def test_small_window_and_bottom_focus(window, qtbot):
    w = window
    assert w.height() <= 650
    scroll = w.centralWidget().widget(2)
    assert isinstance(scroll, QScrollArea) and scroll.widget() is w.metadata_panel
    assert w.centralWidget().widget(0) is w.folder_navigator
    assert w.centralWidget().widget(1) is w.file_list
    assert scroll.verticalScrollBar().maximum() > 0
    assert scroll.horizontalScrollBar().maximum() == 0
    w.copyright_edit.setFocus()
    qtbot.waitUntil(lambda: visible(scroll, w.copyright_edit))
    qtbot.keyClick(w.copyright_edit, Qt.Key_Tab)
    qtbot.waitUntil(lambda: w.description_edit.hasFocus() and visible(scroll, w.description_edit))
    assert scroll.verticalScrollBar().value() > 0
    w.metadata_panel.focus_numeric_field('Track')
    qtbot.waitUntil(lambda: w.track_edit.hasFocus() and visible(scroll, w.track_edit))
    w.metadata_panel.focus_date_field()
    qtbot.waitUntil(lambda: w.date_edit.hasFocus() and visible(scroll, w.date_edit))


def test_small_window_artwork_pending_and_save(window, qtbot, tmp_path, audio_fixture_dir, monkeypatch):
    w = window
    p = tmp_path / 'audio.mp3'
    shutil.copy2(audio_fixture_dir / 'silence.mp3', p)
    w._directory_selected(tmp_path); w.file_list.select_files([str(p)])
    scroll = w.centralWidget().widget(2)
    image_path = tmp_path / 'cover.png'
    image = QImage(2, 2, QImage.Format_RGB32); image.fill(Qt.red); image.save(str(image_path))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(image_path), ''))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    before = p.read_bytes()
    w.choose_artwork_button.setFocus()
    qtbot.waitUntil(lambda: visible(scroll, w.choose_artwork_button))
    qtbot.keyClick(w.choose_artwork_button, Qt.Key_Space)
    assert not w.artwork_label.pixmap().isNull()
    assert w.pending_artwork == image_path.read_bytes()
    w.description_edit.setFocus()
    qtbot.waitUntil(lambda: visible(scroll, w.description_edit))
    qtbot.keyClicks(w.description_edit, 'Pending description')
    assert w._has_unsaved_changes() and p.read_bytes() == before
    w._save_changes()
    assert not w._has_unsaved_changes()
    assert read_metadata(p).description == 'Pending description'
    assert read_metadata(p).artwork == image_path.read_bytes()
    w.remove_artwork_button.setFocus()
    qtbot.waitUntil(lambda: visible(scroll, w.remove_artwork_button))
    qtbot.keyClick(w.remove_artwork_button, Qt.Key_Space)
    assert w._has_unsaved_changes() and w.pending_artwork is None
    w._undo_changes()
    assert not w._has_unsaved_changes() and not w.artwork_label.pixmap().isNull()
