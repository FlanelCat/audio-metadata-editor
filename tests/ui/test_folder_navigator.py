"""Filesystem navigation, guarded acceptance and isolated root persistence."""
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from audio_metadata_editor import settings
from audio_metadata_editor.metadata import read_metadata
from audio_metadata_editor.ui.main_window import MainWindow
from audio_metadata_editor.ui.folder_navigator import FolderNavigator


def child(item, name):
    return next(item.child(i) for i in range(item.childCount()) if item.child(i).text(0) == name)


def click(win, item, qtbot):
    qtbot.mouseClick(win.directory_tree.viewport(), Qt.LeftButton,
                     pos=win.directory_tree.visualItemRect(item).center())


def choose_root(win, path, monkeypatch):
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a: str(path))
    win.folder_navigator.choose_button.click()


def table_paths(win):
    return {Path(win.file_list.item(r, 0).data(256)) for r in range(win.file_list.rowCount())}


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: pytest.fail(str(a)))
    win = MainWindow()
    qtbot.addWidget(win, before_close_func=lambda w: w._clear_editing_context())
    win.show()
    return win


@pytest.fixture
def library(tmp_path, audio_fixture_dir):
    root = tmp_path / 'Author'
    for folder in ('Book/Edition A', 'Book/Edition B', '.hidden', 'Empty'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    for folder in (root, root / 'Book/Edition A', root / 'Book/Edition B'):
        for suffix in ('mp3', 'm4b'):
            shutil.copy2(audio_fixture_dir / f'silence.{suffix}', folder / f'part.{suffix}')
    (root / 'notes.txt').write_text('notes')
    (root / 'cycle').symlink_to(root, target_is_directory=True)
    return root


def test_no_root_and_lazy_presentation(window, library, monkeypatch):
    win = window
    nav = win.folder_navigator
    assert nav.heading.text() == 'No audiobook root selected'
    assert nav.path_label.text() == '' and nav.tree.topLevelItemCount() == 0
    assert nav.choose_button.text() == 'Choose Root…'
    seen = []
    original = Path.iterdir
    def scan(path):
        seen.append(path)
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', scan)
    choose_root(win, library, monkeypatch)
    assert set(seen) == {library}  # Root only, no child probing or metadata tree reads.
    assert nav.heading.text() == 'Author' and nav.path_label.text() == str(library)
    books = nav.tree.topLevelItem(0)
    assert books.text(0) == 'Books' and books.data(0, 256) == str(library)
    assert [books.child(i).text(0) for i in range(books.childCount())] == ['Book', 'Empty']
    book = child(books, 'Book')
    seen.clear()
    book.setExpanded(True)
    assert seen == [library / 'Book']
    assert [book.child(i).text(0) for i in range(book.childCount())] == ['Edition A', 'Edition B']
    seen.clear()
    child(book, 'Edition A').setExpanded(True)
    assert seen == [library / 'Book/Edition A']
    assert child(book, 'Edition A').childCount() == 0


def test_direct_navigation_and_keyboard(window, library, monkeypatch, qtbot):
    choose_root(window, library, monkeypatch)
    books = window.directory_tree.topLevelItem(0)
    book = child(books, 'Book')
    click(window, book, qtbot)
    assert window.current_directory == library / 'Book'
    assert not table_paths(window)  # No aggregation from editions.
    book.setExpanded(True)
    edition = child(book, 'Edition A')
    click(window, edition, qtbot)
    assert table_paths(window) == {library / 'Book/Edition A' / f'part.{s}' for s in ('mp3', 'm4b')}
    assert window.current_directory == library / 'Book/Edition A'
    requests = []
    window.directory_tree.directory_requested.connect(requests.append)
    window.directory_tree.restore_current_directory()
    assert not requests
    qtbot.keyClick(window.directory_tree, Qt.Key_Down)
    assert window.current_directory == library / 'Book/Edition B'
    click(window, books, qtbot)
    assert table_paths(window) == {library / f'part.{s}' for s in ('mp3', 'm4b')}


@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_tree_guard(window, library, monkeypatch, qtbot, reply):
    choose_root(window, library, monkeypatch)
    books = window.directory_tree.topLevelItem(0)
    window.file_list.select_files([str(library / 'part.mp3')])
    qtbot.keyClicks(window.artist_edit, 'Pending')
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: prompts.append(a) or reply)
    click(window, child(books, 'Empty'), qtbot)
    assert len(prompts) == 1
    if reply == QMessageBox.Cancel:
        assert window.directory_tree.currentItem() is books
        assert window.current_directory == library
        assert window.artist_edit.text() == 'Pending'
    else:
        assert window.current_directory == library / 'Empty'
        assert not table_paths(window) and not window._has_unsaved_changes()
    assert read_metadata(library / 'part.mp3').artist == ('Pending' if reply == QMessageBox.Save else '')


