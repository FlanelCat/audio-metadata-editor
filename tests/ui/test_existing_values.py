"""Existing-value choices are pending input, never a persistence operation."""
from copy import deepcopy
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QMessageBox

from audio_metadata_editor.metadata import Metadata, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.ui.existing_values_edit import ExistingValuesEdit, MIXED_PLACEHOLDER
from audio_metadata_editor.ui.metadata_panel import MetadataPanel
import audio_metadata_editor.ui.main_window as module


TEXT_FIELDS = ('title', 'artist', 'album', 'album_artist', 'genre', 'date',
               'composer', 'comment', 'id3v1_comment', 'publisher', 'copyright',
               'narrator', 'series', 'series_number')


def menu(editor):
    return editor.findChild(QMenu)


def choices(editor):
    return [action.data() for action in menu(editor).actions()]


def choose(editor, value):
    next(action for action in menu(editor).actions() if action.data() == value).trigger()


@pytest.fixture
def panel(qtbot):
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.show()
    return panel


@pytest.mark.parametrize('field', TEXT_FIELDS)
def test_text_fields_have_silent_ordered_choices(panel, field):
    edits, changes = [], []
    panel.field_edited.connect(edits.append)
    panel.values_changed.connect(lambda: changes.append(True))
    widget = getattr(panel, field + '_edit')
    assert isinstance(widget, ExistingValuesEdit)
    panel.set_field_values({field: None}, mixed_fields={field})
    values = ['Stephen Fry', 'Jim Dale', 'Stephen Fry', '', 'jim dale', ' Jim Dale ', MIXED_PLACEHOLDER]
    panel.set_existing_values([{field: value} for value in values])
    assert choices(widget) == ['', 'Stephen Fry', 'Jim Dale', 'jim dale', ' Jim Dale ']
    assert widget.text() == '' and widget.placeholderText() == MIXED_PLACEHOLDER
    assert not edits and not changes
    choose(widget, ' Jim Dale ')
    assert getattr(panel.collect_metadata(), field) == ' Jim Dale '
    assert edits == [field] and changes == [True]


def test_empty_label_is_distinct_from_literal_metadata(panel):
    panel.set_existing_values([{'artist': ''}, {'artist': 'Empty'}, {'artist': 'A&B'}])
    editor = panel.artist_edit
    assert menu(editor).actions()[0].text() == 'Empty'
    assert choices(editor) == ['', 'Empty', 'A&B']
    choose(editor, '')
    assert panel.collect_metadata().artist == ''
    choose(editor, 'Empty')
    assert panel.collect_metadata().artist == 'Empty'
    choose(editor, 'A&B')
    assert panel.collect_metadata().artist == 'A&B'


def test_open_navigation_dismiss_and_keyboard_commit(panel, qtbot):
    editor = panel.artist_edit
    panel.set_field_values({'artist': None}, mixed_fields={'artist'})
    panel.set_existing_values([{'artist': 'A'}, {'artist': 'B'}])
    edits, changes = [], []
    panel.field_edited.connect(edits.append)
    panel.values_changed.connect(lambda: changes.append(True))
    editor.setFocus()
    qtbot.keyClick(editor, Qt.Key_Down, Qt.AltModifier)
    assert menu(editor).isVisible()
    qtbot.keyClick(menu(editor), Qt.Key_Down)
    qtbot.keyClick(menu(editor), Qt.Key_Down)
    assert not edits and not changes and editor.text() == ''
    qtbot.keyClick(menu(editor), Qt.Key_Escape)
    assert not edits and not changes and editor.placeholderText() == MIXED_PLACEHOLDER
    editor.show_existing_values()
    action = next(a for a in menu(editor).actions() if a.data() == 'B')
    menu(editor).setActiveAction(action)
    qtbot.keyClick(menu(editor), Qt.Key_Return)
    assert editor.text() == 'B' and edits == ['artist'] and changes == [True]


def test_rebuild_preserves_pending_text_and_size(panel):
    editor = panel.artist_edit
    panel.set_existing_values([{'artist': 'A'}, {'artist': 'B'}])
    choose(editor, 'A')
    editor.setText('pending')
    size = panel.sizeHint()
    edits = []
    panel.field_edited.connect(edits.append)
    panel.set_existing_values([{'artist': 'Long metadata ' * 100}, {'artist': 'C'}])
    assert editor.text() == 'pending' and not edits
    assert panel.sizeHint().width() == size.width()
    panel.set_metadata(Metadata(artist='single'))
    assert choices(editor) == [] and editor.text() == 'single'
    assert not editor.actions()[0].isVisible()
    assert not isinstance(panel.track_edit, ExistingValuesEdit)
    assert not isinstance(panel.description_edit, ExistingValuesEdit)


