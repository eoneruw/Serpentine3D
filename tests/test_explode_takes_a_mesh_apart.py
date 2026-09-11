"""Explode on a mesh gives its connected pieces.

It raised AttributeError: 'MeshShape' object has no attribute
'ShapeType' — the topology walker asked a mesh what OCCT shape it was —
and the command was cancelled. A scan of a car is one mesh of many
parts, and each is wanted on its own, so a mesh comes apart at the
gaps between its pieces; one piece stays one.
"""

import time

import numpy as np

from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def _quad(x0):
    v = np.array([[x0, 0, 0], [x0 + 1, 0, 0], [x0 + 1, 1, 0], [x0, 1, 0]],
                 float)
    t = np.array([[0, 1, 2], [0, 2, 3]], np.uint32)
    return v, t


def _two_quads():
    v1, t1 = _quad(0.0)
    v2, t2 = _quad(5.0)
    return MeshShape(np.vstack([v1, v2]), np.vstack([t1, t2 + 4]))


def test_two_separate_quads_come_apart():
    parts = g.explode(_two_quads())
    assert len(parts) == 2
    assert all(isinstance(p, MeshShape) for p in parts)
    assert sorted(len(p.triangles) for p in parts) == [2, 2]
    assert all(len(p.vertices) == 4 for p in parts)        # vertices remapped


def test_one_piece_stays_one():
    v, t = _quad(0.0)
    assert len(g.explode(MeshShape(v, t))) == 1


def test_the_command_explodes_a_mesh():
    scene = Scene()
    obj = scene.add(_two_quads(), name="Scan")
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    sel.set([obj.id])
    proc.run("explode")
    assert not proc.busy
    assert scene.get(obj.id) is None
    assert len([o for o in scene.all() if o.kind == "mesh"]) == 2
    assert any("Exploded into 2" in e for e in echoes), echoes


def test_a_big_mesh_comes_apart_in_a_moment():
    n = 300                                     # 300 separate quads
    vs, ts = [], []
    for i in range(n):
        v, t = _quad(float(i * 3))
        vs.append(v)
        ts.append(t + 4 * i)
    big = MeshShape(np.vstack(vs), np.vstack(ts))
    t0 = time.perf_counter()
    parts = big.pieces()
    assert len(parts) == n
    assert time.perf_counter() - t0 < 5.0