@pytest.mark.parametrize('kind', ['multi', 'invalid', 'single_uncertain', 'multi_uncertain', 'unverified'])
def test_guard_preserves_protected_state(window, library, monkeypatch, qtbot, kind):
    choose_root(window, library, monkeypatch)
    paths = sorted(table_paths(window))
    window.file_list.select_files([str(p) for p in (paths if kind in ('multi', 'multi_uncertain') else paths[:1])])
    if kind == 'multi':
        qtbot.keyClicks(window.artist_edit, 'Pending')
    elif kind == 'invalid':
        qtbot.keyClicks(window.track_edit, 'invalid')
    elif kind == 'single_uncertain':
        window._unresolved_single_fields.add('artist')
    elif kind == 'multi_uncertain':
        window._unresolved_multi_fields.add('artist')
    else:
        window._unverified_fields[paths[0]] = {'artist'}
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Save if kind == 'invalid' else QMessageBox.Cancel)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: warnings.append(a))
    books = window.directory_tree.topLevelItem(0)
    click(window, child(books, 'Empty'), qtbot)
    assert window.directory_tree.currentItem() is books
    assert window.current_directory == library and window._has_unsaved_changes()
    assert table_paths(window) == set(paths)
    if kind == 'invalid':
        assert warnings and window.track_edit.text() == 'invalid'


@pytest.mark.parametrize('reply', [QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel])
def test_root_switch_guard(window, library, tmp_path, monkeypatch, qtbot, reply):
    choose_root(window, library, monkeypatch)
    old = window.directory_tree.topLevelItem(0)
    window.file_list.select_files([str(library / 'part.mp3')])
    qtbot.keyClicks(window.artist_edit, 'Pending')
    new = tmp_path / 'New root'
    (new / 'Only new').mkdir(parents=True)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: reply)
    choose_root(window, new, monkeypatch)
    expected = library if reply == QMessageBox.Cancel else new
    assert window.root_path == expected and window.current_directory == expected
    assert window.settings.value(settings.ROOT_KEY) == str(expected)
    if reply == QMessageBox.Cancel:
        assert window.directory_tree.topLevelItem(0) is old
        assert window.artist_edit.text() == 'Pending'
    else:
        books = window.directory_tree.topLevelItem(0)
        assert books.childCount() == 1 and books.child(0).text(0) == 'Only new'
        assert window.folder_navigator.heading.text() == new.name
    assert read_metadata(library / 'part.mp3').artist == ('Pending' if reply == QMessageBox.Save else '')


def test_restart_open_folder_and_refresh(window, library, tmp_path, monkeypatch, qtbot):
    choose_root(window, library, monkeypatch)
    other = tmp_path / 'Outside'
    other.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a: str(other))
    window._open_folder()
    assert window.current_directory == other and window.root_path == library
    assert window.directory_tree.currentItem() is None
    assert window.settings.value(settings.ROOT_KEY) == str(library)
    window._refresh_tree()
    assert window.current_directory == library
    restored = MainWindow()
    qtbot.addWidget(restored)
    assert restored.root_path == library and restored.current_directory == library
    assert len(table_paths(restored)) == 2
    assert restored.folder_navigator.heading.text() == 'Author'


@pytest.mark.parametrize('missing', [True, False])
def test_unavailable_remembered_root_is_retained(tmp_path, monkeypatch, qtbot, missing):
    root = tmp_path / 'Unavailable'
    if not missing:
        root.mkdir()
        original = Path.iterdir
        def scan(path):
            if path == root:
                raise PermissionError('offline')
            return original(path)
        monkeypatch.setattr(Path, 'iterdir', scan)
    store = settings.create_settings()
    store.setValue(settings.ROOT_KEY, str(root))
    store.sync()
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.root_path is None and win.directory_tree.topLevelItemCount() == 0
    assert win.folder_navigator.heading.text() == 'No audiobook root selected'
    assert win.settings.value(settings.ROOT_KEY) == str(root)
    assert str(root) in win.statusBar().currentMessage()


def test_expansion_failure_is_atomic_and_retryable(window, library, monkeypatch):
    choose_root(window, library, monkeypatch)
    book = child(window.directory_tree.topLevelItem(0), 'Book')
    original = Path.iterdir
    def scan(path):
        if path == library / 'Book':
            def fail_after_one():
                yield library / 'Book/Edition A'
                raise PermissionError('offline')
            return fail_after_one()
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', scan)
    book.setExpanded(True)
    assert book.childCount() == 1 and book.child(0).data(0, 256) is None
    assert 'offline' in window.statusBar().currentMessage()
    monkeypatch.setattr(Path, 'iterdir', original)
    book.setExpanded(False)
    book.setExpanded(True)
    assert book.childCount() == 2


