"""MergeSrf: two surfaces that share an edge become one net of handles.

Extend, blend, join — every one of them left the model as pieces, and
pieces cannot be pulled together: Points On on the joined thing said
"explode polysurfaces first", and after exploding, a handle on one
piece moved that piece alone and opened the seam. Rhino has MergeSrf
for this. Where the two are really one surface cut in two (a surface
and the strip an older ExtendSrf sewed onto it) they go back together
exactly; otherwise one surface is fitted through both and the command
says how far it strays.
"""

import numpy as np
import pytest

from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def _bonnet():
    rails = [g.make_interp_curve([(0, y, 0), (50, y, 12), (100, y, z)])
             for y, z in ((0, 8), (40, 12), (80, 8))]
    return g.loft(rails)


def _continuation(a, fractions=(0.0, 0.5, 1.0)):
    """A second surface whose near edge is the bonnet's far edge."""
    bs, _ = g._face_bspline_surface(a)
    u0, u1, v0, v1 = bs.Bounds()
    starts = [bs.Value(u1, v0 + (v1 - v0) * f) for f in fractions]
    rails = [g.make_interp_curve([(p.X(), p.Y(), p.Z()),
                                  (130.0, p.Y(), 4.0), (160.0, p.Y(), -5.0)])
             for p in starts]
    return g.loft(rails)


def test_a_sewn_extension_goes_back_together_exactly():
    a = _bonnet()
    old = g._extend_surface_sewn(a, 1, 30.0)
    fa, fb = g.faces_of(old)
    face, exact, dev = g.merge_surfaces(fa, fb)
    assert exact
    assert len(g.faces_of(face)) == 1
    assert g.surface_control_points(face)[1] == (4, 3)     # one smooth net
    # the strip was a unit-length one, not quite tangent in parameter, so
    # making the seam one knot gives a hair; a hair is all it gives
    assert dev < 0.5 and g.surface_deviation(a, face) < 0.5


def test_order_does_not_matter():
    a = _bonnet()
    fa, fb = g.faces_of(g._extend_surface_sewn(a, 1, 30.0))
    one = g.merge_surfaces(fa, fb)[0]
    other = g.merge_surfaces(fb, fa)[0]
    assert g.surface_deviation(one, other) < 1e-9


def test_two_surfaces_that_merely_meet_are_fitted_and_measured():
    a = _bonnet()
    b = _continuation(a, (0.0, 0.3, 1.0))      # same edge, other parameters
    face, exact, dev = g.merge_surfaces(a, b)
    assert not exact
    assert len(g.faces_of(face)) == 1
    assert dev < 0.2                            # said, and small
    assert g.surface_deviation(a, face) < 0.2
    assert g.surface_deviation(b, face) < 0.2


def test_surfaces_apart_are_refused():
    a = _bonnet()
    far = g.translate(a, (0.0, 500.0, 0.0))
    with pytest.raises(g.GeometryError):
        g.merge_surfaces(a, far)


def test_no_smooth_keeps_the_seam():
    a = _bonnet()
    fa, fb = g.faces_of(g._extend_surface_sewn(a, 1, 30.0))
    face, exact, _dev = g.merge_surfaces(fa, fb, smooth=False)
    assert exact
    assert g.surface_control_points(face)[1] == (5, 3)     # seam kept


def test_a_weighted_surface_is_fitted_not_refused():
    """A Weight edit makes a surface rational, and the exact assembly
    cannot carry weights: "CompBezierSurfacesToBSpl : rational !" was
    the whole of the command's answer. Such a pair is fitted."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    a = _bonnet()
    bs, _ = g._face_bspline_surface(a)
    bs.SetWeight(2, 2, 2.5)
    heavy = BRepBuilderAPI_MakeFace(bs, 1e-6).Face()
    b = _continuation(heavy)
    face, exact, dev = g.merge_surfaces(heavy, b)
    assert not exact
    assert len(g.faces_of(face)) == 1
    assert dev < 0.2


# -- the command --

def _run(scene, text, *answers):
    ctx = CommandContext(scene, SelectionManager(scene), History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    proc.run(text)
    for a in answers:
        proc.provide_text(a)
    return ctx, proc, echoes


def test_the_command_takes_a_two_face_polysurface():
    scene = Scene()
    a = _bonnet()
    obj = scene.add(g._extend_surface_sewn(a, 1, 30.0), name="Hood")
    scene_sel = SelectionManager(scene)
    ctx = CommandContext(scene, scene_sel, History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    scene_sel.set([obj.id])
    proc.run("mergesrf")
    proc.provide_text("Yes")
    assert not proc.busy
    assert len(g.faces_of(scene.get(obj.id).shape)) == 1
    assert any("exactly" in e for e in echoes), echoes


def test_the_command_takes_two_surfaces_and_leaves_one():
    scene = Scene()
    a = scene.add(_bonnet(), name="A")
    b = scene.add(_continuation(scene.get(a.id).shape), name="B")
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    sel.set([a.id, b.id])
    proc.run("mergesrf")
    proc.provide_text("Yes")
    assert not proc.busy
    assert scene.get(b.id) is None
    assert len(g.faces_of(scene.get(a.id).shape)) == 1
    assert sel.ids == [a.id]
    assert any("Merged into one surface" in e for e in echoes), echoes
