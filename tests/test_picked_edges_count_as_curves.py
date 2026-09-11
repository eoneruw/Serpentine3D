"""A Ctrl+Shift-picked surface edge is a curve to the commands that
make surfaces from curves.

Two panels with a gap between them: the natural thing is to pick the
facing edges and say Loft, or draw a curve across and say Sweep 2. Loft
answered "Object type not accepted here" — an edge is not an object —
and the panel offered nothing for the pick. Now the picked edges count
as curves for loft, sweep, edge surface, planar surface, patch, extrude
and revolve; with enough of them held the command just runs; and the
panel offers those commands for the pick.
"""

import numpy as np
import pytest

from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui import actions_panel as ap


def _panel(y0):
    rails = [g.make_interp_curve([(0, y, 0), (50, y, 12), (100, y, 8)])
             for y in (y0, y0 + 40)]
    return g.loft(rails)


def _facing_edge(shape, y):
    """The index of the edge nearest the line y = const."""
    best, best_d = None, None
    for i, e in enumerate(g.edges_of(shape)):
        c = np.asarray(g.centroid(e), float)
        d = abs(c[1] - y)
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best


@pytest.fixture
def two_panels():
    scene = Scene()
    a = scene.add(_panel(0.0), name="A")
    b = scene.add(_panel(80.0), name="B")
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    sel.set_subobjects([(a.id, "edge", _facing_edge(a.shape, 40.0)),
                        (b.id, "edge", _facing_edge(b.shape, 80.0))])
    return scene, sel, proc, echoes, a, b


def test_loft_runs_at_once_between_two_picked_edges(two_panels):
    scene, sel, proc, echoes, a, b = two_panels
    before = len(scene.all())
    proc.run("loft")
    assert not proc.busy, echoes
    assert len(scene.all()) == before + 1
    new = [o for o in scene.all() if o.id not in (a.id, b.id)][0]
    assert new.kind == "surface"
    (lo, hi) = g.bbox(new.shape)
    assert lo[1] > 35.0 and hi[1] < 85.0          # spans the gap only
    assert not any("not accepted" in e for e in echoes), echoes


def test_edgesrf_takes_the_two_edges(two_panels):
    scene, sel, proc, echoes, a, b = two_panels
    before = len(scene.all())
    proc.run("edgesrf")
    assert not proc.busy, echoes
    assert len(scene.all()) == before + 1


def test_sweep2_finds_the_profile_among_two_edges_and_a_curve(two_panels):
    scene, sel, proc, echoes, a, b = two_panels
    ea = g.edges_of(a.shape)[_facing_edge(a.shape, 40.0)]
    eb = g.edges_of(b.shape)[_facing_edge(b.shape, 80.0)]
    pa = g.curve_endpoints(ea)[0]
    pb = min(g.curve_endpoints(eb), key=lambda q: np.linalg.norm(
        np.subtract(q, pa)))
    mid = tuple((np.asarray(pa) + np.asarray(pb)) / 2 + (0, 0, 15.0))
    profile = scene.add(g.make_interp_curve([pa, mid, pb]), name="P")
    sel.set([profile.id])
    sel.set_subobjects([(a.id, "edge", _facing_edge(a.shape, 40.0)),
                        (b.id, "edge", _facing_edge(b.shape, 80.0))])
    before = len(scene.all())
    proc.run("sweep2")
    assert not proc.busy, echoes
    assert len(scene.all()) == before + 1


def test_the_edges_are_still_there_afterwards(two_panels):
    scene, sel, proc, echoes, a, b = two_panels
    proc.run("loft")
    assert scene.get(a.id) is not None and scene.get(b.id) is not None
    assert len(g.edges_of(scene.get(a.id).shape)) == 4


def test_a_command_that_edits_curves_does_not_take_an_edge(two_panels):
    """An edge is not an object of its own to rebuild."""
    scene, sel, proc, echoes, a, b = two_panels
    proc.run("rebuild")
    assert proc.busy or any("needs" in e for e in echoes), echoes
    proc.cancel()


def test_the_panel_offers_surfaces_between_two_picked_edges():
    titles = [t for t, _ in ap.groups_for(set(), {"edge"}, {}, {"edge": 2})]
    assert "Between the picked edges" in titles
    titles = [t for t, _ in ap.groups_for(set(), {"edge"}, {}, {"edge": 1})]
    assert "Between the picked edges" not in titles
    titles = [t for t, _ in ap.groups_for({"curve"}, {"edge"}, {"curve": 1},
                                          {"edge": 1})]
    assert "Between the picked edges" in titles          # an edge + a curve
