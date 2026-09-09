"""Dragging one held control point drags all of them.

Two curves that meet at a corner have a control point each there, and a
band drawn round the corner holds both. Dragging then moved only the
one under the cursor and left the other behind, so the corner came
apart: what is held is what should move, the way the gumball already
moves them all. A press on a point that is already held keeps the group
held, too, rather than dropping the others.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g


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
    w.resize(900, 600)
    w.show()
    for _ in range(3):
        QApplication.processEvents()
    w._saved_revision = w.scene.revision
    if w.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")
    yield w
    w.mark_saved()
    w.close()


def _corner(win):
    """Two lines meeting at (20, 0, 0), both with points on, both ends
    at the corner held."""
    a = win.scene.add(g.make_line((0, 0, 0), (20, 0, 0)), name="A")
    b = win.scene.add(g.make_line((20, 0, 0), (20, 20, 0)), name="B")
    win.processor.run("top")
    win.processor.run("zoomextents")
    vp = win.viewport
    vp.land_flight()
    vp.cv_enabled.update({a.id, b.id})
    win.selection.set([])
    win.selection.set_subobjects([(a.id, "cv", 1), (b.id, "cv", 0)])
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    return a, b


def _px(vp, world):
    s = vp.camera.project(np.array([world], float), vp.width(), vp.height())
    return QPointF(float(s[0, 0]), float(s[0, 1]))


def _drag(vp, start, end):
    for kind, at, b, bs in ((QEvent.Type.MouseButtonPress, start,
                             Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton),
                            (QEvent.Type.MouseMove, end,
                             Qt.MouseButton.NoButton,
                             Qt.MouseButton.LeftButton),
                            (QEvent.Type.MouseButtonRelease, end,
                             Qt.MouseButton.LeftButton,
                             Qt.MouseButton.NoButton)):
        QApplication.sendEvent(vp, QMouseEvent(
            kind, at, b, bs, Qt.KeyboardModifier.NoModifier))


def test_both_ends_of_a_corner_move_together(win):
    a, b = _corner(win)
    vp = win.viewport
    _drag(vp, _px(vp, (20, 0, 0)), _px(vp, (30, 5, 0)))
    end_a = g.get_control_points(win.scene.get(a.id).shape)[1]
    end_b = g.get_control_points(win.scene.get(b.id).shape)[0]
    assert np.allclose(end_a, end_b, atol=1e-6), "the corner came apart"
    assert np.linalg.norm(np.asarray(end_a) - (30, 5, 0)) < 1.0


def test_pressing_a_held_point_keeps_the_others_held(win):
    a, b = _corner(win)
    vp = win.viewport
    at = _px(vp, (20, 0, 0))
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonPress, at, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert len(win.selection.subobjects) == 2
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonRelease, at, Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


def test_a_point_not_held_is_dragged_alone_as_before(win):
    a, b = _corner(win)
    vp = win.viewport
    win.selection.set_subobjects([])
    _drag(vp, _px(vp, (0, 0, 0)), _px(vp, (-5, 5, 0)))
    start_a = g.get_control_points(win.scene.get(a.id).shape)[0]
    end_b = g.get_control_points(win.scene.get(b.id).shape)[0]
    assert np.linalg.norm(np.asarray(start_a) - (-5, 5, 0)) < 1.0
    assert np.allclose(end_b, (20, 0, 0)), "nothing else moved"
