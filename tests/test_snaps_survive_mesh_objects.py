"""Object snaps with a mesh in the scene.

Seen live: a scanned car opened (an STL, a GLB, a USDZ — anything that
arrives as a mesh rather than a BRep), and from then on every mouse move
printed a traceback and nothing could be picked or drawn. The snap
engine asked every visible object for its ends and centres the BRep way,
`shape.ShapeType()`, and a MeshShape has no such thing. Snapping is on by
default, so one mesh was enough to take the whole viewport down.

A small mesh now snaps to its vertices, as Rhino's mesh vertex snap does;
a big one — a scan — offers nothing, because millions of vertices are
nowhere in particular and testing them all on every move is its own way
of making the viewport feel dead.
"""

from __future__ import annotations

import numpy as np

from serpentine3d.core import geometry as g
from serpentine3d.core import snaps as snaps_mod
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from tests.test_pending_snaps import _px, _vp


def _tri():
    return MeshShape(np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], float),
                     np.array([[0, 1, 2]], np.uint32))


def test_a_mesh_in_the_scene_does_not_break_snapping():
    scene = Scene()
    scene.add(_tri(), name="Scan")
    scene.add(g.make_line((0, 0, 0), (0, 0, 5)), name="Post")
    idx = snaps_mod.SnapIndex(scene)
    vp, _ = _vp(scene)
    # the call every mouse move makes; it used to raise AttributeError
    px, py = _px(vp, (10, 0, 0))
    hit = idx.find(vp.camera, px, py, vp.width(), vp.height())
    assert hit is not None and hit[1] == "end"
    assert np.allclose(hit[0], (10, 0, 0)), "and the mesh corner snaps"


def test_a_small_mesh_snaps_to_its_vertices():
    pts = snaps_mod._static_snap_points(_tri())
    assert ((10.0, 0.0, 0.0), "end") in pts
    assert len(pts) == 3


def test_a_scan_sized_mesh_offers_no_snaps():
    n = snaps_mod.MESH_SNAP_VERTEX_LIMIT + 1
    big = MeshShape(np.zeros((n, 3)), np.array([[0, 1, 2]], np.uint32))
    assert snaps_mod._static_snap_points(big) == []
