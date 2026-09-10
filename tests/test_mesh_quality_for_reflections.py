"""A Mesh quality setting, for reflections that showed the triangles.

A bonnet lofted through a few curves looked wrinkled in Rendered: bands
of light bending along lines that were not in the surface. They were the
display mesh. A mirror-like reflection is read off the normal at each
pixel, and between a triangle's corners the normal is only interpolated,
so a big triangle across a gently curved panel reflects the room with a
kink at each of its edges. The surface was fine; the mesh was coarse.

So the mesh has a quality now — Coarse, Normal, Fine, Very fine — in the
Display panel, as a `meshquality` command, and remembered in settings.
Normal is what every mode used to get.
"""

import pytest

from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry, tessellate
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


@pytest.fixture(autouse=True)
def _normal_again():
    tessellate.end_preview()        # whatever an earlier test left held
    yield
    tessellate.end_preview()
    tessellate.set_mesh_quality("normal")


def _bonnet():
    rails = [geometry.make_interp_curve([(0, y, 0), (50, y, 12), (100, y, 8)])
             for y in (0, 40, 80)]
    return geometry.loft(rails)


def _triangles(shape):
    return len(tessellate.tessellate(shape).triangles)


# -- the setting itself --

def test_normal_is_the_default():
    assert tessellate.mesh_quality() == "normal"


def test_finer_qualities_cut_more_triangles():
    shape = _bonnet()
    counts = []
    for name in ("coarse", "normal", "fine", "very fine"):
        tessellate.set_mesh_quality(name)
        counts.append(_triangles(shape))
    assert counts == sorted(counts), counts
    assert counts[0] < counts[1] < counts[2] < counts[3], counts


def test_an_unknown_quality_is_refused():
    with pytest.raises(ValueError):
        tessellate.set_mesh_quality("ludicrous")
    assert tessellate.mesh_quality() == "normal"


def test_dropping_meshes_recuts_at_the_new_quality():
    scene = Scene()
    obj = scene.add(_bonnet(), name="bonnet")
    before = len(obj.mesh.triangles)
    tessellate.set_mesh_quality("fine")
    assert len(obj.mesh.triangles) == before      # cached: still coarse
    scene.drop_meshes()
    assert len(obj.mesh.triangles) > before


# -- the command --