def test_failed_navigation_and_root_leave_context(window, library, monkeypatch, qtbot):
    choose_root(window, library, monkeypatch)
    window.file_list.select_files([str(library / 'part.mp3')])
    qtbot.keyClicks(window.artist_edit, 'Pending')
    books = window.directory_tree.topLevelItem(0)
    original = Path.iterdir
    def scan(path):
        if path == library / 'Empty':
            raise PermissionError('unreadable')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', scan)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: pytest.fail('Must fail before discarding edits'))
    click(window, child(books, 'Empty'), qtbot)
    assert window.directory_tree.currentItem() is books
    choose_root(window, library / 'Empty', monkeypatch)
    assert window.root_path == library and window.directory_tree.currentItem() is books
    assert window.artist_edit.text() == 'Pending' and len(table_paths(window)) == 2
    assert window.settings.value(settings.ROOT_KEY) == str(library)


def test_empty_root_and_cancel_chooser(window, tmp_path, monkeypatch):
    empty = tmp_path / 'empty'
    empty.mkdir()
    choose_root(window, empty, monkeypatch)
    assert window.directory_tree.topLevelItem(0).childCount() == 0
    assert not table_paths(window)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a: '')
    window._choose_root()
    assert window.root_path == empty


def test_clean_root_switch_and_open_without_root(window, library, tmp_path, monkeypatch):
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a: str(library))
    window._open_folder()
    assert window.current_directory == library and window.root_path is None
    assert window.settings.value(settings.ROOT_KEY) is None
    assert window.directory_tree.topLevelItemCount() == 0
    window._refresh_tree()
    assert len(table_paths(window)) == 2
    choose_root(window, library, monkeypatch)
    second = tmp_path / 'Second'
    second.mkdir()
    choose_root(window, second, monkeypatch)
    assert window.root_path == second and window.current_directory == second
    assert window.directory_tree.topLevelItem(0).childCount() == 0
    assert window.settings.value(settings.ROOT_KEY) == str(second)


def test_loading_failure_after_preflight_retains_rows(window, library, monkeypatch, qtbot):
    choose_root(window, library, monkeypatch)
    window.file_list.select_files([str(library / 'part.mp3')])
    accepted_file = window.current_file
    books = window.directory_tree.topLevelItem(0)
    original = Path.iterdir
    attempts = []
    def scan(path):
        if path == library / 'Empty':
            attempts.append(path)
            if len(attempts) == 2:
                raise FileNotFoundError('disappeared after preflight')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', scan)
    click(window, child(books, 'Empty'), qtbot)
    assert len(attempts) == 2
    assert window.directory_tree.currentItem() is books
    assert window.current_directory == library and window.current_file == accepted_file
    assert len(table_paths(window)) == 2
    assert 'disappeared' in window.statusBar().currentMessage()


def test_tree_has_no_depth_limit_or_metadata_reads(tmp_path, qtbot, monkeypatch):
    import audio_metadata_editor.metadata.reader as reader
    monkeypatch.setattr(reader, 'read_metadata', lambda *a: pytest.fail('Tree read metadata'))
    root = tmp_path / 'unparsed YEAR - NAME'
    deepest = root / 'alpha' / 'one' / 'two' / 'three' / 'four'
    deepest.mkdir(parents=True)
    (root / 'Zebra').mkdir()
    (root / 'Beta').mkdir()
    (root / 'audio.mp3').touch()
    nav = FolderNavigator()
    qtbot.addWidget(nav)
    nav.set_root(root, nav.tree.child_directories(root))
    item = nav.tree.topLevelItem(0)
    assert [item.child(i).text(0) for i in range(item.childCount())] == ['alpha', 'Beta', 'Zebra']
    for name in ('alpha', 'one', 'two', 'three', 'four'):
        item = child(item, name)
        item.setExpanded(True)
    assert item.childCount() == 0


def test_root_failed_save_restores_old_context(window, library, tmp_path, monkeypatch, qtbot):
    import audio_metadata_editor.ui.main_window as module
    choose_root(window, library, monkeypatch)
    window.file_list.select_files([str(library / 'part.mp3')])
    qtbot.keyClicks(window.artist_edit, 'Pending')
    books = window.directory_tree.currentItem()
    other = tmp_path / 'Other'
    other.mkdir()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Save)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: None)
    def fail(*a, **k):
        raise OSError('writer failure')
    monkeypatch.setattr(module, 'write_mp3_metadata', fail)
    choose_root(window, other, monkeypatch)
    assert window.root_path == library and window.current_directory == library
    assert window.directory_tree.currentItem() is books
    assert window.artist_edit.text() == 'Pending'
    assert window._unresolved_single_fields == {'artist'}
    assert window.settings.value(settings.ROOT_KEY) == str(library)
