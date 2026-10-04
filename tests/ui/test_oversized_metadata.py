"""Panel display limits must never manufacture metadata edit intent."""
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QToolButton

from audio_metadata_editor.metadata import Metadata, read_metadata, write_mp3_metadata, write_m4b_metadata
from audio_metadata_editor.ui.main_window import MainWindow
from audio_metadata_editor.ui.metadata_panel import MetadataPanel
from audio_metadata_editor.editing_rules import SCALAR_FIELDS

LONG = 'A' * 40000


@pytest.fixture(params=['mp3', 'm4b'])
def loaded(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{i}.{request.param}' for i in range(2)]
    writer = write_mp3_metadata if request.param == 'mp3' else write_m4b_metadata
    for path in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        writer(path, Metadata(title=LONG, publisher=LONG, series_number=LONG,
                              description=LONG))
    window = MainWindow()
    qtbot.addWidget(window, before_close_func=lambda w: w._clear_editing_context())
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    window._directory_selected(tmp_path)
    window.file_list.select_files([str(paths[0])])
    return window, paths


def test_loading_is_clean(loaded):
    window, paths = loaded
    assert not window._has_unsaved_changes()
    assert window._get_edited_metadata() == read_metadata(paths[0])


def test_unrelated_save_preserves_long_values(loaded, qtbot):
    window, paths = loaded
    qtbot.keyClicks(window.artist_edit, 'Artist')
    window._save_changes()
    saved = read_metadata(paths[0])
    assert saved.artist == 'Artist'
    for field in ('title', 'publisher', 'series_number', 'description'):
        assert getattr(saved, field) == LONG


@pytest.mark.parametrize('field', sorted(SCALAR_FIELDS - {'description'}))
def test_every_single_line_field_retains_unrepresentable_value(qtbot, field):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    numeric = field in {'track_number', 'track_total', 'disc_number', 'disc_total'}
    value = 12345 if numeric else LONG
    editor = panel._editors[field]
    # Exercise the invariant at the widget's actual limit, even for numbers.
    if numeric:
        editor.setMaxLength(2)
    events = []
    panel.field_edited.connect(events.append)
    panel.values_changed.connect(lambda: events.append('changed'))
    panel.set_field_values({field: value})
    assert events == []
    assert getattr(panel.collect_metadata(), field) == value
    assert editor.isReadOnly()
    assert editor.text() == ''  # No truncated prefix masquerading as the value.
    assert 'too long' in editor.placeholderText()
    editor.replace_value_action.trigger()
    qtbot.keyClicks(editor, '1' if numeric else 'Replacement')
    assert getattr(panel.collect_metadata(), field) == (1 if numeric else 'Replacement')
    panel.set_field_values({field: value})
    panel.clear_metadata()
    assert not editor.isReadOnly()
    assert not editor.replace_value_action.isVisible()


def test_utf16_limit_and_description(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    value = '\U0001f600' * 20000  # Python length fits; Qt UTF-16 length does not.
    panel.set_field_values({'title': value, 'description': LONG})
    assert panel.title_edit.isReadOnly()
    assert panel.collect_metadata().title == value
    assert panel.description_edit.toPlainText() == LONG
    assert panel.collect_metadata().description == LONG


def test_intentional_replacement_via_button(loaded, qtbot):
    window, paths = loaded
    window.show()
    editor = window.title_edit
    button = next(b for b in editor.findChildren(QToolButton)
                  if b.defaultAction() == editor.replace_value_action)
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.keyClicks(editor, 'Replacement')
    assert window._has_unsaved_changes()
    assert read_metadata(paths[0]).title == LONG
    window._save_changes()
    assert read_metadata(paths[0]).title == 'Replacement'
    assert read_metadata(paths[0]).publisher == LONG
    assert not window._has_unsaved_changes()


@pytest.mark.parametrize('reply', [QMessageBox.Discard, QMessageBox.Cancel])
def test_undo_and_guarded_navigation(loaded, qtbot, monkeypatch, reply):
    window, paths = loaded
    window.title_edit.replace_value_action.trigger()
    qtbot.keyClicks(window.title_edit, 'Replacement')
    window._undo_changes()
    assert window._get_edited_metadata().title == LONG
    assert not window._has_unsaved_changes()
    qtbot.keyClicks(window.artist_edit, 'Pending')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: reply)
    window.file_list.select_files([str(paths[1])])
    assert window._get_edited_metadata().title == LONG
    assert window.current_file == paths[1 if reply == QMessageBox.Discard else 0]
    if reply == QMessageBox.Cancel:
        window._undo_changes()
    window.file_list.select_files([str(paths[0])])
    assert not window._has_unsaved_changes()
    assert all(read_metadata(p).title == LONG for p in paths)


def choose_title(window, value):
    editor = window.title_edit
    action = next(a for a in editor._menu.actions() if a.data() == value)
    editor._choose_value(action)


def test_common_long_value_and_dropdown_restoration(loaded, qtbot):
    window, paths = loaded
    window.file_list.select_files([str(p) for p in paths])
    assert not window._has_unsaved_changes()
    assert window._get_edited_metadata().title == LONG
    window.title_edit.replace_value_action.trigger()
    qtbot.keyClicks(window.title_edit, 'Replacement')
    assert 'title' in window.multi_edit_fields
    choose_title(window, LONG)
    assert 'title' not in window.multi_edit_fields
    assert not window._has_unsaved_changes()
    qtbot.keyClicks(window.artist_edit, 'Artist')
    window._save_changes()
    assert all(read_metadata(p).title == LONG for p in paths)
    assert not window._has_unsaved_changes()


def test_mixed_dropdown_and_per_file_markers(loaded):
    window, paths = loaded
    writer = write_mp3_metadata if paths[1].suffix == '.mp3' else write_m4b_metadata
    writer(paths[1], Metadata(title='Short'), fields={'title'})
    window.file_list.select_files([str(p) for p in paths])
    assert not window.title_edit.isReadOnly()
    choose_title(window, LONG)
    assert window._get_edited_metadata().title == LONG
    assert window.multi_edit_fields == {'title'}
    markers = {window.file_list.item(r, 0).data(256): window.file_list.item(r, 0).text().startswith('*')
               for r in range(window.file_list.rowCount())}
    assert markers == {str(paths[0]): False, str(paths[1]): True}
    window._save_changes()
    assert all(read_metadata(p).title == LONG for p in paths)


@pytest.mark.parametrize('operation', ['generate', 'copy'])
def test_per_file_pending_values_survive_panel_representation(loaded, operation):
    window, paths = loaded
    window.file_list.select_files([str(p) for p in paths])
    value = LONG + 'generated'
    if operation == 'generate':
        window._apply_generated('title', {p: value for p in paths})
    else:
        window._copy_table_values('title', {str(paths[1]): value})
    assert window._has_unsaved_changes()
    window._save_changes()
    assert read_metadata(paths[1]).title == value
    assert read_metadata(paths[0]).title == (value if operation == 'generate' else LONG)
    assert not window._has_unsaved_changes()


@pytest.mark.parametrize('multi', [False, True])
def test_long_pending_value_survives_write_uncertainty(loaded, monkeypatch, multi):
    import audio_metadata_editor.ui.main_window as module
    window, paths = loaded
    selected = paths if multi else paths[:1]
    window.file_list.select_files([str(p) for p in selected])
    value = LONG + 'pending'
    window._apply_generated('title', {p: value for p in selected})
    name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, name)
    def fail_after_write(*args, **kwargs):
        writer(*args, **kwargs)
        raise OSError('injected after-write failure')
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a))
    monkeypatch.setattr(module, name, fail_after_write)
    window._save_changes()
    assert errors and window._has_unsaved_changes()
    assert window._get_edited_metadata().title == value
    monkeypatch.setattr(module, name, writer)
    window._save_changes()
    assert all(read_metadata(p).title == value for p in selected)
    assert not window._has_unsaved_changes()


def test_immediate_save_synchronizes_full_panel_value(loaded):
    window, paths = loaded
    value = LONG + 'immediate'
    window._save_table_cell(str(paths[0]), 2, value)
    assert window.file_list.cell_save_succeeded
    assert window._get_edited_metadata().title == value
    assert read_metadata(paths[0]).title == value
    assert not window._has_unsaved_changes()