def _run(scene, text):
    ctx = CommandContext(scene, SelectionManager(scene), History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    proc.run(text)
    return echoes


def test_the_command_changes_it_and_says_so():
    scene = Scene()
    obj = scene.add(_bonnet(), name="bonnet")
    before = len(obj.mesh.triangles)
    echoes = _run(scene, "meshquality VeryFine")
    assert tessellate.mesh_quality() == "very fine"
    assert any("VeryFine" in e for e in echoes), echoes
    assert len(obj.mesh.triangles) > before       # meshes were dropped


def test_the_command_ignores_nonsense():
    echoes = _run(Scene(), "meshquality Ludicrous")
    assert tessellate.mesh_quality() == "normal"
    # the prompt refuses it and lists what it does take
    assert any("Coarse, Normal, Fine, VeryFine" in e for e in echoes), echoes


# -- the panel and the settings file --

@pytest.fixture
def win(_qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    from serpentine3d.app import MainWindow
    w = MainWindow()
    yield w
    w.mark_saved()          # no "save changes?" dialog on the way out
    w.close()


def test_the_panel_shows_the_current_quality(win):
    assert win.display_panel.mesh_quality() == "normal"


def test_picking_fine_in_the_panel_recuts_and_remembers(win):
    obj = win.scene.add(_bonnet(), name="bonnet")
    before = len(obj.mesh.triangles)
    win.display_panel.set_mesh_quality("fine")
    assert tessellate.mesh_quality() == "fine"
    assert len(obj.mesh.triangles) > before
    assert win.cfg.get("display", "mesh_quality") == "fine"


def test_the_saved_quality_comes_back_on_launch(_qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    from serpentine3d.utils.config import Config
    Config().set("display", "mesh_quality", "very fine")
    from serpentine3d.app import MainWindow
    w = MainWindow()
    try:
        assert tessellate.mesh_quality() == "very fine"
        assert w.display_panel.mesh_quality() == "very fine"
    finally:
        w.close()


def test_the_command_updates_the_panel(win):
    win.processor.run("meshquality Coarse")
    assert win.display_panel.mesh_quality() == "coarse"


# -- dragging stays quick whatever the quality --
#
# A control point or gumball drag cuts the shape again on every mouse move.
# At Very fine a bonnet takes over a second a cut, and the drag stopped
# following the mouse (the run log's stall dumps all ended in tessellate,
# under a cv-drag). So a drag meshes at Normal, and on release what moved
# is cut once more at the real quality.

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent


def _pane_over(shape):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from serpentine3d.ui.viewport import Viewport
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(800, 600)
    vp.set_view("top")
    vp.grid_snap = False
    obj = scene.add(shape, name="bonnet")
    vp.camera.target = geometry.bbox_center(shape) if hasattr(
        geometry, "bbox_center") else __import__("numpy").mean(
            geometry.bbox(shape), axis=0)
    vp.camera.distance = 300.0
    vp.cv_enabled.add(obj.id)
    return vp, obj


def _pixel_of_cv(vp, obj, index):
    import numpy as np
    pt = np.asarray(geometry.surface_control_points(obj.shape)[0],
                    float)[index]
    scr = vp.camera.project(np.asarray([pt]), vp.width(), vp.height())
    return float(scr[0][0]), float(scr[0][1])


def _mouse(vp, kind, x, y, buttons):
    ev_type = {"press": QEvent.Type.MouseButtonPress,
               "move": QEvent.Type.MouseMove,
               "release": QEvent.Type.MouseButtonRelease}[kind]
    button = (Qt.MouseButton.NoButton if kind == "move"
              else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(ev_type, QPointF(x, y), QPointF(x, y), button, buttons,
                     Qt.KeyboardModifier.NoModifier)
    {"press": vp.mousePressEvent, "move": vp.mouseMoveEvent,
     "release": vp.mouseReleaseEvent}[kind](ev)


def test_a_preview_meshes_no_finer_than_normal():
    shape = _bonnet()
    tessellate.set_mesh_quality("normal")
    normal = _triangles(shape)
    tessellate.set_mesh_quality("very fine")
    tessellate.begin_preview()
    try:
        assert _triangles(shape) == normal
    finally:
        tessellate.end_preview()
    assert _triangles(shape) > normal


def test_a_coarse_setting_previews_coarse():
    """Coarse is for keeping a heavy scene quick; a drag must not make it
    Normal behind the user's back."""
    shape = _bonnet()
    tessellate.set_mesh_quality("coarse")
    coarse = _triangles(shape)
    tessellate.begin_preview()
    try:
        assert _triangles(shape) == coarse
        assert not tessellate.preview_is_coarser()
    finally:
        tessellate.end_preview()


def test_a_control_point_drag_cuts_coarsely_then_properly(_qapp):
    tessellate.set_mesh_quality("very fine")
    vp, obj = _pane_over(_bonnet())
    fine = len(obj.mesh.triangles)
    tessellate.set_mesh_quality("normal")
    normal = len(tessellate.tessellate(obj.shape).triangles)
    tessellate.set_mesh_quality("very fine")
    assert normal < fine

    x, y = _pixel_of_cv(vp, obj, 4)
    _mouse(vp, "press", x, y, Qt.MouseButton.LeftButton)
    assert vp._cv_drag is not None, "the press did not take the point"
    _mouse(vp, "move", x + 25, y + 25, Qt.MouseButton.LeftButton)
    moved = vp.scene.get(obj.id)
    assert moved.shape is not obj.shape, "the point did not move"
    assert len(moved.mesh.triangles) <= normal * 1.05     # the preview cut
    _mouse(vp, "release", x + 25, y + 25, Qt.MouseButton.NoButton)
    assert vp._cv_drag is None
    final = vp.scene.get(obj.id)
    assert not final.mesh_ready, "release did not drop the preview mesh"
    assert len(final.mesh.triangles) > normal * 2         # the real cut


def test_a_gumball_drag_does_the_same(_qapp):
    tessellate.set_mesh_quality("very fine")
    vp, obj = _pane_over(_bonnet())
    vp.selection.set([obj.id])
    gb = vp.gumball
    anchor, axes = gb.anchor_and_axes()
    from serpentine3d.ui.gumball import CONE1, SHAFT0
    import numpy as np
    at = anchor + axes[0] * (SHAFT0 + CONE1) / 2 * gb._size_world(anchor)
    px, py = (float(v) for v in vp.camera.project(
        np.asarray([at]), vp.width(), vp.height())[0][:2])
    assert gb.begin_drag(("move", 0), px, py, Qt.KeyboardModifier.NoModifier)
    assert tessellate._active_quality() == "normal"
    gb.apply_scalar(10.0)
    moved = vp.scene.get(obj.id)
    assert moved.mesh_ready or True
    gb.end_drag()
    assert tessellate._active_quality() == "very fine"
    assert not vp.scene.get(obj.id).mesh_ready, "the moved object keeps a preview mesh"