@pytest.fixture
def context(qtbot, monkeypatch):
    disk = {Path('/virtual/a.mp3'): Metadata(artist='A'),
            Path('/virtual/b.mp3'): Metadata(artist='B'),
            Path('/virtual/c.mp3'): Metadata(artist='A'),
            Path('/virtual/d.m4b'): Metadata(artist='D')}
    monkeypatch.setattr(module, 'read_metadata', lambda path: deepcopy(disk[Path(path)]))
    win = module.MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.show()
    def unexpected(*args, **kwargs):
        pytest.fail('Unexpected write or dialog')
    monkeypatch.setattr(module, 'write_mp3_metadata', unexpected)
    monkeypatch.setattr(module, 'write_m4b_metadata', unexpected)
    monkeypatch.setattr(QMessageBox, 'critical', unexpected)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    monkeypatch.setattr(QMessageBox, 'question', unexpected)
    return win, disk


def select(win, paths):
    assert win._files_selected([str(p) for p in paths])


@pytest.mark.parametrize('values,choice,pending', [
    (['A', 'A'], 'A', False), (['', ''], '', False),
    (['A', 'B'], 'A', True), (['A', 'B'], '', True), (['', 'B'], '', True),
])
def test_existing_effective_intent(context, values, choice, pending):
    win, disk = context
    paths = list(disk)[:2]
    for path, value in zip(paths, values):
        disk[path].artist = value
    select(win, paths)
    assert not win._has_unsaved_changes()
    choose(win.artist_edit, choice)
    assert win.artist_edit.text() == choice
    assert win.multi_edit_fields == ({'artist'} if pending else set())
    assert win._has_unsaved_changes() == pending
    assert bool(win.artist_edit.styleSheet()) == pending


@pytest.mark.parametrize('start,typed', [('mixed', 'new value'), ('common', 'new value'),
                                        ('chosen', 'edited choice'), ('empty', 'after empty'),
                                        ('common', 'A'), ('mixed', 'A')])
def test_arbitrary_typing_and_restoration(context, qtbot, start, typed):
    win, disk = context
    paths = list(disk)[:2]
    if start == 'common':
        disk[paths[1]].artist = 'A'
    select(win, paths)
    if start in ('chosen', 'empty'):
        choose(win.artist_edit, 'B' if start == 'chosen' else '')
    win.artist_edit.selectAll()
    qtbot.keyClicks(win.artist_edit, typed)
    assert win.artist_edit.text() == typed
    assert win._has_unsaved_changes() == (start != 'common' or typed != 'A')
    if start == 'common':
        choose(win.artist_edit, 'A')
        assert not win.multi_edit_fields and not win._has_unsaved_changes()


def test_selection_order_and_context_replacement(context):
    win, disk = context
    a, b, c, d = disk
    select(win, [a])
    assert choices(win.artist_edit) == []
    select(win, [b, a, c])
    assert choices(win.artist_edit) == ['', 'B', 'A']
    select(win, [c, d])
    assert choices(win.artist_edit) == ['', 'A', 'D']
    select(win, [d])
    assert choices(win.artist_edit) == []
    select(win, [a, b])
    select(win, [])
    assert choices(win.artist_edit) == []


def test_cancel_and_discard_use_accepted_context(context, monkeypatch):
    win, disk = context
    a, b, c, d = disk
    select(win, [a, b])
    choose(win.artist_edit, 'B')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Cancel)
    assert not win._files_selected([str(c), str(d)])
    assert win.artist_edit.text() == 'B' and choices(win.artist_edit) == ['', 'A', 'B']
    assert win.multi_edit_fields == {'artist'}
    disk[a].artist = 'disk truth'
    win._undo_changes()
    assert choices(win.artist_edit) == ['', 'disk truth', 'B']
    assert win.artist_edit.placeholderText() == MIXED_PLACEHOLDER
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('suffixes,enabled', [(['mp3', 'mp3'], True), (['m4b', 'm4b'], False), (['mp3', 'm4b'], False)])
def test_format_applicability(context, suffixes, enabled):
    win, disk = context
    paths = [Path(f'/virtual/{i}.{suffix}') for i, suffix in enumerate(suffixes)]
    for path in paths:
        disk[path] = Metadata(id3v1_comment='comment')
    select(win, paths)
    assert win.id3v1_comment_edit.isEnabled() == enabled
    choose(win.id3v1_comment_edit, '')
    assert ('id3v1_comment' in win.multi_edit_fields) == enabled


def test_verification_rebuild_is_silent_and_keeps_pending_value(context):
    win, disk = context
    a, b, *_ = disk
    select(win, [a, b])
    choose(win.artist_edit, 'B')
    edits, changes = [], []
    win.metadata_panel.field_edited.connect(edits.append)
    win.metadata_panel.values_changed.connect(lambda: changes.append(True))
    disk[a].artist = 'verified'
    win._unverified_fields[a] = {'artist'}
    win._verify_field_saves()
    assert choices(win.artist_edit) == ['', 'verified', 'B']
    assert win.artist_edit.text() == 'B' and win.multi_edit_fields == {'artist'}
    assert not edits and not changes


