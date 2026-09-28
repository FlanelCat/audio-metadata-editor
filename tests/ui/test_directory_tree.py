from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from audio_metadata_editor.ui.directory_tree import DirectoryTree


@pytest.fixture
def tree(qtbot):
    tree = DirectoryTree()
    qtbot.addWidget(tree)
    return tree


def test_root_and_lazy_expansion(tree, tmp_path):
    for name in ('zeta', 'Alpha', '.hidden', 'Alpha/nested'):
        (tmp_path / name).mkdir()
    (tmp_path / 'file.txt').write_text('not a directory')
    requests = []
    tree.directory_requested.connect(requests.append)
    tree.set_root(tmp_path)
    root = tree.topLevelItem(0)
    assert tree.headerItem().text(0) == 'Folders'
    assert root.text(0) == "Books"
    assert root.data(0, 256) == str(tmp_path)
    assert root.isExpanded()
    assert tree.currentItem() is root
    assert root.isSelected()
    assert [root.child(i).text(0) for i in range(root.childCount())] == ['Alpha', 'zeta']
    child = root.child(0)
    assert child.child(0).data(0, 256) is None  # Lazy placeholder.
    child.setExpanded(True)
    assert child.childCount() == 1
    assert child.child(0).text(0) == 'nested'
    child.setExpanded(False)
    child.setExpanded(True)
    assert child.childCount() == 1
    assert requests == []


def test_click_request_and_accept_or_restore(tree, tmp_path, qtbot):
    (tmp_path / 'child').mkdir()
    tree.set_root(tmp_path)
    tree.set_current_directory(tmp_path)
    root = tree.topLevelItem(0)
    child = root.child(0)
    requests = []
    tree.directory_requested.connect(requests.append)
    tree.show()
    qtbot.mouseClick(tree.viewport(), Qt.LeftButton,
                     pos=tree.visualItemRect(child).center())
    assert requests == [str(tmp_path / 'child')]
    assert tree.currentItem() is child
    tree.restore_current_directory()
    assert tree.currentItem() is root
    tree.set_current_directory(tmp_path / 'child')
    tree.setCurrentItem(root)
    tree.restore_current_directory()
    assert tree.currentItem() is child
    assert requests == [str(tmp_path / 'child')]


def test_root_rebuild_is_silent_and_resets_old_item(tree, tmp_path):
    (tmp_path / 'old').mkdir()
    tree.set_root(tmp_path)
    tree.set_current_directory(tmp_path / 'old')
    (tmp_path / 'new').mkdir()
    requests = []
    tree.directory_requested.connect(requests.append)
    tree.set_root(tmp_path)
    tree.restore_current_directory()  # Must not use a deleted item.
    root = tree.topLevelItem(0)
    assert tree.currentItem() is root
    assert [root.child(i).text(0) for i in range(root.childCount())] == ['new', 'old']
    tree.set_current_directory(tmp_path)
    tree.restore_current_directory()
    assert requests == []


def test_empty_root(tree, tmp_path):
    tree.set_root(tmp_path)
    assert tree.topLevelItemCount() == 1
    assert tree.topLevelItem(0).childCount() == 0


def test_unreadable_directory(tree, tmp_path, monkeypatch):
    def fail(path):
        raise PermissionError('unreadable')
    monkeypatch.setattr(Path, 'iterdir', fail)
    errors = []
    tree.enumeration_failed.connect(errors.append)
    assert not tree.set_root(tmp_path)
    assert tree.topLevelItemCount() == 0
    assert errors and 'unreadable' in errors[0]
