"""Double-click a curve and a control point appears where you clicked.

`insertknot` does the same by the book — select the curves, Enter, then
click along them — which is three steps for what is one gesture when
you are shaping a line by hand. The curve does not move (a knot goes
in), the new point comes up held so the next drag pulls on it, and the
curve's points are shown if they were not already.

Picking needs the tessellated curve and a real projection, so these run
with a GL context and skip on CI's offscreen platform.
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
    w._saved_revision = w.scene.revision
    if w.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")
    yield w
    w.mark_saved()
    w.close()


def _curve(win):
    o = win.scene.add(g.make_interp_curve([(0, 0, 0), (20, 15, 0),
                                           (40, 0, 0)]), name="Arc")
    win.processor.run("top")
    win.processor.run("zoomextents")
    for _ in range(3):
        win.viewport.update()
        QApplication.processEvents()
    return o


def _pixel_of(vp, world):
    s = vp.camera.project(np.array([world], float), vp.width(), vp.height())
    return float(s[0, 0]), float(s[0, 1])


def _on_curve(shape, t=0.3):
    """A point on the curve, from its polyline approximation."""
    pts = np.asarray(g.sample_curve(shape, 50), float)
    return tuple(pts[int(t * (len(pts) - 1))])


def test_a_double_click_on_a_curve_adds_a_point_there(win):
    o = _curve(win)
    vp = win.viewport
    before = g.get_control_points(o.shape)
    px, py = _pixel_of(vp, _on_curve(o.shape))
    assert vp.add_control_point_at(px, py)
    after = g.get_control_points(win.scene.get(o.id).shape)
    assert len(after) == len(before) + 1


def test_the_curve_itself_does_not_move(win):
    o = _curve(win)
    vp = win.viewport
    samples = np.asarray(g.sample_curve(o.shape, 30), float)
    px, py = _pixel_of(vp, _on_curve(o.shape, 0.6))
    assert vp.add_control_point_at(px, py)
    after = np.asarray(g.sample_curve(win.scene.get(o.id).shape, 30), float)
    assert np.allclose(samples, after, atol=1e-6)


def test_the_new_point_comes_up_held_with_points_shown(win):
    o = _curve(win)
    vp = win.viewport
    assert o.id not in vp.cv_enabled
    px, py = _pixel_of(vp, _on_curve(o.shape))
    assert vp.add_control_point_at(px, py)
    assert o.id in vp.cv_enabled, "points on, so you can see what you got"
    held = win.selection.subobjects_of(o.id, "cv")
    assert len(held) == 1, "the new point is held, ready to drag"
    assert win.selection.is_selected(o.id)


def test_it_is_undoable(win):
    o = _curve(win)
    vp = win.viewport
    before = len(g.get_control_points(o.shape))
    px, py = _pixel_of(vp, _on_curve(o.shape))
    assert vp.add_control_point_at(px, py)
    win.processor.run("undo")
    assert len(g.get_control_points(win.scene.get(o.id).shape)) == before


def test_double_clicking_empty_space_does_nothing(win):
    _curve(win)
    vp = win.viewport
    assert not vp.add_control_point_at(3, 3)


def test_the_double_click_event_reaches_it(win):
    o = _curve(win)
    vp = win.viewport
    before = len(g.get_control_points(o.shape))
    px, py = _pixel_of(vp, _on_curve(o.shape, 0.4))
    ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(px, py),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, ev)
    assert len(g.get_control_points(win.scene.get(o.id).shape)) == before + 1
