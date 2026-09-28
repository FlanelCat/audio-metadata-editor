from copy import deepcopy
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from audio_metadata_editor.metadata import Metadata, MetadataReadError, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.ui.dialogs.generate_text_dialog import GenerateTextDialog, TARGETS
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    paths = [tmp_path / f'{name}.{request.param}' for name in 'abc']
    for i, path in enumerate(paths, 1):
        shutil.copy2(audio_fixture_dir / f'silence.{request.param}', path)
        write_metadata(path, Metadata(title=f'Chapter {i:02}' if i != 2 else 'Old',
                                     artist='Original', album='Album', track_number=i, track_total=10))
    win = module.MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.root_path = tmp_path
    win._populate_root()
    win.file_list.sortItems(0, Qt.AscendingOrder)
    win.file_list.select_files([str(p) for p in paths])
    win.show()
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: pytest.fail(str(a)))
    return win, paths


def generated(win, paths, field='title', prefix='Chapter '):
    values = {p: f'{prefix}{i:02}' for i, p in enumerate(paths, 1)}
    win._apply_generated(field, values)
    return values


def rows(win):
    return {Path(win.file_list.item(r, 0).data(256)): r for r in range(win.file_list.rowCount())}


def dirty(win):
    return {p for p, r in rows(win).items() if win.file_list.item(r, 0).text().startswith('*')}


def test_dialog_preview_and_errors(qtbot):
    dialog = GenerateTextDialog([(Path('a.mp3'), {'track': 1}), (Path('b.mp3'), {'track': None})])
    qtbot.addWidget(dialog)
    assert [dialog.field.itemData(i) for i in range(dialog.field.count())] == list(TARGETS)
    assert dialog.preview.item(0, 1).text() == 'Chapter 01'
    assert 'ERROR' in dialog.preview.item(1, 1).text()
    assert not dialog.apply_button.isEnabled()
    dialog.accept()
    assert dialog.result() != QDialog.Accepted
    dialog.template.setText('Literal {{value}}')
    assert dialog.apply_button.isEnabled()
    dialog.field.setCurrentIndex(1)
    dialog.accept()
    assert dialog.generated == ('artist', {Path('a.mp3'): 'Literal {value}', Path('b.mp3'): 'Literal {value}'})


def test_preview_cancel_and_visual_order(setup, monkeypatch):
    win, paths = setup
    win.file_list.sortItems(0, Qt.DescendingOrder)
    before = {p: p.read_bytes() for p in paths}
    state = deepcopy((win._multi_field_baselines, win.multi_edit_fields, win._generated_edits))
    def cancel(dialog):
        assert [p for p, _ in dialog.targets] == list(reversed(paths))
        dialog.template.setText('{index:02} {filename}')
        assert dialog.preview.item(0, 1).text() == f'01 {paths[2].name}'
        assert not win._has_unsaved_changes()
        return QDialog.Rejected
    monkeypatch.setattr(GenerateTextDialog, 'exec', cancel)
    win._generate_text()
    assert state == (win._multi_field_baselines, win.multi_edit_fields, win._generated_edits)
    assert {p: p.read_bytes() for p in paths} == before
    def apply(dialog):
        dialog.template.setText('Part {index:02}')
        dialog.accept()
        return dialog.result()
    monkeypatch.setattr(GenerateTextDialog, 'exec', apply)
    win._generate_text()
    assert win._generated_edits[paths[2]]['title'] == 'Part 01'
    assert {p: p.read_bytes() for p in paths} == before


def test_apply_pending_presentation_and_save(setup):
    win, paths = setup
    before = {p: p.read_bytes() for p in paths}
    expected = generated(win, paths)
    assert {p: p.read_bytes() for p in paths} == before
    assert dirty(win) == {paths[1]}
    assert win.multi_edit_fields == set() and win._has_unsaved_changes()
    assert win.title_edit.placeholderText() and win.title_edit.text() == ''
    for p, row in rows(win).items():
        assert win.file_list.item(row, 2).text() == expected[p]
    win._save_changes()
    assert not win._has_unsaved_changes() and not dirty(win)
    for p in paths:
        m = read_metadata(p)
        assert m.title == expected[p] and m.artist == 'Original' and m.track_total == 10
    assert not win._generated_edits and not win._unresolved_generated_fields


