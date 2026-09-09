"""A curved face turns no more than a few degrees between mesh vertices.

The analysis modes read the normal between vertices, so every facet of a
coarse mesh shows as a kink in the zebra stripes. Twenty degrees per
facet (the old angular deflection) put forty segments round a sphere and
a visible wobble in every ring; 0.15 rad is under nine.
"""

from __future__ import annotations

import numpy as np

from serpentine3d.core import geometry as g
from serpentine3d.core import tessellate as T


def test_the_angular_deflection_is_under_nine_degrees():
    assert T.ANGULAR_DEFLECTION <= np.radians(9.0)


def test_a_sphere_turns_gently_between_neighbouring_vertices():
    dm = T.tessellate(g.make_sphere((0, 0, 0), 50))
    v = dm.vertices / np.linalg.norm(dm.vertices, axis=1, keepdims=True)
    tris = dm.triangles
    worst = 0.0
    for a, b in ((0, 1), (1, 2), (2, 0)):
        cos = np.clip((v[tris[:, a]] * v[tris[:, b]]).sum(1), -1, 1)
        worst = max(worst, float(np.degrees(np.arccos(cos)).max()))
    # the pole fans turn more than the setting says; twenty was the old
    assert worst < 15.0, f"an edge turns {worst:.1f} degrees"


def test_a_box_is_not_made_heavier_for_it():
    dm = T.tessellate(g.make_box((0, 0, 0), 10, 10, 10))
    assert len(dm.triangles) == 12
