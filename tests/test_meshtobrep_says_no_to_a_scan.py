"""To Surfaces on a scan was a beach ball.

The run log: a click on To Surfaces for a scanned panel, then the stall
dump inside brep_from_mesh, a face per triangle. It asks above five
thousand triangles and refuses above fifty thousand, with a word about
what a scan wants instead.
"""

import numpy as np

from serpentine3d.commands import organize
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core.history import History
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def _grid_mesh(n: int) -> MeshShape:
    """A flat n×n grid of quads: 2·n² triangles."""
    xs, ys = np.meshgrid(np.arange(n + 1), np.arange(n + 1))
    v = np.stack([xs.ravel(), ys.ravel(), np.zeros((n + 1) ** 2)], 1)
    tris = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            tris.append([a, a + 1, a + n + 2])
            tris.append([a, a + n + 2, a + n + 1])
    return MeshShape(v.astype(float), np.array(tris, np.uint32))


def _run(mesh, *answers):
    scene = Scene()
    o = scene.add(mesh, name="Scan")
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    sel.set([o.id])
    proc.run("meshtobrep")
    for a in answers:
        proc.provide_text(a)
    return scene, o, proc, echoes


def test_a_small_mesh_converts_without_a_word():
    scene, o, proc, echoes = _run(_grid_mesh(3))
    assert not proc.busy
    assert scene.get(o.id).kind != "mesh"


def test_a_big_mesh_asks_first_and_no_is_no(monkeypatch):
    monkeypatch.setattr(organize, "MESHTOBREP_ASK", 10)
    scene, o, proc, echoes = _run(_grid_mesh(4))          # 32 triangles
    assert proc.busy, "it should have asked"
    proc.provide_text("No")
    assert not proc.busy
    assert scene.get(o.id).kind == "mesh"
    assert any("Nothing converted" in e for e in echoes), echoes


def test_a_scan_is_refused_with_a_reason(monkeypatch):
    monkeypatch.setattr(organize, "MESHTOBREP_ASK", 10)
    monkeypatch.setattr(organize, "MESHTOBREP_REFUSE", 20)
    scene, o, proc, echoes = _run(_grid_mesh(4))
    assert not proc.busy
    assert scene.get(o.id).kind == "mesh"
    assert any("face per triangle" in e for e in echoes), echoes