def test_precedence_multiple_fields_and_regeneration(setup, qtbot):
    win, paths = setup
    qtbot.keyClicks(win.artist_edit, 'Common')
    generated(win, paths)
    generated(win, paths, 'series', 'Series ')
    generated(win, paths, 'title', 'New ')
    assert win.multi_edit_fields == {'artist'}
    assert all(set(win._generated_edits[p]) == {'title', 'series'} for p in paths)
    qtbot.keyClicks(win.title_edit, 'Introduction')
    assert all(set(win._generated_edits[p]) == {'series'} for p in paths)
    assert win.multi_edit_fields == {'artist', 'title'}
    generated(win, paths, 'artist', 'Narrator ')
    assert win.multi_edit_fields == {'title'}
    win._save_changes()
    for i, p in enumerate(paths, 1):
        m = read_metadata(p)
        assert m.title == 'Introduction' and m.series == f'Series {i:02}' and m.artist == f'Narrator {i:02}'


def test_single_pending_and_discard(setup):
    win, paths = setup
    win.file_list.select_files([str(paths[1])])
    expected = generated(win, [paths[1]], prefix='Single ')
    assert win.title_edit.text() == expected[paths[1]]
    assert read_metadata(paths[1]).title == 'Old'
    win._undo_changes()
    assert win.title_edit.text() == 'Old' and not win._generated_edits
    generated(win, [paths[1]], prefix='Saved ')
    win._save_changes()
    assert read_metadata(paths[1]).title == 'Saved 01'
    assert not win.title_edit.styleSheet()
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('failure', ['before', 'after', 'readback', 'final'])
def test_partial_uncertainty_retry_and_discard(setup, monkeypatch, failure):
    win, paths = setup
    expected = generated(win, paths, prefix='New ')
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    reader = win._read_after_write
    calls = []
    reads = []
    def write(path, *a, **k):
        calls.append(path)
        if path == paths[1] and failure == 'before':
            raise OSError('before writer')
        writer(path, *a, **k)
        if path == paths[1] and failure == 'after':
            raise OSError('after writer')
    def read(path):
        reads.append(path)
        if (failure == 'readback' and path == paths[1]) or (failure == 'final' and len(reads) == 4):
            raise MetadataReadError(path, 'readback failed')
        return reader(path)
    with monkeypatch.context() as patch:
        patch.setattr(module, writer_name, write)
        patch.setattr(win, '_read_after_write', read)
        patch.setattr(QMessageBox, 'critical', lambda *a: None)
        win._save_changes()
    assert win._has_unsaved_changes() and win._generated_edits
    assert win._unresolved_generated_fields[paths[0]] == {'title'}
    assert not win._unresolved_multi_fields
    assert read_metadata(paths[0]).title == expected[paths[0]]
    for p, row in rows(win).items():
        assert win.file_list.item(row, 2).text() == expected[p]
    # Changed current intent also reaches targets already verified on the first attempt.
    generated(win, paths, prefix='Retry ')
    win._save_changes()
    assert [read_metadata(p).title for p in paths] == [f'Retry {i:02}' for i in range(1, 4)]
    assert not win._has_unsaved_changes()
    generated(win, paths, prefix='Abandon ')
    win._undo_changes()
    assert not win._generated_edits
    for p, row in rows(win).items():
        assert win.file_list.item(row, 2).text() == read_metadata(p).title


@pytest.mark.parametrize('action', ['selection', 'refresh', 'directory', 'close'])
def test_cancel_guards(setup, monkeypatch, action, tmp_path):
    from PySide6.QtGui import QCloseEvent
    win, paths = setup
    generated(win, paths)
    before = deepcopy(win._generated_edits)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Cancel)
    if action == 'selection':
        win.file_list.select_files([str(paths[0])])
    elif action == 'refresh':
        win._refresh_tree()
    elif action == 'directory':
        other = tmp_path / 'Other'
        other.mkdir()
        win._directory_selected(other)
    else:
        event = QCloseEvent()
        win.closeEvent(event)
        assert not event.isAccepted()
    assert win._generated_edits == before
    assert win.selected_files == [str(p) for p in paths]


def test_generated_sorting_identity(setup):
    win, paths = setup
    win.file_list.sortItems(2, Qt.DescendingOrder)
    values = {paths[0]: 'Z', paths[1]: 'A', paths[2]: 'M'}
    win._apply_generated('title', values)
    for p, row in rows(win).items():
        assert win.file_list.item(row, 2).text() == values[p]
    win.file_list.sortItems(0, Qt.AscendingOrder)
    assert list(rows(win)) == paths
    win._save_changes()
    assert {p: read_metadata(p).title for p in paths} == values


