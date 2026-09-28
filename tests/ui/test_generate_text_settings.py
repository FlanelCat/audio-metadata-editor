"""Last applied UI choices share the isolated application settings store."""
from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from audio_metadata_editor import settings
from audio_metadata_editor.metadata import Metadata
from audio_metadata_editor.ui.dialogs.generate_text_dialog import GenerateTextDialog
from audio_metadata_editor.ui.main_window import MainWindow
import audio_metadata_editor.ui.main_window as module


@pytest.fixture
def make_window(qtbot, monkeypatch):
    path = Path('/virtual/book.mp3')
    monkeypatch.setattr(module, 'read_metadata', lambda p: Metadata(title='Original', track_number=4))
    def make():
        win = MainWindow()
        qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
        win._files_selected([str(path)])
        monkeypatch.setattr(win.file_list, 'selected_paths_in_row_order', lambda: [str(path)])
        return win
    return make


def test_first_use_apply_reopen_and_restart(make_window, monkeypatch):
    win = make_window()
    def apply(dialog):
        assert dialog.field.currentData() == 'title'
        assert dialog.template.text() == 'Chapter {track:02}'
        assert dialog.preview.item(0, 1).text() == 'Chapter 04'
        dialog.field.setCurrentIndex(dialog.field.findData('series'))
        dialog.template.setText('Series {index:03}')
        dialog.accept()
        return dialog.result()
    monkeypatch.setattr(GenerateTextDialog, 'exec', apply)
    win._generate_text()
    assert win.settings.value(settings.GENERATE_TEXT_FIELD_KEY) == 'series'
    assert win.settings.value(settings.GENERATE_TEXT_TEMPLATE_KEY) == 'Series {index:03}'
    assert win._generated_edits[Path('/virtual/book.mp3')] == {'series': 'Series 001'}
    def reopen(dialog):
        assert dialog.field.currentData() == 'series'
        assert dialog.template.text() == 'Series {index:03}'
        assert dialog.preview.item(0, 1).text() == 'Series 001'
        assert dialog.apply_button.isEnabled()
        return QDialog.Rejected
    monkeypatch.setattr(GenerateTextDialog, 'exec', reopen)
    win._generate_text()
    make_window()._generate_text()


@pytest.mark.parametrize('invalid', [False, True])
def test_cancel_or_invalid_apply_does_not_replace_settings(make_window, monkeypatch, invalid):
    win = make_window()
    win.settings.setValue(settings.GENERATE_TEXT_FIELD_KEY, 'title')
    win.settings.setValue(settings.GENERATE_TEXT_TEMPLATE_KEY, 'Saved {track:02}')
    before = deepcopy(win._generated_edits)
    def cancel(dialog):
        dialog.field.setCurrentIndex(dialog.field.findData('series'))
        dialog.template.setText('{unknown}' if invalid else '{album}')
        if invalid:
            assert not dialog.apply_button.isEnabled()
            dialog.accept()
            assert dialog.result() != QDialog.Accepted
        dialog.reject()
        return dialog.result()
    monkeypatch.setattr(GenerateTextDialog, 'exec', cancel)
    win._generate_text()
    assert win.settings.value(settings.GENERATE_TEXT_FIELD_KEY) == 'title'
    assert win.settings.value(settings.GENERATE_TEXT_TEMPLATE_KEY) == 'Saved {track:02}'
    assert win._generated_edits == before


@pytest.mark.parametrize('template', ['Restored {index}', '{obsolete}', ''])
def test_stale_target_falls_back_and_template_is_previewed(make_window, monkeypatch, template):
    store = settings.create_settings()
    store.setValue(settings.GENERATE_TEXT_FIELD_KEY, 'artwork')
    store.setValue(settings.GENERATE_TEXT_TEMPLATE_KEY, template)
    store.sync()
    win = make_window()
    def inspect(dialog):
        assert dialog.field.currentData() == 'title'
        assert dialog.template.text() == template
        assert dialog.apply_button.isEnabled() == (template != '{obsolete}')
        assert dialog.preview.item(0, 1).text() == (
            'ERROR: Unknown variable: obsolete' if template == '{obsolete}'
            else 'Restored 1' if template else '')
        return QDialog.Rejected
    monkeypatch.setattr(GenerateTextDialog, 'exec', inspect)
    win._generate_text()
    assert store.value(settings.GENERATE_TEXT_FIELD_KEY) == 'artwork'
