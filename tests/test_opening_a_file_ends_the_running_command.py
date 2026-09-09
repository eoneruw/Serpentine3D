"""Opening or starting a drawing ends the command that was running.

Extrude was left asking for curves while a file opened underneath it,
so the next click on the canvas answered that question — badly, since
the curves it wanted were gone — instead of picking anything, and
nothing on screen said why. A command waiting on the old drawing has
nothing to wait for in the new one, so New and Open cancel it, and
drop the selection and any control points shown with it.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.fileio import native


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def _waiting_extrude(win):
    win.scene.add(g.make_line((0, 0, 0), (10, 0, 0)), name="L")
    win.processor.run("extrude")
    assert win.processor.busy, "extrude is waiting for curves"


def test_opening_a_file_cancels_the_waiting_command(win, tmp_path):
    from serpentine3d.core.scene import Scene
    other = Scene()
    other.add(g.make_box((0, 0, 0), 5, 5, 5), name="Box")
    path = str(tmp_path / "other.serp")
    native.save_scene(other, path)
    _waiting_extrude(win)
    win._open_path(path)
    assert not win.processor.busy
    assert [o.name for o in win.scene.all()] == ["Box"]


def test_starting_a_new_drawing_cancels_it_too(win):
    _waiting_extrude(win)
    win.start_new("mm")
    assert not win.processor.busy
    assert not win.scene.all()


def test_the_selection_and_shown_points_go_with_the_old_drawing(win):
    o = win.scene.add(g.make_line((0, 0, 0), (10, 0, 0)), name="L")
    win.selection.set([o.id])
    win.viewport.cv_enabled.add(o.id)
    win.start_new("mm")
    assert win.selection.ids == []
    assert not win.viewport.cv_enabled


def test_a_click_after_opening_picks_again(win, tmp_path):
    """The complaint itself: the click has to land on the new object."""
    from serpentine3d.core.scene import Scene
    other = Scene()
    other.add(g.make_box((0, 0, 0), 5, 5, 5), name="Box")
    path = str(tmp_path / "other.serp")
    native.save_scene(other, path)
    _waiting_extrude(win)
    win._open_path(path)
    box = win.scene.all()[0]
    from PySide6.QtCore import Qt
    win._on_object_clicked(box.id, Qt.KeyboardModifier.NoModifier)
    assert win.selection.ids == [box.id]