@pytest.mark.parametrize('single', [False, True])
def test_uncertain_generated_to_common_and_back(setup, monkeypatch, qtbot, single):
    win, paths = setup
    if single:
        paths = paths[1:2]
        win.file_list.select_files([str(paths[0])])
    expected = generated(win, paths, prefix='Attempt ')
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    def fail(path, *a, **k):
        writer(path, *a, **k)
        raise OSError('modified then raised')
    with monkeypatch.context() as patch:
        patch.setattr(module, writer_name, fail)
        patch.setattr(QMessageBox, 'critical', lambda *a: None)
        win._save_changes()
    assert win._unresolved_generated_fields and win._has_unsaved_changes()
    win.title_edit.selectAll()
    qtbot.keyClicks(win.title_edit, 'Common')
    assert not any('title' in fields for fields in win._generated_edits.values())
    assert 'title' in (win._unresolved_single_fields if single else win._unresolved_multi_fields)
    generated(win, paths, prefix='Latest ')
    assert not win._unresolved_single_fields and not win._unresolved_multi_fields
    assert win._unresolved_generated_fields
    win._save_changes()
    assert [read_metadata(p).title for p in paths] == [f'Latest {i:02}' for i in range(1, len(paths) + 1)]
    assert not win._has_unsaved_changes()


def test_discard_uncertainty_and_failed_reload(setup, monkeypatch):
    win, paths = setup
    generated(win, paths, prefix='Written ')
    reader = win._read_after_write
    def fail(path):
        raise MetadataReadError(path, 'verification failed')
    with monkeypatch.context() as patch:
        patch.setattr(win, '_read_after_write', fail)
        patch.setattr(QMessageBox, 'critical', lambda *a: None)
        win._save_changes()
        before = deepcopy(win._generated_edits)
        patch.setattr(module, 'read_metadata', fail)
        win._undo_changes()
        assert win._generated_edits == before and win._unresolved_generated_fields
    win._undo_changes()
    assert not win._has_unsaved_changes() and not win._generated_edits
    assert read_metadata(paths[0]).title == 'Written 01'
    assert read_metadata(paths[1]).title == 'Old'  # No rollback, no later write.


def test_artwork_preservation_and_accepted_template_source(setup, monkeypatch, qtbot):
    win, paths = setup
    writer = module.write_mp3_metadata if paths[0].suffix == '.mp3' else module.write_m4b_metadata
    for path in paths:
        writer(path, read_metadata(path), fields=set(), artwork=b'cover bytes', artwork_mime='image/jpeg')
    win.artist_edit.selectAll()
    qtbot.keyClicks(win.artist_edit, 'Pending artist')
    def apply(dialog):
        dialog.template.setText('{artist}: {filename}')
        assert all(dialog.preview.item(row, 1).text().startswith('Original: ') for row in range(3))
        dialog.accept()
        return dialog.result()
    monkeypatch.setattr(GenerateTextDialog, 'exec', apply)
    win._generate_text()
    win._save_changes()
    for path in paths:
        metadata = read_metadata(path)
        assert metadata.title == 'Original: ' + path.name
        assert metadata.artist == 'Pending artist' and metadata.artwork == b'cover bytes'
        assert metadata.album == 'Album' and metadata.track_total == 10


def test_immediate_verification_preserves_generated_intent(setup):
    win, paths = setup
    expected = generated(win, paths, prefix='Pending ')
    write_metadata(paths[0], Metadata(title='Immediate'), fields={'title'})
    win._unverified_fields[paths[0]] = {'title'}
    win._verify_field_saves()
    assert win._multi_field_baselines[paths[0]]['title'] == 'Immediate'
    assert win._generated_edits[paths[0]]['title'] == expected[paths[0]]
    assert win.file_list.item(rows(win)[paths[0]], 2).text() == expected[paths[0]]
    win._save_metadata_field(paths[0], 'title', 'Later explicit')
    assert 'title' not in win._generated_edits[paths[0]]
    assert win.file_list.item(rows(win)[paths[0]], 2).text() == 'Later explicit'
    assert win._generated_edits[paths[1]]['title'] == expected[paths[1]]


def test_apply_errors_atomic_and_no_selection(qtbot):
    dialog = GenerateTextDialog([])
    qtbot.addWidget(dialog)
    assert not dialog.apply_button.isEnabled()
    dialog.accept()
    assert dialog.generated is None


