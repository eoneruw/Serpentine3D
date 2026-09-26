"""Rows put into a loft bend rather than fold: the degree goes up first.

A loft between two curves is degree 1 across — straight between them.
Rows of control points put into that direction and dragged made
corners, not curves, however far they were dragged, and Weight on
them did nothing across. Now insertknot raises the surface to degree
3 in the direction it is adding rows to (exactly: the surface does
not move), says so once, and there is `changedegree` to do it by
hand on curves and surfaces.
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


def _flat_loft():
    return g.loft([g.make_interp_curve([(0, 0, 0), (50, 10, 0), (100, 0, 0)]),
                   g.make_interp_curve([(0, 0, 80), (50, 30, 80),
                                        (100, 0, 80)])])


def test_a_loft_is_degree_one_across_and_a_row_lifts_it_to_three():
    srf = _flat_loft()
    assert g.surface_degrees(srf) == (2, 1)
    more = g.insert_surface_knot(srf, (50, 15, 40), "v")
    assert g.surface_degrees(more) == (2, 3)
    assert g.surface_deviation(srf, more) < 1e-6, "exact: nothing moved"
    same = g.insert_surface_knot(srf, (50, 15, 40), "u")
    assert g.surface_degrees(same) == (2, 1), "only the direction it adds to"
    both = g.insert_surface_knots_at_spans(srf)
    assert g.surface_degrees(both) == (2, 3), "degree 2 bends already"


def test_a_dragged_row_bends_now():
    """The proof of it: pull the middle row of a degree-3 loft and the
    profile between rows curves; in the degree-1 one it was a corner."""
    srf = g.insert_surface_knot(_flat_loft(), (50, 15, 40), "v")
    pts, (nu, nv) = g.surface_control_points(srf)
    # the middle column (v index) of the middle row (u index)
    i, j = nu // 2, nv // 2
    bent = g.move_surface_control_point(srf, i * nv + j,
                                        (pts[i * nv + j][0],
                                         pts[i * nv + j][1] + 30,
                                         pts[i * nv + j][2]))
    # sample the profile along v at the pulled u and check it is smooth:
    # second differences small relative to first, no single corner
    from OCP.BRep import BRep_Tool
    surf = BRep_Tool.Surface_s(g.faces_of(bent)[0])
    u0, u1, v0, v1 = surf.Bounds()
    u = (u0 + u1) / 2
    ys = [surf.Value(u, v0 + (v1 - v0) * k / 40).Y() for k in range(41)]
    d2 = [abs(ys[k + 1] - 2 * ys[k] + ys[k - 1]) for k in range(1, 40)]
    assert max(d2) < 0.25 * max(abs(ys[k + 1] - ys[k]) for k in range(40))


def test_change_degree_raises_and_refuses_to_lower():
    srf = _flat_loft()
    up = g.change_surface_degree(srf, v=3)
    assert g.surface_degrees(up) == (2, 3)
    assert g.surface_deviation(srf, up) < 1e-6
    with pytest.raises(g.GeometryError, match="only be raised"):
        g.change_surface_degree(up, u=1)
    line = g.make_line((0, 0, 0), (10, 0, 0))
    cubic = g.change_curve_degree(line, 3)
    assert len(g.get_control_points(cubic)) == 4
    with pytest.raises(g.GeometryError):
        g.change_curve_degree(cubic, 1)


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def test_insertknot_says_when_it_raised_the_degree(win):
    o = win.scene.add(_flat_loft(), name="Hood")
    win.selection.set([o.id])
    said = []
    win.processor.ctx.add_echo_listener(said.append)
    proc = win.processor
    proc.run("insertknot")
    proc.provide_text("Direction")
    proc.provide_text("V")
    proc.provide_text("50,15,40")
    assert any("raised to degree 3 in V" in line for line in said), said
    proc.provide_text("")
    assert g.surface_degrees(win.scene.get(o.id).shape) == (2, 3)


def test_changedegree_is_a_command(win):
    o = win.scene.add(_flat_loft(), name="Hood")
    win.selection.set([o.id])
    proc = win.processor
    proc.run("changedegree")
    proc.provide_text("V")
    proc.provide_text("3")
    assert not proc.busy
    assert g.surface_degrees(win.scene.get(o.id).shape) == (2, 3)
