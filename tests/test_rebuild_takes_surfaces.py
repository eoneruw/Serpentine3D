"""Rebuild works on surfaces: a count each way, a degree, and how far
the new surface strays from the old.

A MergeSrf fit, or an import, can come with a net of hundreds of
handles, which is no net to pull on. Rhino's Rebuild fixes that on
surfaces as well as curves; ours only took curves.
"""

from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def _bonnet():
    rails = [g.make_interp_curve([(0, y, 0), (50, y, 12), (100, y, 8)])
             for y in (0, 40, 80)]
    return g.loft(rails)


def test_the_count_asked_for_is_the_count_given():
    face, dev = g.rebuild_surface(_bonnet(), 6, 5)
    assert g.surface_control_points(face)[1] == (6, 5)
    assert g.surface_degrees(face) == (3, 3)
    assert dev < 0.1


def test_a_dense_surface_comes_down_to_a_net():
    a = _bonnet()
    bs, _ = g._face_bspline_surface(a)
    for k in range(1, 12):
        bs.InsertUKnot(k / 12.0, 1, 1e-9)
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    dense = BRepBuilderAPI_MakeFace(bs, 1e-6).Face()
    assert g.surface_control_points(dense)[1][0] > 10
    face, dev = g.rebuild_surface(dense, 5, 4)
    assert g.surface_control_points(face)[1] == (5, 4)
    assert dev < 0.1


def test_the_command_takes_a_surface():
    scene = Scene()
    o = scene.add(_bonnet(), name="Hood")
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    sel.set([o.id])
    proc.run("rebuild")
    proc.provide_text("7")
    proc.provide_text("5")
    proc.provide_text("3")
    assert not proc.busy
    assert g.surface_control_points(scene.get(o.id).shape)[1] == (7, 5)
    assert any("within" in e for e in echoes), echoes
