"""S5 rejects audio symlinks without touching their targets."""
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from audio_metadata_editor.metadata import Metadata, MetadataReadError, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.ui.file_list import FileList
import audio_metadata_editor.ui.main_window as module


@pytest.fixture(params=['mp3', 'm4b'])
def media(request, tmp_path, audio_fixture_dir):
    library = tmp_path / 'library'
    library.mkdir()
    target = tmp_path / f'outside.{request.param}'
    shutil.copy2(audio_fixture_dir / f'silence.{request.param}', target)
    write_metadata(target, Metadata(title='Original', track_number=4))
    paths = [library / f'{i}.{request.param}' for i in range(3)]
    for p in paths:
        shutil.copy2(target, p)
    return library, paths, target


def substitute(path, target):
    path.unlink()
    path.symlink_to(target)


def test_discovery_omits_audio_symlinks(media, qtbot):
    library, paths, target = media
    (library / ('linked' + target.suffix.upper())).symlink_to(target)
    (library / ('broken' + target.suffix)).symlink_to(target.parent / 'missing')
    (library / ('folder' + target.suffix)).symlink_to(library, target_is_directory=True)
    assert FileList.directory_files(library) == paths
    table = FileList()
    qtbot.addWidget(table)
    assert table.load_directory(library) == []
    assert {Path(table.item(row, 0).data(256)) for row in range(table.rowCount())} == set(paths)


@pytest.fixture
def window(media, qtbot, monkeypatch):
    library, paths, target = media
    w = module.MainWindow()
    qtbot.addWidget(w, before_close_func=lambda w: w._clear_editing_context())
    w.file_list.setSortingEnabled(False)
    w._directory_selected(library)
    w.file_list.setCurrentCell(0, 2)
    w.show()
    messages = []
    for kind in ('warning', 'critical', 'information'):
        monkeypatch.setattr(QMessageBox, kind, lambda *args: messages.append(args[1:3]))
    return w, paths, target, messages


@pytest.mark.parametrize('mode', ['single', 'multi', 'generated', 'artwork'])
def test_panel_late_substitution_preserves_intent(window, monkeypatch, mode):
    w, paths, target, messages = window
    if mode in ('multi', 'generated'):
        w.file_list.select_files([str(p) for p in paths])
    if mode == 'generated':
        w._apply_generated('title', {p: 'Pending' for p in paths})
    elif mode == 'artwork':
        w.pending_artwork, w.pending_artwork_mime = b'cover', 'image/png'
        w.artwork_edited = True
    else:
        w.title_edit.setText('Pending')
        w.title_edit.textEdited.emit('Pending')
    substitute(paths[1] if mode in ('multi', 'generated') else paths[0], target)
    before = target.read_bytes()
    spies = []
    for name in ('write_metadata', 'write_mp3_metadata', 'write_m4b_metadata'):
        spy = Mock()
        monkeypatch.setattr(module, name, spy)
        spies.append(spy)
    w._save_changes()
    assert all(spy.call_count == 0 for spy in spies)
    assert target.read_bytes() == before
    assert w._has_unsaved_changes()
    if mode == 'artwork':
        assert w.pending_artwork == b'cover'
    else:
        assert w._get_edited_metadata().title == 'Pending'
    assert any('symlink' in text.lower() for _, text in messages)
    assert not any(title == 'Saved' for title, _ in messages)


@pytest.mark.parametrize('mode', ['enter', 'auto', 'direct'])
def test_immediate_substitution_never_invokes_writer(window, monkeypatch, qtbot, mode):
    w, paths, target, messages = window
    if mode == 'auto':
        w.file_list.select_files([str(p) for p in paths])
    substitute(paths[0], target)
    before = target.read_bytes()
    writer = Mock()
    monkeypatch.setattr(module, 'write_metadata', writer)
    if mode == 'enter':
        table = w.file_list
        table.editItem(table.item(0, 2))
        editor = table.focusWidget()
        editor.setText('Pending')
        qtbot.keyClick(editor, Qt.Key_Return)
        assert not table.cell_save_succeeded
        assert table.currentRow() == 0
    elif mode == 'auto':
        monkeypatch.setattr(module.AutoNumberDialog, 'exec', lambda self: QDialog.Accepted)
        monkeypatch.setattr(module.AutoNumberDialog, 'starting_number', property(lambda self: 8))
        w._auto_number_tracks()
    else:
        with pytest.raises(ValueError, match='symlink'):
            w._save_metadata_field(paths[0], 'title', 'Pending')
    assert writer.call_count == 0
    assert target.read_bytes() == before
    assert not w._unverified_fields and not w._unverified_requests
    if mode != 'direct':
        assert any('symlink' in text.lower() for _, text in messages)


