"""Weight: pull a curve or surface toward a control point, by dragging.

A control point's weight is the other way to sharpen a turn — Rhino's
Weight — and there was none. Now `weight` takes the held points and a
chip to drag: above 1 the shape tightens in toward the point, high
enough and the turn is nearly a kink; below 1 it goes soft. Enter
keeps it, Escape puts the shape back.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


def _arch():
    return g.make_control_curve([(0, 0, 0), (50, 50, 0), (100, 0, 0)],
                                degree=2)


def _height(curve):
    """How high the curve itself reaches (bbox is the loose hull)."""
    return max(p[1] for p in g.sample_curve(curve, 65))


# ------------------------------------------------------------ geometry

def test_more_weight_pulls_the_curve_toward_the_point():
    c = _arch()
    assert g.control_point_weight(c, 1) == 1.0
    heavy = g.set_control_point_weights(c, [1], 5.0)
    light = g.set_control_point_weights(c, [1], 0.3)
    assert _height(heavy) > _height(c) > _height(light)
    assert g.control_point_weight(heavy, 1) == 5.0
    assert g.get_control_points(heavy) == g.get_control_points(c), \
        "the points stay where they are"
    with pytest.raises(g.GeometryError):
        g.set_control_point_weights(c, [1], 0)


def test_a_surface_pulls_toward_a_held_row_point():
    srf = g.loft([g.make_interp_curve([(0, 0, 0), (50, 10, 0), (100, 0, 0)]),
                  g.make_interp_curve([(0, 0, 80), (50, 30, 80),
                                       (100, 0, 80)])])
    pts, (nu, nv) = g.surface_control_points(srf)
    apex = max(range(len(pts)), key=lambda i: pts[i][1])
    heavy = g.set_control_point_weights(srf, [apex], 6.0)
    # the surface comes closer to the point it is pulled toward
    assert g.distance_point_to_shape(heavy, pts[apex]) < \
        g.distance_point_to_shape(srf, pts[apex])
    assert g.control_point_weight(heavy, apex) == 6.0
    assert g.surface_control_points(heavy)[1] == (nu, nv)


# ------------------------------------------------------------- command

@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def test_weight_drags_the_held_point_and_enter_keeps_it(win):
    o = win.scene.add(_arch(), name="Arch")
    win.viewport.cv_enabled.add(o.id)
    win.selection.set_subobjects([(o.id, "cv", 1)])
    proc = win.processor
    proc.run("weight")
    assert proc.busy
    assert proc.option_chips() == [("Weight", "1")]
    before = _height(win.scene.get(o.id).shape)
    proc.set_option("Weight", "2.5", quiet=True)     # a drag on the chip
    assert _height(win.scene.get(o.id).shape) > before, "follows the drag"
    proc.set_option("Weight", "4")
    proc.provide_text("")
    assert not proc.busy
    assert g.control_point_weight(win.scene.get(o.id).shape, 1) == 4.0
    assert win.selection.subobjects == [(o.id, "cv", 1)], "still held"
    proc.run("undo")
    assert g.control_point_weight(win.scene.get(o.id).shape, 1) == 1.0


def test_escape_puts_the_shape_back(win):
    o = win.scene.add(_arch(), name="Arch")
    win.selection.set_subobjects([(o.id, "cv", 1)])
    proc = win.processor
    proc.run("weight")
    proc.set_option("Weight", "8")
    assert _height(win.scene.get(o.id).shape) > 40
    proc.cancel()
    assert _height(win.scene.get(o.id).shape) == pytest.approx(25, abs=1e-6)


def test_with_nothing_held_it_asks(win):
    o = win.scene.add(_arch(), name="Arch")
    win.selection.set([o.id])
    proc = win.processor
    said = []
    proc.ctx.add_echo_listener(said.append)
    proc.run("weight")
    assert proc.busy, "waiting for the points to be clicked"
    win.selection.toggle_subobject(o.id, "cv", 1)
    proc.provide_text("")
    assert proc.option_chips() == [("Weight", "1")]
    proc.provide_text("3")
    proc.provide_text("")
    assert not proc.busy
    assert g.control_point_weight(win.scene.get(o.id).shape, 1) == 3.0
