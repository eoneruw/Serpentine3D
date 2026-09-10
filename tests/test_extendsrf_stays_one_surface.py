"""ExtendSrf gives back one surface, not two glued together.

Extending a surface sewed a tangent strip onto it, and the result was a
two-face shell: Points On answered "explode polysurfaces first", the
seam was a hard line to blend or join against, and the strip's handles
could not be pulled with the rest. Now the surface is taken apart into
its Bezier patches, a column of patches is added past the picked edge
along the pole net's last leg, and the lot is put back together as a
single B-spline with the seam knot taken down to one — so the original
is untouched to the last digit and one new row of handles sits beyond
the edge, part of the same net.
"""

import numpy as np
import pytest

from serpentine3d.core import geometry as g


def _bonnet():
    rails = [g.make_interp_curve([(0, y, 0), (50, y, 12), (100, y, 8)])
             for y in (0, 40, 80)]
    return g.loft(rails)


@pytest.mark.parametrize("edge", [0, 1, 2, 3])
def test_every_side_extends_to_a_single_face(edge):
    s = _bonnet()
    out = g.extend_surface(s, edge, 30.0)
    assert len(g.faces_of(out)) == 1
    assert g.surface_control_points(out)[1] in ((4, 3), (3, 4))


def test_the_original_does_not_move():
    s = _bonnet()
    out = g.extend_surface(s, 1, 30.0)
    assert g.surface_deviation(s, out) < 1e-9


def test_it_reaches_about_the_length_asked():
    s = _bonnet()
    out = g.extend_surface(s, 1, 30.0)
    (_lo, hi) = g.bbox(out)
    assert 125.0 < hi[0] < 135.0            # x ran 0..100; ~30 more, sloped


def test_the_new_row_can_be_pulled_like_any_other():
    s = _bonnet()
    out = g.extend_surface(s, 1, 30.0)
    pts, (nu, nv) = g.surface_control_points(out)
    last = (nu - 1) * nv + 1                # a handle on the new row
    moved = g.move_surface_control_point(out, last, (140.0, 40.0, 30.0))
    assert len(g.faces_of(moved)) == 1
    assert g.surface_deviation(s, moved) < 1e-9, "pulling the new row " \
        "must not move the original part"


def test_the_seam_is_smooth_not_a_crease():
    """One knot at the seam: the two are one surface."""
    s = _bonnet()
    out = g.extend_surface(s, 1, 30.0)
    bs, _ = g._face_bspline_surface(out)
    mults = [bs.UMultiplicity(i) for i in range(2, bs.NbUKnots())]
    assert all(m < bs.UDegree() for m in mults), mults


def test_a_flat_loft_extends_too():
    rails = [g.make_polyline([(0, y, 0), (100, y, 8)]) for y in (0, 80)]
    s = g.loft(rails)
    out = g.extend_surface(s, 1, 30.0)
    assert len(g.faces_of(out)) == 1
    (_lo, hi) = g.bbox(out)
    assert hi[0] > 125.0


def test_a_rational_surface_still_gets_the_strip():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    bs, _ = g._face_bspline_surface(_bonnet())
    bs.SetWeight(2, 2, 3.0)
    heavy = BRepBuilderAPI_MakeFace(bs, 1e-6).Face()
    out = g.extend_surface(heavy, 1, 30.0)
    assert len(g.faces_of(out)) == 2        # sewn, as before