@pytest.fixture(params=['mp3', 'm4b'])
def media(request, qtbot, tmp_path, audio_fixture_dir, monkeypatch):
    paths = [tmp_path / f'{name}.{request.param}' for name in 'abc']
    for path, artist in zip(paths, ['A', 'B', 'A']):
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        write_metadata(path, Metadata(title=path.stem, artist=artist, track_number=4, track_total=17))
    win = module.MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.file_list.sortItems(0, Qt.AscendingOrder)
    win.root_path = tmp_path
    win._populate_root()
    win.file_list.select_files([str(p) for p in paths[:2]])
    win.show()
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: pytest.fail(str(args)))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: pytest.fail(str(args)))
    return win, paths


@pytest.mark.parametrize('value', ['B', ''])
def test_save_is_explicit_and_refreshes_choices(media, qtbot, value):
    win, paths = media
    before = {p: p.read_bytes() for p in paths}
    metadata = {p: read_metadata(p) for p in paths}
    editor = win.artist_edit
    editor.show_existing_values()
    action = next(a for a in menu(editor).actions() if a.data() == value)
    qtbot.mouseClick(menu(editor), Qt.LeftButton, pos=menu(editor).actionGeometry(action).center())
    qtbot.keyClick(editor, Qt.Key_Return)
    assert {p: p.read_bytes() for p in paths} == before
    assert win.multi_edit_fields == {'artist'}
    assert dirty_paths(win) == ({paths[0]} if value == 'B' else set(paths[:2]))
    win._save_changes()
    for path in paths[:2]:
        metadata[path].artist = value
    assert {p: read_metadata(p) for p in paths} == metadata
    assert paths[2].read_bytes() == before[paths[2]]
    assert choices(editor) == (['', value] if value else [''])
    assert not dirty_paths(win)
    assert editor.text() == value and not editor.placeholderText()
    assert not win._has_unsaved_changes()


def test_save_guard_rebuilds_new_selection_choices(media, monkeypatch):
    win, paths = media
    choose(win.artist_edit, 'B')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Save)
    win.file_list.select_files([str(p) for p in paths[1:]])
    assert read_metadata(paths[0]).artist == 'B'
    assert choices(win.artist_edit) == ['', 'B', 'A']
    assert win.artist_edit.placeholderText() == MIXED_PLACEHOLDER
    assert not win._has_unsaved_changes()


def test_partial_save_choices_cannot_clear_unresolved_intent(media, monkeypatch):
    win, paths = media
    choose(win.artist_edit, 'B')
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    def fail(*args, **kwargs):
        writer(*args, **kwargs)
        raise OSError('injected partial save')
    with monkeypatch.context() as patch:
        patch.setattr(module, writer_name, fail)
        patch.setattr(QMessageBox, 'critical', lambda *args: None)
        win._save_changes()
    assert win._unresolved_multi_fields == {'artist'}
    assert dirty_paths(win) == set(paths[:2])
    # The failed target no longer has a trustworthy accepted Artist baseline.
    assert choices(win.artist_edit) == ['', 'B']
    choose(win.artist_edit, 'B')
    assert win.multi_edit_fields == {'artist'} and win._has_unsaved_changes()
    choose(win.artist_edit, '')
    win._save_changes()
    assert all(read_metadata(p).artist == '' for p in paths[:2])
    assert choices(win.artist_edit) == ['']
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('action', ['refresh', 'directory'])
def test_directory_context_clears_choices(media, tmp_path, action):
    win, _ = media
    assert choices(win.artist_edit) == ['', 'A', 'B']
    if action == 'refresh':
        win._refresh_tree()
    else:
        empty = tmp_path / 'empty'
        empty.mkdir()
        win._directory_selected(empty)
    assert choices(win.artist_edit) == []
    assert win.selected_files == [] and not win._has_unsaved_changes()


def test_cached_common_choice_retains_unresolved_intent(context):
    win, disk = context
    a, b, *_ = disk
    disk[b].artist = 'A'
    select(win, [a, b])
    win._unresolved_multi_fields.add('artist')
    choose(win.artist_edit, 'A')
    assert win.multi_edit_fields == {'artist'}
    assert win._has_unsaved_changes()


def test_dropdown_button_opens_without_editing(panel, qtbot):
    from PySide6.QtWidgets import QToolButton
    panel.set_existing_values([{'artist': 'A'}, {'artist': 'B'}])
    edits = []
    panel.field_edited.connect(edits.append)
    button = next(b for b in panel.artist_edit.findChildren(QToolButton)
                  if b.defaultAction() == panel.artist_edit._dropdown)
    assert button is not None and button.isVisible()
    qtbot.mouseClick(button, Qt.LeftButton)
    assert menu(panel.artist_edit).isVisible()
    qtbot.keyClick(menu(panel.artist_edit), Qt.Key_Escape)
    assert not edits


