"""Dragging a control point honours the object snaps.

The drag moved the point freely on a plane facing the camera and never
looked at the Osnap bar, so the only way to land a control point on the
end of another curve was the `move` command. Now the drag runs the cursor
through the same snap lookup a click does: near the end of another curve
with End lit, the point lands on it, with the snap marker showing. The
curve being dragged is left out of the lookup — it is always under the
cursor and would snap the point onto itself.
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
        QApplication.processEvents()     # let the panes take their size
    w._saved_revision = w.scene.revision
    if w.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")
    yield w
    w.mark_saved()
    w.close()


TARGET = (60.0, 40.0, 0.0)


def _scene(win):
    """A polyline to drag, and a line whose far end is the target."""
    poly = win.scene.add(g.make_polyline([(0, 0, 0), (20, 20, 0),
                                          (40, 0, 0)]), name="Poly")
    win.scene.add(g.make_line((60, 0, 0), TARGET), name="Target")
    win.processor.run("top")
    win.processor.run("zoomextents")
    vp = win.viewport
    vp.land_flight()                      # the turn to Top, finished now
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    vp.cv_enabled.add(poly.id)
    vp.snaps.enabled = True
    vp.snaps.types["end"] = True
    return poly


def _px(vp, world):
    s = vp.camera.project(np.array([world], float), vp.width(), vp.height())
    return QPointF(float(s[0, 0]), float(s[0, 1]))


def _drag(vp, start, end):
    press = QMouseEvent(QEvent.Type.MouseButtonPress, start,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, press)
    for t in (0.5, 1.0):
        at = start + (end - start) * t
        move = QMouseEvent(QEvent.Type.MouseMove, at,
                           Qt.MouseButton.NoButton,
                           Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, move)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, end,
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                          Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, release)


def test_a_control_point_dragged_near_an_end_lands_on_it(win):
    poly = _scene(win)
    vp = win.viewport
    # aim a few pixels off the target: the snap has to do the last bit
    end = _px(vp, TARGET) + QPointF(4, -3)
    _drag(vp, _px(vp, (20, 20, 0)), end)
    pts = g.get_control_points(win.scene.get(poly.id).shape)
    assert np.allclose(pts[1], TARGET, atol=1e-6), pts[1]


def test_without_that_snap_the_drag_is_free(win):
    poly = _scene(win)
    vp = win.viewport
    vp.snaps.types["end"] = False
    end = _px(vp, TARGET) + QPointF(4, -3)
    _drag(vp, _px(vp, (20, 20, 0)), end)
    pts = g.get_control_points(win.scene.get(poly.id).shape)
    assert not np.allclose(pts[1], TARGET, atol=1e-3)
    assert np.linalg.norm(np.asarray(pts[1]) - TARGET) < 3.0, \
        "close, since that is where the cursor was"


def test_the_curve_does_not_snap_to_itself(win):
    """Drag the middle point a little: with Near lit and the polyline's
    own segments right under the cursor, it must still go where dragged
    rather than onto its own line."""
    poly = _scene(win)
    vp = win.viewport
    vp.snaps.types["near"] = True
    dest = (22.0, 30.0, 0.0)
    _drag(vp, _px(vp, (20, 20, 0)), _px(vp, dest))
    pts = g.get_control_points(win.scene.get(poly.id).shape)
    # within a pixel or two of the drop, at this zoom a unit or so
    assert np.allclose(pts[1], dest, atol=1.5), pts[1]


def test_the_marker_shows_during_the_drag_and_goes_on_release(win):
    _scene(win)
    vp = win.viewport
    start = _px(vp, (20, 20, 0))
    end = _px(vp, TARGET)
    press = QMouseEvent(QEvent.Type.MouseButtonPress, start,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, press)
    move = QMouseEvent(QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton,
                       Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, move)
    assert vp._active_snap is not None and vp._active_snap[1] == "end"
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, end,
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                          Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, release)
    assert vp._active_snap is None
