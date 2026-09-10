"""The row InsertKnot adds lands where you pointed.

The yellow line under the cursor was the isocurve at the picked spot, and
the knot went in there — but a knot at u is not a control point at u. A
pole acts at its Greville abscissa, the mean of the `degree` knots after
it, so the new row of handles came up to one side of the line, and on a
bonnet a long way to one side. Rhino's InsertControlPoint puts the knot
where the handle will be under the cursor; so does this now, and the
ghost is the row of handles that will appear rather than the line.
"""

import numpy as np

from serpentine3d.core import geometry as g


def _curved():
    rails = [g.make_interp_curve([(0, y, 0), (50, y, 12), (100, y, 8)])
             for y in (0, 40, 80)]
    return g.loft(rails)


def _rows_x(shape):
    pts, (nu, nv) = g.surface_control_points(shape)
    grid = np.asarray(pts).reshape(nu, nv, 3)
    return [float(grid[i, :, 0].mean()) for i in range(nu)]


def test_the_new_row_sits_under_the_pick():
    s = _curved()
    for x in (20.0, 50.0, 70.0, 90.0):
        new = g.insert_surface_knot(s, (x, 40.0, 10.0), "u")
        nearest = min(_rows_x(new), key=lambda r: abs(r - x))
        assert abs(nearest - x) < 1.5, (x, _rows_x(new))


def test_the_surface_itself_does_not_move():
    s = _curved()
    new = g.insert_surface_knot(s, (70.0, 40.0, 10.0), "u")
    assert g.surface_deviation(s, new) < 1e-6


def test_a_degree_one_loft_gets_its_row_where_picked_too():
    rails = [g.make_polyline([(0, y, 0), (100, y, 8)]) for y in (0, 80)]
    s = g.loft(rails)
    new = g.insert_surface_knot(s, (70.0, 30.0, 5.0), "u")
    assert g.surface_degrees(new)[0] == 3           # lifted so it bends
    assert min(abs(r - 70.0) for r in _rows_x(new)) < 0.5


def test_the_knot_solver_lands_a_pole_at_the_parameter():
    flat = [0, 0, 0, 0, 1, 1, 1, 1]                # one cubic span
    for gv in (0.1, 0.4, 0.5, 0.75, 0.95):
        t = g._knot_for_greville(flat, 3, gv)
        assert 0 < t < 1
        after = sorted(flat + [t])
        grevilles = [sum(after[i + 1:i + 4]) / 3 for i in range(len(after) - 4)]
        assert min(abs(a - gv) for a in grevilles) < 1e-9, (gv, t, grevilles)


def test_the_ghost_is_the_row_of_handles():
    s = _curved()
    lines = g.new_control_rows_at(s, (70.0, 40.0, 10.0), "u")
    assert len(lines) == 1
    pts = np.asarray(g.get_control_points(lines[0]))
    assert len(pts) == 3                            # one handle per v row
    assert abs(pts[:, 0].mean() - 70.0) < 1.5
    both = g.new_control_rows_at(s, (70.0, 40.0, 10.0), "both")
    assert len(both) == 2
