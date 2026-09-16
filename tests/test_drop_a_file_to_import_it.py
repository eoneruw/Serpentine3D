"""Any file Import can read can be dropped on the window.

Dragging a .step or .stl onto Serpentine3D did nothing — only the file
dialog knew how to take one. A drop now imports the file (adds its objects,
one undo step), a batch of files imports them all, and a .serp — a whole
document — opens, so Save goes back to that file.
"""

import os

import pytest
from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from serpentine3d import fileio
from serpentine3d.app import MainWindow
from serpentine3d.core import geometry as g


@pytest.fixture
def window():
    w = MainWindow()
    yield w
    w.mark_saved()          # or closing asks about unsaved changes
    w.close()


def _mime(*paths):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return m


def _drop(w, mime):
    pos = QPointF(w.width() / 2, w.height() / 2)
    enter = QDragEnterEvent(pos.toPoint(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    w.dragEnterEvent(enter)
    drop = QDropEvent(pos, Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    w.dropEvent(drop)
    return enter.isAccepted(), drop.isAccepted()


def _step_with_box(path):
    from serpentine3d.core.scene import Scene
    s = Scene()
    s.add(g.make_box((0, 0, 0), 10, 10, 10), name="box")
    fileio.export_file(s, path)
    return path


def test_a_step_dropped_on_the_window_is_imported(window, tmp_path):
    path = _step_with_box(str(tmp_path / "box.step"))
    accepted, dropped = _drop(window, _mime(path))
    assert accepted and dropped
    assert len(window.scene.all()) == 1
    assert window.ctx.current_path is None, "an import is not an open"


def test_a_drop_adds_to_what_is_there_and_undoes_as_one(window, tmp_path):
    window.scene.add(g.make_box((0, 0, 0), 1, 1, 1), name="mine")
    path = _step_with_box(str(tmp_path / "box.step"))
    _drop(window, _mime(path, path))
    assert len(window.scene.all()) == 3, "two drops, two boxes added"
    window.history.undo()
    assert len(window.scene.all()) == 2
    window.history.undo()
    assert len(window.scene.all()) == 1


def test_a_serp_dropped_on_an_empty_document_opens_it(window, tmp_path):
    from serpentine3d.core.scene import Scene
    s = Scene()
    s.add(g.make_box((0, 0, 0), 2, 2, 2), name="saved")
    path = str(tmp_path / "model.serp")
    fileio.export_file(s, path)
    _drop(window, _mime(path))
    assert len(window.scene.all()) == 1
    assert window.ctx.current_path == path, "Save should go back to it"


def test_a_serp_dropped_on_a_document_opens_it_and_undo_brings_the_work_back(
        window, tmp_path):
    from serpentine3d.core.scene import Scene
    s = Scene()
    s.add(g.make_box((0, 0, 0), 2, 2, 2), name="saved")
    path = str(tmp_path / "model.serp")
    fileio.export_file(s, path)
    window.scene.add(g.make_box((0, 0, 0), 1, 1, 1), name="mine")
    _drop(window, _mime(path))
    assert [o.name for o in window.scene.all()] == ["saved"]
    assert window.ctx.current_path == path
    window.history.undo()
    assert [o.name for o in window.scene.all()] == ["mine"]


def test_files_import_cannot_read_are_left_alone(window, tmp_path):
    txt = str(tmp_path / "notes.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("hello")
    accepted, dropped = _drop(window, _mime(txt))
    assert not accepted and not dropped
    assert window.scene.all() == []
    assert MainWindow.droppable_paths(_mime(str(tmp_path))) == [], "a folder"


def test_every_import_format_is_droppable(tmp_path):
    for ext in fileio.IMPORT_EXTS:
        p = str(tmp_path / f"file{ext}")
        open(p, "w", encoding="utf-8").close()
        assert MainWindow.droppable_paths(_mime(p)) == [p], ext
    assert os.path.exists(p)