def dirty_paths(win):
    return {Path(win.file_list.item(row, 0).data(256))
            for row in range(win.file_list.rowCount())
            if win.file_list.item(row, 0).text().startswith('*')}


@pytest.fixture
def row_context(context):
    from PySide6.QtWidgets import QTableWidgetItem
    win, disk = context
    win.file_list.setSortingEnabled(False)
    win.file_list.setRowCount(len(disk))
    for row, path in enumerate(disk):
        item = QTableWidgetItem(path.name)
        item.setData(256, str(path))
        win.file_list.setItem(row, 0, item)
        for column in range(1, 8):
            win.file_list.setItem(row, column, QTableWidgetItem(""))
    win.file_list.setSortingEnabled(True)
    win.file_list.sortItems(0, Qt.AscendingOrder)
    return win, disk


@pytest.mark.parametrize('values,value,typed,indices', [
    (['A', 'B', 'A'], 'A', False, {1}),
    (['A', 'B', 'A'], 'B', False, {0, 2}),
    (['A', 'B', 'A'], 'A', True, {1}),
    (['A', 'B', 'A'], 'B', True, {0, 2}),
    (['A', 'B', 'A'], 'C', True, {0, 1, 2}),
    (['', 'B', ''], '', False, {1}),
    (['A', 'A', 'A'], 'A', False, set()),
    (['A', 'A', 'A'], 'B', True, {0, 1, 2}),
])
def test_per_file_scalar_markers(row_context, qtbot, values, value, typed, indices):
    win, disk = row_context
    paths = list(disk)[:3]
    for path, artist in zip(paths, values):
        disk[path].artist = artist
    select(win, paths)  # Direct initial multi-selection, without a single-file baseline.
    assert win.current_file is None
    if typed:
        win.artist_edit.selectAll()
        qtbot.keyClicks(win.artist_edit, value)
    else:
        choose(win.artist_edit, value)
    assert dirty_paths(win) == {paths[i] for i in indices}
    assert win._has_unsaved_changes() == bool(indices)
    assert win.multi_edit_fields == ({'artist'} if indices else set())


def test_union_restoration_and_artwork(row_context, qtbot):
    win, disk = row_context
    a, b, c, _ = disk
    disk[a].album, disk[b].album, disk[c].album = 'X', 'Y', 'X'
    disk[c].artwork = b'cover'
    select(win, [a, b, c])
    choose(win.artist_edit, 'A')
    choose(win.album_edit, 'Y')
    assert dirty_paths(win) == {a, b, c}
    choose(win.album_edit, 'X')
    assert dirty_paths(win) == {b}
    win._remove_artwork()
    assert dirty_paths(win) == {b, c}
    win._undo_changes()
    assert not dirty_paths(win)
    win.pending_artwork = b'replacement'
    win.multi_edit_artwork = True
    win._update_dirty_indicators()
    assert dirty_paths(win) == {a, b, c}


def test_cancel_discard_and_new_selection_markers(row_context, monkeypatch):
    win, disk = row_context
    a, b, c, d = disk
    select(win, [a, b, c])
    choose(win.artist_edit, 'A')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Cancel)
    assert not win._files_selected([str(c), str(d)])
    assert dirty_paths(win) == {b}
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Discard)
    select(win, [c, d])
    assert not dirty_paths(win)
    choose(win.artist_edit, 'A')
    assert dirty_paths(win) == {d}


def test_unresolved_and_immediate_uncertainty_markers(row_context):
    win, disk = row_context
    a, b, c, d = disk
    select(win, [a, b, c])
    choose(win.artist_edit, 'A')
    win._unverified_fields[d] = {'title'}
    win._update_dirty_indicators()
    assert dirty_paths(win) == {b, d}
    win._unresolved_multi_fields.add('artist')
    win._update_dirty_indicators()
    assert dirty_paths(win) == {a, b, c, d}


@pytest.mark.parametrize('order', [Qt.AscendingOrder, Qt.DescendingOrder])
def test_marker_updates_visit_each_file_despite_filename_sorting(row_context, order):
    win, disk = row_context
    paths = list(disk)[:3]
    select(win, paths)
    win.file_list.sortItems(0, order)
    for value, expected in [('A', {paths[1]}), ('B', {paths[0], paths[2]}),
                            ('', set(paths)), ('A', {paths[1]})]:
        choose(win.artist_edit, value)
        assert dirty_paths(win) == expected
    win._undo_changes()
    assert not dirty_paths(win)
