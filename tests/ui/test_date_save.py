import shutil
import pytest
from PySide6.QtWidgets import QMessageBox
from audio_metadata_editor.metadata import Metadata, read_metadata
from audio_metadata_editor.metadata.writer import write_metadata
from audio_metadata_editor.ui.main_window import MainWindow

@pytest.fixture(params=['mp3', 'v23', 'm4b'])
def setup(request, tmp_path, audio_fixture_dir, qtbot, monkeypatch):
    suffix = 'mp3' if request.param == 'v23' else request.param
    paths = [tmp_path / f'{i}.{suffix}' for i in range(2)]
    for p in paths:
        shutil.copy2(audio_fixture_dir / f'silence.{suffix}', p)
        write_metadata(p, Metadata(title='Keep', date='2020'))
        if request.param == 'v23':
            from mutagen.id3 import ID3
            tags = ID3(p); tags.update_to_v23(); tags.save(p, v2_version=3)
    w = MainWindow()
    qtbot.addWidget(w, before_close_func=lambda w: w._clear_editing_context())
    w._directory_selected(tmp_path)
    w.file_list.select_files([str(paths[0])])
    w.show()
    messages = []
    for kind in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, kind, lambda *a, kind=kind: messages.append((kind, a[1], a[2])))
    return w, paths, messages

@pytest.mark.parametrize('mode', ['single', 'multi', 'generated'])
def test_invalid_date_never_writes(setup, qtbot, mode):
    w, paths, messages = setup
    if mode != 'single':
        w.file_list.select_files([str(p) for p in paths])
    if mode == 'generated':
        w._apply_generated('date', {p: 'not a date' for p in paths})
    else:
        w.date_edit.selectAll()
        qtbot.keyClicks(w.date_edit, 'not a date')
    before = [p.read_bytes() for p in paths]
    w._save_changes()
    assert [p.read_bytes() for p in paths] == before
    assert w._has_unsaved_changes()
    assert w.date_edit.text() == 'not a date'
    assert not any(title == 'Saved' for _, title, _ in messages)
    assert any('Date' in text for _, _, text in messages)

@pytest.mark.parametrize('mode', ['single', 'multi', 'generated', 'final_read'])
def test_mismatch_retains_intent_and_retry(setup, qtbot, monkeypatch, mode):
    w, paths, messages = setup
    if mode != 'single': w.file_list.select_files([str(p) for p in paths])
    if mode in ('generated', 'final_read'):
        w._apply_generated('date', {p: '2024-02-29T00:00' for p in paths})
    else:
        w.date_edit.selectAll(); qtbot.keyClicks(w.date_edit, '2024-02-29T00:00')
    reader = w._read_after_write
    calls = 0
    def mismatch(path):
        nonlocal calls
        calls += 1
        result = reader(path)
        if mode != 'final_read' or calls == 3: result.date = ''
        return result
    with monkeypatch.context() as patch:
        patch.setattr(w, '_read_after_write', mismatch)
        w._save_changes()
    assert w._has_unsaved_changes()
    assert w.date_edit.text() == '2024-02-29T00:00'
    assert not any(title == 'Saved' for _, title, _ in messages)
    assert any('did not match' in text for _, _, text in messages)
    assert not w._unverified_fields
    w._save_changes()
    assert not w._has_unsaved_changes()
    from audio_metadata_editor.metadata.date import normalize_date
    assert normalize_date(read_metadata(paths[0]).date) == '2024-02-29 00:00'

@pytest.mark.parametrize('action', ['selection', 'refresh', 'close'])
@pytest.mark.parametrize('reply', ['Save', 'Cancel', 'Discard'])
def test_invalid_transition_guards(setup, qtbot, monkeypatch, action, reply):
    from PySide6.QtGui import QCloseEvent
    w, paths, messages = setup
    w.date_edit.selectAll(); qtbot.keyClicks(w.date_edit, 'not a date')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: getattr(QMessageBox, reply))
    if action == 'selection': w.file_list.select_files([str(paths[1])])
    elif action == 'refresh': w._refresh_tree()
    else:
        event = QCloseEvent(); w.closeEvent(event)
        assert event.isAccepted() == (reply == 'Discard')
    assert read_metadata(paths[0]).date == '2020'
    if reply != 'Discard':
        assert w._has_unsaved_changes() and w.date_edit.text() == 'not a date'
    elif action != 'close': assert not w._has_unsaved_changes()


def test_paste_invalid_retained_then_corrected(setup, monkeypatch, qtbot):
    from PySide6.QtWidgets import QDialog
    from audio_metadata_editor.ui.dialogs.paste_fields_dialog import PasteFieldsDialog
    w, paths, messages = setup
    w.metadata_clipboard = Metadata(date='not a date')
    monkeypatch.setattr(PasteFieldsDialog, 'exec', lambda self: QDialog.Accepted)
    monkeypatch.setattr(PasteFieldsDialog, 'selected_fields', property(lambda self: {'date'}))
    w._paste_metadata(); w._save_changes()
    assert w.date_edit.text() == 'not a date' and w._has_unsaved_changes()
    assert w.date_edit.selectedText() == 'not a date'
    assert read_metadata(paths[0]).date == '2020'
    w.date_edit.selectAll(); qtbot.keyClicks(w.date_edit, ' 2024 ')
    w._save_changes()
    assert read_metadata(paths[0]).date == '2024'
    assert not w._has_unsaved_changes()


def test_batch_preflight_no_partial_write(setup):
    w, paths, messages = setup
    w.file_list.select_files([str(p) for p in paths])
    w._apply_generated('date', {paths[0]: '2024', paths[1]: 'not a date'})
    before = [p.read_bytes() for p in paths]
    w._save_changes()
    assert [p.read_bytes() for p in paths] == before
    assert w._per_file_edits[paths[1]]['date'] == 'not a date'
    assert not w._unresolved_per_file_fields


def test_v23_precision_rejected_with_clear_explanation(setup, qtbot):
    from mutagen.id3 import ID3
    w, paths, messages = setup
    if paths[0].suffix != '.mp3':
        w.date_edit.selectAll(); qtbot.keyClicks(w.date_edit, '2024-02')
        w._save_changes()
        assert read_metadata(paths[0]).date == '2024-02'
        return
    tags = ID3(paths[0]); tags.update_to_v23(); tags.save(paths[0], v2_version=3)
    w.date_edit.selectAll(); qtbot.keyClicks(w.date_edit, '2024-02')
    before = paths[0].read_bytes()
    w._save_changes()
    assert paths[0].read_bytes() == before
    assert w._has_unsaved_changes()
    assert any('ID3v2.3' in text for _, _, text in messages)