def test_substitution_after_batch_preflight_stops_at_dispatch(window, monkeypatch):
    w, paths, target, messages = window
    w.file_list.select_files([str(p) for p in paths])
    w.title_edit.setText('Pending')
    w.title_edit.textEdited.emit('Pending')
    original_read = module.read_metadata
    def late_read(path):
        metadata = original_read(path)
        if path == paths[1]:
            substitute(path, target)
        return metadata
    monkeypatch.setattr(module, 'read_metadata', late_read)
    calls = []
    def writer(path, metadata, **kwargs):
        calls.append(path)
        write_metadata(path, metadata, fields=kwargs['fields'])
    monkeypatch.setattr(module, 'write_mp3_metadata', writer)
    monkeypatch.setattr(module, 'write_m4b_metadata', writer)
    before = target.read_bytes()
    w._save_changes()
    assert calls == [paths[0]]
    assert target.read_bytes() == before
    assert read_metadata(paths[0]).title == 'Pending'
    assert read_metadata(paths[2]).title == 'Original'
    assert w._has_unsaved_changes() and w.title_edit.text() == 'Pending'
    assert any('symlink' in text.lower() and 'verified: 1' in text for _, text in messages)
    assert not any(title == 'Saved' for title, _ in messages)


def test_direct_read_rejects_symlink(media):
    _, paths, target = media
    substitute(paths[0], target)
    with pytest.raises(MetadataReadError, match='symlink'):
        read_metadata(paths[0])


@pytest.mark.parametrize('entry', ['dispatch', 'format'])
def test_metadata_write_boundary_rejects_symlink(media, monkeypatch, entry):
    _, paths, target = media
    substitute(paths[0], target)
    before = target.read_bytes()
    if entry == 'dispatch':
        import audio_metadata_editor.metadata.writer as writer_module
        spy = Mock()
        monkeypatch.setattr(writer_module, 'write_mp3_metadata', spy)
        monkeypatch.setattr(writer_module, 'write_m4b_metadata', spy)
        writer = writer_module.write_metadata
    elif target.suffix == '.mp3':
        import audio_metadata_editor.metadata.mp3 as writer_module
        spy = Mock()
        monkeypatch.setattr(writer_module, 'load_mp3_tags_for_write', spy)
        writer = writer_module.write_mp3_metadata
    else:
        import audio_metadata_editor.metadata.m4b as writer_module
        spy = Mock()
        monkeypatch.setattr(writer_module, 'MP4', spy)
        writer = writer_module.write_m4b_metadata
    with pytest.raises(ValueError, match='symlink'):
        writer(paths[0], Metadata(title='Pending'), fields={'title'})
    assert spy.call_count == 0
    assert target.read_bytes() == before


@pytest.mark.parametrize('mode', ['single', 'immediate'])
def test_recheck_immediately_before_dispatch(window, monkeypatch, mode):
    w, paths, target, messages = window
    w.title_edit.setText('Pending')
    before = target.read_bytes()
    spies = []
    for name in ('write_metadata', 'write_mp3_metadata', 'write_m4b_metadata'):
        spy = Mock()
        monkeypatch.setattr(module, name, spy)
        spies.append(spy)
    if mode == 'single':
        validate = module.validate_values_for_file
        def replace_after_preflight(path, values):
            validate(path, values)
            substitute(path, target)
        monkeypatch.setattr(module, 'validate_values_for_file', replace_after_preflight)
        w._save_changes()
    else:
        read = module.read_metadata
        def replace_after_read(path):
            result = read(path)
            substitute(path, target)
            return result
        monkeypatch.setattr(module, 'read_metadata', replace_after_read)
        w._save_table_cell(str(paths[0]), 2, 'Pending')
        assert not w.file_list.cell_save_succeeded
    assert all(spy.call_count == 0 for spy in spies)
    assert target.read_bytes() == before
    assert w.title_edit.text() == 'Pending' and w._has_unsaved_changes()
    assert any('symlink' in text.lower() for _, text in messages)


def test_load_rechecks_a_stale_discovery_result(media, qtbot, monkeypatch):
    library, paths, target = media
    table = FileList()
    qtbot.addWidget(table)
    snapshot = table.directory_files(library)
    substitute(paths[0], target)
    monkeypatch.setattr(table, 'directory_files', lambda directory: snapshot)
    errors = table.load_directory(library)
    assert len(errors) == 1 and 'symlink' in str(errors[0])
    assert {Path(table.item(r, 0).data(256)) for r in range(table.rowCount())} == set(paths[1:])
