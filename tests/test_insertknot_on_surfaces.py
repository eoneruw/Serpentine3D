"""InsertKnot adds a row of control points to a surface.

A lofted panel comes with the handful of points its curves gave it, and
there was no way to get more without rebuilding it: insertknot took
curves only. It takes surfaces now, adding a row through the picked
point — U across, V along, or both — without moving the surface by so
much as a tolerance, and Automatic doubles the rows both ways. The line
the new row will follow ghosts under the cursor before the click.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g


def _panel():
    a = g.make_interp_curve([(0, 0, 0), (50, 10, 0), (100, 0, 0)])
    b = g.make_interp_curve([(0, 0, 80), (50, 30, 80), (100, 0, 80)])
    return g.loft([a, b])


def _closest_point(shape, p):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from serpentine3d.core.occ import BRepBuilderAPI_MakeVertex, gp_Pnt
    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex()
    d = BRepExtrema_DistShapeShape(v, shape)
    return d.Value()


def test_a_u_knot_adds_a_row_and_v_a_column():
    srf = _panel()
    assert g.surface_control_points(srf)[1] == (3, 2)
    assert g.surface_control_points(
        g.insert_surface_knot(srf, (50, 20, 40), "u"))[1] == (4, 2)
    # across the loft the surface is degree 1, so a row there first
    # lifts it to degree 3 (two more poles) and then adds its own
    assert g.surface_control_points(
        g.insert_surface_knot(srf, (50, 20, 40), "v"))[1] == (3, 5)
    assert g.surface_control_points(
        g.insert_surface_knot(srf, (50, 20, 40), "both"))[1] == (4, 5)


def test_the_surface_does_not_move():
    srf = _panel()
    more = g.insert_surface_knot(srf, (50, 20, 40), "both")
    assert g.surface_area(more) == pytest.approx(g.surface_area(srf), rel=1e-6)
    for p in [(20, 5, 10), (80, 10, 70), (50, 15, 40)]:
        assert _closest_point(more, p) == pytest.approx(
            _closest_point(srf, p), abs=1e-4)


def test_automatic_adds_a_row_in_every_span_both_ways():
    srf = _panel()
    auto = g.insert_surface_knots_at_spans(srf)
    nu, nv = g.surface_control_points(auto)[1]
    assert nu > 3 and nv > 2


def test_the_edge_of_the_surface_is_refused_plainly():
    with pytest.raises(g.GeometryError, match="edge"):
        g.insert_surface_knot(_panel(), (0, 0, 0), "u")


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def test_the_command_takes_a_surface_and_a_direction(win):
    o = win.scene.add(_panel(), name="Panel")
    win.selection.set([o.id])
    win.processor.run("insertknot")
    assert win.processor.busy
    win.processor.provide_text("Direction")
    win.processor.provide_text("Both")
    win.processor.provide_text("50,20,40")
    win.processor.provide_text("")
    assert not win.processor.busy
    assert g.surface_control_points(win.scene.get(o.id).shape)[1] == (4, 5)
    assert o.id in win.viewport.cv_enabled, "points shown, ready to drag"