@pytest.mark.parametrize('failure', ['before', 'after', 'readback'])
def test_single_generated_failure_retains_retry_value(setup, monkeypatch, failure):
    win, paths = setup
    path = paths[1]
    win.file_list.select_files([str(path)])
    generated(win, [path], prefix='Attempt ')
    writer_name = 'write_mp3_metadata' if path.suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    def write(*a, **k):
        if failure == 'before':
            raise OSError('before')
        writer(*a, **k)
        if failure == 'after':
            raise OSError('after')
    def fail_read(path):
        raise MetadataReadError(path, 'readback')
    with monkeypatch.context() as patch:
        patch.setattr(module, writer_name, write)
        patch.setattr(QMessageBox, 'critical', lambda *a: None)
        if failure == 'readback':
            patch.setattr(win, '_read_after_write', fail_read)
        win._save_changes()
    assert win._unresolved_generated_fields == {path: {'title'}}
    assert not win._unresolved_single_fields
    # Restoring the cached original must not erase uncertainty.
    win._apply_generated('title', {path: 'Old'})
    assert win._has_unsaved_changes() and dirty(win) == {path}
    win._save_changes()
    assert read_metadata(path).title == 'Old'
    assert not win._has_unsaved_changes()


@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard])
def test_generated_refresh_save_discard(setup, monkeypatch, reply):
    win, paths = setup
    before = {p: read_metadata(p).title for p in paths}
    expected = generated(win, paths, prefix='Refresh ')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: reply)
    win._refresh_tree()
    assert win.current_directory == paths[0].parent
    assert not win._generated_edits and not win._has_unsaved_changes()
    assert {p: read_metadata(p).title for p in paths} == (expected if reply == QMessageBox.Save else before)


def test_generated_save_uses_accepted_path_order(setup, monkeypatch):
    win, paths = setup
    win.file_list.select_files([str(paths[2]), str(paths[0]), str(paths[1])])
    accepted = [Path(p) for p in win.selected_files]
    generated(win, paths, prefix='Order ')
    win.file_list.sortItems(2, Qt.DescendingOrder)
    writer_name = 'write_mp3_metadata' if paths[0].suffix == '.mp3' else 'write_m4b_metadata'
    writer = getattr(module, writer_name)
    written = []
    def record(path, *a, **k):
        written.append(path)
        writer(path, *a, **k)
    monkeypatch.setattr(module, writer_name, record)
    win._save_changes()
    assert written == accepted


def test_generation_result_validation_is_atomic(setup):
    win, paths = setup
    before = deepcopy(win._generated_edits)
    with pytest.raises(ValueError):
        win._apply_generated('title', {paths[0]: 'Partial'})
    with pytest.raises(ValueError):
        win._apply_generated('track_number', {p: '1' for p in paths})
    assert win._generated_edits == before and not win._has_unsaved_changes()


def test_last_generated_difference_saved_immediately_clears_highlight(setup):
    win, paths = setup
    generated(win, paths)
    assert win.title_edit.styleSheet()
    win._save_metadata_field(paths[1], 'title', 'Chapter 02')
    assert not dirty(win) and not win._has_unsaved_changes()
    assert not win.title_edit.styleSheet()


def test_toolbar_dialog_apply(setup, qtbot):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QToolBar
    win, paths = setup
    before = {p: p.read_bytes() for p in paths}
    def respond():
        dialog = win.findChild(GenerateTextDialog)
        assert dialog is not None
        dialog.template.setText('Toolbar {index:02}')
        qtbot.mouseClick(dialog.apply_button, Qt.LeftButton)
    QTimer.singleShot(0, respond)
    next(a for a in win.findChild(QToolBar).actions() if a.text() == 'Generate Text…').trigger()
    assert win._generated_edits[paths[0]]['title'] == 'Toolbar 01'
    assert {p: p.read_bytes() for p in paths} == before


def test_panel_only_generated_values_remain_inspectable(setup):
    win, paths = setup
    generated(win, paths, 'genre', '<Genre> ')
    for p, row in rows(win).items():
        tooltip = win.file_list.item(row, 0).toolTip()
        assert 'Pending generated text' in tooltip and 'Genre: &lt;Genre&gt;' in tooltip
    win._save_changes()
    assert all(not win.file_list.item(row, 0).toolTip() for row in rows(win).values())
    assert [read_metadata(p).genre for p in paths] == [f'<Genre> {i:02}' for i in range(1, 4)]
