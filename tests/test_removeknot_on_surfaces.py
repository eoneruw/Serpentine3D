"""A row of control points comes off a surface: RemoveKnot, or Delete.

InsertKnot put rows in; there was no way to take one out again.
Holding a surface's control points and pressing Delete said "Not a
curve" and did nothing, and removeknot took curves only. Now Delete
on held surface points takes out the row (or column) they sit on —
a surface's points come in rows, and one cannot go alone — and
removeknot takes surfaces with a Direction, ghosting the surface as it
will be. Either way it says how far the surface moved.
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


def _panel():
    """A 7x7 grid of control points: a loft of two lines (degree 1 both
    ways, lifted to 3 by the first rows) with two rounds of rows."""
    srf = g.loft([g.make_line((0, 0, 0), (100, 0, 0)),
                  g.make_line((0, 50, 0), (100, 50, 10))])
    return g.insert_surface_knots_at_spans(
        g.insert_surface_knots_at_spans(srf))


# ------------------------------------------------------------ geometry

def test_a_u_row_or_a_v_column_comes_out():
    srf = _panel()
    assert g.surface_control_points(srf)[1] == (7, 7)
    assert g.surface_control_points(
        g.remove_surface_knot(srf, (50, 25, 2), "u"))[1] == (6, 7)
    assert g.surface_control_points(
        g.remove_surface_knot(srf, (50, 25, 2), "v"))[1] == (7, 6)
    assert g.surface_control_points(
        g.remove_surface_knot(srf, (50, 25, 2), "both"))[1] == (6, 6)


def test_a_row_that_held_nothing_costs_nothing():
    """Rows that insert_surface_knot added carry no shape of their own,
    so taking one out again moves the surface by nothing."""
    srf = _panel()
    out = g.remove_surface_knot(srf, (50, 25, 2), "u")
    assert g.surface_deviation(srf, out) < 1e-6


def test_a_single_span_has_no_row_to_give():
    srf = g.loft([g.make_line((0, 0, 0), (100, 0, 0)),
                  g.make_line((0, 50, 0), (100, 50, 10))])
    with pytest.raises(g.GeometryError, match="single span"):
        g.remove_surface_knot(srf, (50, 25, 2), "u")


def test_held_points_take_their_row_or_column_with_them():
    srf = _panel()
    _, (nu, nv) = g.surface_control_points(srf)
    out, what = g.delete_surface_control_rows(srf, [2 * nv + 0, 2 * nv + 3])
    assert g.surface_control_points(out)[1] == (6, 7) and "row" in what
    out, what = g.delete_surface_control_rows(srf, [1 * nv + 2, 3 * nv + 2])
    assert g.surface_control_points(out)[1] == (7, 6) and "column" in what
    with pytest.raises(g.GeometryError, match="one row or one column"):
        g.delete_surface_control_rows(srf, [0, 2 * nv + 3])


# ------------------------------------------------------------- the app

@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def test_delete_on_held_surface_points_takes_the_row_out(win):
    o = win.scene.add(_panel(), name="Panel")
    _, (nu, nv) = g.surface_control_points(o.shape)
    said = []
    win.processor.ctx.add_echo_listener(said.append)
    win.viewport.cv_enabled.add(o.id)
    win.selection.set_subobjects([(o.id, "cv", 2 * nv + 1),
                                  (o.id, "cv", 2 * nv + 3)])
    win.processor.run("delete")
    assert g.surface_control_points(win.scene.get(o.id).shape)[1] == (6, 7)
    assert any("row" in line and "moved by" in line for line in said), said
    win.processor.run("undo")
    assert g.surface_control_points(win.scene.get(o.id).shape)[1] == (7, 7)


def test_removeknot_takes_surfaces_with_a_direction(win):
    o = win.scene.add(_panel(), name="Panel")
    win.selection.set([o.id])
    win.processor.run("removeknot")
    assert win.processor.busy
    assert "Direction=U" in win.processor.prompt_text()
    assert win.processor.preview_shape("50,25,2") is not None, \
        "the surface as it will be, ghosted"
    win.processor.provide_text("Direction")
    win.processor.provide_text("V")
    win.processor.provide_text("50,25,2")
    assert g.surface_control_points(win.scene.get(o.id).shape)[1] == (7, 6)
    win.processor.provide_text("")
    assert not win.processor.busy


def test_the_edge_row_is_refused_rather_than_a_neighbour_taken():
    """A row on the edge acts at the boundary knot, and "the nearest
    interior knot" to that is the row beside it — which came out under
    the edge row's name."""
    srf = _panel()
    _pts, (nu, nv) = g.surface_control_points(srf)
    with pytest.raises(g.GeometryError, match="edge"):
        g.delete_surface_control_rows(srf, [0])            # first row
    with pytest.raises(g.GeometryError, match="edge"):
        g.delete_surface_control_rows(srf, [(nu - 1) * nv])  # last row
