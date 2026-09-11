"""A picture in the model: dropped in, cropped with its corners, saved.

A blueprint sheet has the front, side and top of a car on one page, and
the way to trace it is not to cut the page up in an image editor but to
put the sheet in the model three times and show a different part of it
each time. So a picture is an object — picked, moved by the gumball,
copied, undone, saved — that keeps its whole image and shows a window
of it. Its control points are the window's corners; dragging one crops.
Dropping an image file on a pane places it on that pane's construction
plane.

The drawing needs GL and skips on CI's offscreen platform; the shape,
the command plumbing and the file round-trip run everywhere.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.core.picture import (PictureShape, is_image_path,
                                       picture_on_plane)
from serpentine3d.core.scene import Scene


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


@pytest.fixture
def image(tmp_path):
    """An 80x40 PNG: left half red, right half blue."""
    from PySide6.QtGui import QColor, QImage
    QApplication.instance() or QApplication([])
    img = QImage(80, 40, QImage.Format.Format_RGB32)
    for x in range(80):
        for y in range(40):
            img.setPixelColor(x, y, QColor(220, 30, 30) if x < 40
                              else QColor(30, 30, 220))
    path = tmp_path / "sheet.png"
    img.save(str(path))
    return str(path)


def _pic(path="/x/sheet.png", crop=(0, 0, 1, 1)):
    return PictureShape(path, (0, 0, 0), (100, 0, 0), (0, 50, 0), crop,
                        (800, 400))


# ------------------------------------------------------------- the shape

def test_a_picture_is_a_kind_of_its_own_and_a_mesh_underneath():
    p = _pic()
    assert g.shape_kind(p) == "picture"
    assert len(p.triangles) == 2
    assert g.bbox(p) == ((0, 0, 0), (100, 50, 0))


def test_its_control_points_are_the_windows_corners():
    p = _pic(crop=(0.25, 0.0, 0.75, 1.0))
    pts = g.get_control_points(p)
    assert pts[0] == (25.0, 0.0, 0.0)
    assert pts[2] == (75.0, 50.0, 0.0)


def test_moving_a_corner_crops_without_moving_the_image():
    p = _pic()
    q = g.move_control_point(p, 1, (60.0, 10.0, 0.0))
    assert q.crop == pytest.approx((0.0, 0.2, 0.6, 1.0))
    assert np.allclose(q.full_corners(), p.full_corners()), \
        "the image did not move, only the window"


def test_a_corner_cannot_cross_its_opposite_or_leave_the_image():
    p = _pic(crop=(0.2, 0.2, 0.8, 0.8))
    q = g.move_control_point(p, 0, (95.0, 90.0, 0.0))
    s0, t0, s1, t1 = q.crop
    assert s0 < s1 and t0 < t1
    assert t1 <= 1.0
    r = g.move_control_point(p, 2, (-50.0, -50.0, 0.0))
    assert r.crop[2] > r.crop[0] and r.crop[3] > r.crop[1]


def test_the_transforms_keep_it_a_picture():
    p = _pic(crop=(0.1, 0.1, 0.9, 0.9))
    for q in (g.translate(p, (5, 5, 5)), g.rotate(p, (0, 0, 0), (0, 0, 1), 90),
              g.scale(p, (0, 0, 0), 2.0), g.mirror(p, (0, 0, 0), (1, 0, 0)),
              g.copy_shape(p)):
        assert isinstance(q, PictureShape)
        assert q.crop == p.crop and q.path == p.path
    assert np.allclose(g.rotate(p, (0, 0, 0), (0, 0, 1), 90).u, (0, 100, 0))


def test_it_survives_bytes_and_the_file(tmp_path):
    from serpentine3d.fileio import native
    p = _pic(crop=(0.1, 0.2, 0.6, 0.9))
    q = g.shape_from_bytes(g.shape_to_bytes(p))
    assert isinstance(q, PictureShape) and q.crop == p.crop
    scene = Scene()
    o = scene.add(p, name="sheet")
    scene.update(o.id, material={"opacity": 0.4})
    native.save_scene(scene, str(tmp_path / "pic.serp"))
    back = Scene()
    native.load_scene(back, str(tmp_path / "pic.serp"))
    r = back.all()[0]
    assert r.kind == "picture" and r.shape.crop == p.crop
    assert r.material == {"opacity": 0.4}
    assert r.shape.size_px == (800, 400)


def test_placing_on_a_plane_keeps_the_images_aspect():
    from serpentine3d.core.cplane import PRESETS
    p = picture_on_plane("/x/a.png", PRESETS["world"](), (10, 10, 0), 80,
                         size_px=(800, 400))
    assert np.linalg.norm(p.u) == pytest.approx(80)
    assert np.linalg.norm(p.v) == pytest.approx(40)
    assert np.allclose(p.at(0.5, 0.5), (10, 10, 0))


def test_only_images_are_pictures():
    assert is_image_path("a.PNG") and is_image_path("b.jpeg")
    assert not is_image_path("c.step")


def test_the_commands_know_the_kind():
    from serpentine3d.commands.base import resolve
    assert resolve("selpicture") is not None
    assert resolve("pictureframe") is not None


# ------------------------------------------------------------ the window

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
    yield w
    w.mark_saved()
    w.close()


def _drop(vp, path):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    ev = QDropEvent(QPointF(vp.width() / 2, vp.height() / 2),
                    Qt.DropAction.CopyAction, mime, Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier)
    vp.dropEvent(ev)
    return ev


def test_dropping_an_image_on_a_front_pane_stands_it_up(win, image):
    vp = win.viewport
    win.processor.run("front")
    vp.land_flight()
    ev = _drop(vp, image)
    assert ev.isAccepted()
    objs = win.scene.all()
    assert len(objs) == 1 and objs[0].kind == "picture"
    assert win.selection.ids == [objs[0].id], "picked, ready to move"
    assert abs(objs[0].shape.normal()[1]) > 0.99, "facing the Front view"
    win.processor.run("undo")
    assert not win.scene.all(), "undoable like anything added"


def test_dropping_something_else_is_refused(win, tmp_path):
    other = tmp_path / "part.step"
    other.write_text("not an image")
    ev = _drop(win.viewport, str(other))
    assert not ev.isAccepted()
    assert not win.scene.all()


def test_the_properties_panel_offers_crop_and_opacity(win, image):
    vp = win.viewport
    _drop(vp, image)
    o = win.scene.all()[0]
    panel = win.properties
    assert panel.form.isRowVisible(panel.crop_widget)
    panel.crop_btn.setChecked(True)
    assert o.id in vp.cv_enabled, "the crop corners are its control points"
    panel.opacity_slider.setValue(40)
    assert win.scene.get(o.id).material["opacity"] == pytest.approx(0.4)
    win.scene.replace_shape(o.id, o.shape.with_crop((0.2, 0.2, 0.8, 0.8)))
    panel._reset_crop()
    assert win.scene.get(o.id).shape.crop == (0.0, 0.0, 1.0, 1.0)


def _gl(win):
    if win.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")


def test_a_dragged_corner_crops_in_the_pane(win, image):
    _gl(win)
    vp = win.viewport
    win.processor.run("top")
    win.processor.run("zoomextents")
    vp.land_flight()
    _drop(vp, image)
    o = win.scene.all()[0]
    vp.cv_enabled.add(o.id)
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    pts = vp._cv_points(o)
    scr = vp.camera.project(pts, vp.width(), vp.height())
    mid = vp.camera.project(np.array([(pts[0] + pts[1]) / 2]),
                            vp.width(), vp.height())[0]
    start = QPointF(float(scr[1, 0]), float(scr[1, 1]))
    end = QPointF(float(mid[0]), float(mid[1]))
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
    crop = win.scene.get(o.id).shape.crop
    assert crop[2] == pytest.approx(0.5, abs=0.03), crop
    assert crop[0] == 0.0 and crop[3] == 1.0


def test_the_picture_is_painted_with_its_image(win, image):
    _gl(win)
    vp = win.viewport
    win.processor.run("top")
    _drop(vp, image)
    o = win.scene.all()[0]
    win.selection.clear()
    win.processor.run("zoomextents")
    vp.land_flight()
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    img = vp.grabFramebuffer()
    sh = o.shape
    left = vp.camera.project(np.array([sh.at(0.25, 0.5)]), vp.width(),
                             vp.height())[0]
    right = vp.camera.project(np.array([sh.at(0.75, 0.5)]), vp.width(),
                              vp.height())[0]
    cl = img.pixelColor(int(left[0]), int(left[1]))
    cr = img.pixelColor(int(right[0]), int(right[1]))
    assert cl.red() > cl.blue() + 80, "the red half is on the left"
    assert cr.blue() > cr.red() + 80, "the blue half is on the right"


def test_the_gumballs_scale_box_works_on_a_picture_and_a_mesh():
    """Scaling along one axis went through OCCT's GTransform, which has
    no idea what a picture is; the gumball's scale box raised on every
    mouse move. Meshes had the same hole."""
    from serpentine3d.core.mesh import MeshShape
    p = _pic()
    q = g.scale_along_axis(p, (0, 0, 0), (1, 0, 0), 2.0)
    assert isinstance(q, PictureShape)
    assert np.allclose(q.u, (200, 0, 0)) and np.allclose(q.v, (0, 50, 0))
    m = MeshShape(np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], float),
                  np.array([[0, 1, 2]], np.uint32))
    r = g.scale_along_axis(m, (0, 0, 0), (0, 1, 0), 3.0)
    assert np.allclose(r.vertices[2], (0, 30, 0))


def test_drawing_a_picture_leaves_texture_unit_0_as_it_found_it(win, image):
    """A display mode lit by an environment map keeps its map on unit 0
    for the frame; a picture drawn mid-frame bound its own image there
    and the objects after it reflected the blueprint — coming and going
    as the view changed the draw order."""
    _gl(win)
    from OpenGL import GL
    vp = win.viewport
    _drop(vp, image)
    o = win.scene.all()[0]
    for _ in range(3):                    # a frame, so the picture is on the GPU
        vp.update()
        QApplication.processEvents()
    gpu = vp._gpu.get(o.id)
    assert gpu is not None
    vp.makeCurrent()
    try:
        probe = GL.glGenTextures(1)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, probe)
        vp._draw_picture(o, gpu, np.eye(4, dtype=np.float32))
        assert int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D)) == probe
    finally:
        vp.doneCurrent()


def test_the_placed_picture_stays_selected(win, image):
    """The command set the selection itself, and the processor let it
    go on the way out; F10 then had nothing to show."""
    win.processor.run("pictureframe")
    win.processor.provide_text(str(image))
    win.processor.provide_text("0,0,0")
    win.processor.provide_text("40,30,0")
    assert not win.processor.busy
    assert len(win.selection.ids) == 1
    assert win.scene.get(win.selection.ids[0]).kind == "picture"


def test_an_opacity_drag_is_one_undo_step(win, image):
    _drop(win.viewport, image)
    o = win.scene.all()[0]
    win.selection.set([o.id])
    panel = win.properties
    depth = len(win.history._undo)
    panel.opacity_slider.sliderPressed.emit()
    for v in (90, 70, 50):
        panel.opacity_slider.setValue(v)
    panel.opacity_slider.sliderReleased.emit()
    assert len(win.history._undo) == depth + 1
    assert win.scene.get(o.id).material["opacity"] == pytest.approx(0.5)
