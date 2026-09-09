"""In a parallel view, what is drawn can be picked — all of it.

A parallel view's near plane sits behind the eye (Camera.clip_planes), so
the nearer half of a model stays visible when you zoom in on a detail in
Right or Top. But every picker took "depth <= 0" as "behind the camera",
measured from the eye, so a control point you could plainly see would not
take a click, and a drag on one hit nothing because the ray started at
the eye and the point was behind it. Depth in a parallel view is now
measured from the near plane, and parallel rays start there.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.ui.camera import Camera


# ------------------------------------------------------------ the camera

def _right_view_camera():
    cam = Camera()
    cam.set_standard_view("right")
    cam.target = np.array([200.0, 0.0, 0.0])
    cam.distance = 30.0                   # zoomed in: the eye is at x=230
    cam.scene_bounds = ((0, 0, 0), (400, 60, 30))
    return cam


def test_a_point_between_the_eye_and_the_near_plane_has_positive_depth():
    cam = _right_view_camera()
    ahead_of_eye = np.array([[400.0, 0.0, 0.0]])       # nearer than the eye
    depth = cam.project(ahead_of_eye, 800, 600)[0, 2]
    assert depth > 0, "it is drawn, so a picker must not call it behind"


def test_depth_still_orders_front_to_back():
    cam = _right_view_camera()
    pts = np.array([[400.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    depth = cam.project(pts, 800, 600)[:, 2]
    assert depth[0] < depth[1], "the nearer point is the smaller depth"


def test_a_parallel_ray_reaches_a_plane_in_front_of_the_eye():
    from serpentine3d.utils.math3d import ray_plane
    cam = _right_view_camera()
    origin, direction = cam.ray_through(400, 300, 800, 600)
    plane_pt = np.array([400.0, 0.0, 0.0])           # nearer than the eye
    hit = ray_plane(origin, direction, plane_pt, -direction)
    assert hit is not None


def test_perspective_is_untouched():
    cam = Camera()
    cam.scene_bounds = ((0, 0, 0), (400, 60, 30))
    behind = cam.position + (cam.position - cam.target)
    depth = cam.project(np.array([behind]), 800, 600)[0, 2]
    assert depth < 0, "behind a perspective camera is still behind"


# ------------------------------------------------------------ the window

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


def _zoomed_in_right(win):
    o = win.scene.add(g.make_interp_curve([(0, 0, 0), (200, 150, 100),
                                           (400, 60, 30)]), name="C")
    vp = win.viewport
    vp.cv_enabled.add(o.id)
    win.processor.run("right")
    win.processor.run("zoomextents")
    vp.land_flight()                      # the turn to Right, finished now
    vp.camera.target = np.array([300.0, 60.0, 30.0])
    vp.camera.distance = 60.0             # the eye at x=360; the far end is nearer
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    return o


def _drag(vp, start, end):
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


def test_a_visible_control_point_nearer_than_the_eye_takes_a_drag(win):
    o = _zoomed_in_right(win)
    vp = win.viewport
    pts = vp._cv_points(win.scene.get(o.id))
    scr = vp.camera.project(pts, vp.width(), vp.height())
    eye_depth = float((pts[2] - vp.camera.position)
                      @ (vp.camera.target - vp.camera.position)
                      / np.linalg.norm(vp.camera.target - vp.camera.position))
    assert eye_depth < 0, "the test wants the point nearer than the eye"
    start = QPointF(float(scr[2, 0]), float(scr[2, 1]))
    _drag(vp, start, start + QPointF(40, 0))
    moved = g.get_control_points(win.scene.get(o.id).shape)[2]
    assert win.selection.subobjects_of(o.id, "cv") == [2], "it was picked"
    assert not np.allclose(moved, (400, 60, 30)), "and it moved"


def test_a_click_on_such_a_curve_selects_it(win):
    o = _zoomed_in_right(win)
    vp = win.viewport
    vp.cv_enabled.discard(o.id)
    pts = np.asarray(g.sample_curve(win.scene.get(o.id).shape, 40), float)
    near_end = pts[-3]                    # nearer than the eye in Right
    scr = vp.camera.project(np.array([near_end]), vp.width(), vp.height())
    assert vp.pick_object(float(scr[0, 0]), float(scr[0, 1])) == o.id
