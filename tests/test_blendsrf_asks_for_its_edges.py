"""BlendSrf picks its edges at a prompt, and makes something across a gap.

Run with nothing picked it used to print an instruction and end, which
in Rhino terms is a command that does nothing: there, BlendSrf asks
for the edges. And with two edges picked that would not take a
tangent blend it raised, so again nothing appeared. Now it prompts
when it has to, and when G1 will not build it steps down to a surface
that at least meets the edges, saying so.
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


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def _two_surfaces_with_a_gap(scene):
    a = scene.add(g.loft([g.make_line((0, -50, 0), (100, -50, 10)),
                          g.make_line((0, 0, 0), (100, 0, 0))]), name="A")
    b = scene.add(g.loft([g.make_line((0, 30, 5), (100, 30, 5)),
                          g.make_line((0, 80, 0), (100, 80, -10))]),
                  name="B")
    return a, b


def _edge_at_y(obj, y):
    for i, e in enumerate(g.edges_of(obj.shape)):
        p0, p1 = g.curve_endpoints(e)
        if abs(p0[1] - y) < 1e-6 and abs(p1[1] - y) < 1e-6:
            return i
    raise AssertionError(f"no edge of {obj.name} at y={y}")


def test_with_edges_picked_first_it_just_builds(win):
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.selection.set_subobjects([(a.id, "edge", _edge_at_y(a, 0)),
                                  (b.id, "edge", _edge_at_y(b, 30))])
    win.processor.run("blendsrf")
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)]
    assert len(made) == 1 and made[0].kind == "surface"
    win.processor.provide_text("")          # Enter keeps the bulge as is
    assert not win.processor.busy
    assert win.selection.ids == [made[0].id], "left holding what it made"
    lo, hi = g.bbox(made[0].shape)
    # a tangent blend bulges a little past its edges; it spans the gap
    assert -5 < lo[1] <= 0.01 and 29.99 <= hi[1] < 35, (lo, hi)


def test_with_nothing_picked_it_asks_and_waits(win):
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.processor.run("blendsrf")
    assert win.processor.busy, "waiting for edges, not over"
    assert "Ctrl+Shift" in win.processor.prompt_text()
    # the picks arrive around the prompt, the way the viewport sends them
    win.selection.toggle_subobject(a.id, "edge", _edge_at_y(a, 0))
    win.selection.toggle_subobject(b.id, "edge", _edge_at_y(b, 30))
    win.processor.provide_text("")          # Enter: the edges are picked
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)]
    assert len(made) == 1, "the blend is there to look at"
    win.processor.provide_text("")          # Enter again keeps it
    assert not win.processor.busy


def test_a_selected_surface_does_not_stand_in_for_the_edges(win):
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.selection.set([a.id, b.id])
    win.processor.run("blendsrf")
    assert win.processor.busy, "surfaces are not edges; it still asks"
    win.processor.provide_text("")
    assert not win.processor.busy
    assert len(win.scene.all()) == 2, "nothing made, and it said so"


def test_edges_that_refuse_a_tangent_blend_still_get_a_surface():
    """Two edges parallel to each other but with the surfaces folded
    back the wrong way: G1 will not build. Something must."""
    a = g.loft([g.make_line((0, 0, 0), (100, 0, 0)),
                g.make_line((0, -50, 0), (100, -50, 0))])
    b = g.loft([g.make_line((0, 0.2, 0), (100, 0.2, 0)),
                g.make_line((0, 0.2, 60), (100, 0.2, 60))])
    ea = g.edges_of(a)[_edge_at_y(type("O", (), {"shape": a, "name": "a"}),
                                  0)]
    eb = next(e for e in g.edges_of(b)
              if all(abs(p[1] - 0.2) < 1e-6 and abs(p[2]) < 1e-6
                     for p in g.curve_endpoints(e)))
    shape, how = g.blend_surfaces_somehow(g.faces_of(a)[0], ea,
                                          g.faces_of(b)[0], eb)
    assert not shape.IsNull()
    assert how == "G1" or "G0" in how or "ruled" in how


# ------------------------------------------------------------- the bulge

def test_the_blend_appears_at_once_and_a_typed_bulge_reshapes_it(win):
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.selection.set_subobjects([(a.id, "edge", _edge_at_y(a, 0)),
                                  (b.id, "edge", _edge_at_y(b, 30))])
    win.processor.run("blendsrf")
    assert win.processor.busy, "the blend is on screen, the bulge is open"
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)]
    assert len(made) == 1
    even = g.bbox(made[0].shape)
    assert ("Bulge", "1") in win.processor.option_chips()
    ghost = win.processor.preview_shape("2")
    assert ghost is not None, "a typed bulge ghosts before it lands"
    win.processor.provide_text("2")
    assert win.processor.busy, "still open for another number"
    fat = g.bbox(win.scene.get(made[0].id).shape)
    assert fat[1][2] > even[1][2] + 1, "more bulge, more belly"
    win.processor.provide_text("0.3")
    taut = g.bbox(win.scene.get(made[0].id).shape)
    assert taut[1][2] < even[1][2]
    win.processor.provide_text("")          # Enter keeps it
    assert not win.processor.busy
    assert win.selection.ids == [made[0].id]
    win.processor.run("undo")
    assert len(win.scene.all()) == 2, "one undo takes the whole blend"


def test_position_continuity_runs_straight_across(win):
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.selection.set_subobjects([(a.id, "edge", _edge_at_y(a, 0)),
                                  (b.id, "edge", _edge_at_y(b, 30))])
    win.processor.run("blendsrf")
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)][0]
    win.processor.provide_text("Continuity=Position")
    lo, hi = g.bbox(win.scene.get(made.id).shape)
    assert lo[2] > -0.01 and hi[2] < 5.01, "no belly: straight between"
    win.processor.provide_text("")
    assert not win.processor.busy


def test_the_bulge_is_a_geometry_call_too():
    a = g.loft([g.make_line((0, -50, 0), (100, -50, 10)),
                g.make_line((0, 0, 0), (100, 0, 0))])
    b = g.loft([g.make_line((0, 30, 5), (100, 30, 5)),
                g.make_line((0, 80, 0), (100, 80, -10))])
    fake = lambda sh: type("O", (), {"shape": sh, "name": "x"})  # noqa: E731
    ea = g.edges_of(a)[_edge_at_y(fake(a), 0)]
    eb = g.edges_of(b)[_edge_at_y(fake(b), 30)]
    fa, fb = g.faces_of(a)[0], g.faces_of(b)[0]
    thin = g.blend_between_edges(fa, ea, fb, eb, bulge=0.3)
    fat = g.blend_between_edges(fa, ea, fb, eb, bulge=2.0)
    assert g.bbox(fat)[1][2] > g.bbox(thin)[1][2]
    with pytest.raises(g.GeometryError):
        g.blend_between_edges(fa, ea, fb, eb, bulge=0)


def test_escape_takes_the_blend_away_again(win):
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.selection.set_subobjects([(a.id, "edge", _edge_at_y(a, 0)),
                                  (b.id, "edge", _edge_at_y(b, 30))])
    win.processor.run("blendsrf")
    assert len(win.scene.all()) == 3
    win.processor.cancel()
    assert len(win.scene.all()) == 2, "cancelled means no blend"


def test_an_edge_of_a_mesh_is_named_as_the_reason(win):
    """Two edges picked, one of them on a mesh: it said "1 picked" and
    nothing else, and two edges were plainly lit. Now it says which
    pick it could not use, and why."""
    from serpentine3d.core.mesh import MeshShape
    import numpy as np
    a, _b = _two_surfaces_with_a_gap(win.scene)
    m = win.scene.add(MeshShape(
        np.array([[0, 40, 0], [100, 40, 0], [0, 90, 0]], float),
        np.array([[0, 1, 2]], np.uint32)), name="Scan")
    said = []
    win.processor.ctx.add_echo_listener(said.append)
    win.selection.set_subobjects([(a.id, "edge", _edge_at_y(a, 0)),
                                  (m.id, "edge", 0)])
    win.processor.run("blendsrf")
    assert "Scan is a mesh" in "\n".join(said), "said before it asks"
    assert win.processor.busy, "and asks for the edge it still needs"
    win.processor.provide_text("")
    assert not win.processor.busy
    assert "1 usable of 2 picked" in "\n".join(said)


def test_the_chips_reshape_the_blend_as_you_drag(win):
    """Bulge is a chip you drag and the blend follows; Continuity flips
    on a click. The history hears the drag once, at its end."""
    from serpentine3d.ui.command_line import ScrubChip
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.selection.set_subobjects([(a.id, "edge", _edge_at_y(a, 0)),
                                  (b.id, "edge", _edge_at_y(b, 30))])
    said = []
    win.processor.ctx.add_echo_listener(said.append)
    win.processor.run("blendsrf")
    QApplication.processEvents()
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)][0]
    even = g.bbox(made.shape)[1][2]
    chips = {c.name: c for c in win.command_line._chips}
    assert isinstance(chips["Bulge"], ScrubChip)
    # a drag, in pieces, the way the mouse sends it
    proc = win.processor
    for v in (1.3, 1.6, 2.0):
        proc.set_option("Bulge", f"{v:g}", quiet=True)
        assert g.bbox(win.scene.get(made.id).shape)[1][2] > even, \
            "the blend follows the drag"
    proc.set_option("Bulge", "2")
    assert said.count("Bulge=2") == 1
    fat = g.bbox(win.scene.get(made.id).shape)[1][2]
    assert fat > even + 1
    chips["Continuity"].click()
    assert proc.option("Continuity", "Tangent") == "Position"
    lo, hi = g.bbox(win.scene.get(made.id).shape)
    assert lo[2] > -0.01 and hi[2] < 5.01, "straight across now"
    proc.provide_text("")
    assert not proc.busy
    assert "bulge 2, position" in said[-1]


def test_a_v_shaped_gap_blends_to_a_point_where_the_edges_meet():
    """Two surfaces that touch at one end and open out at the other:
    the sections at the touching end have no length. It used to refuse
    ("the two edges touch"); now the blend closes on that point."""
    a = g.loft([g.make_line((0, -50, 0), (100, -50, 0)),
                g.make_line((0, 0, 0), (100, 0, 0))])
    b = g.loft([g.make_line((0, 0, 0), (100, 40, 0)),     # meets A at x=0
                g.make_line((0, 50, 0), (100, 90, 0))])
    fa, fb = g.faces_of(a)[0], g.faces_of(b)[0]
    ea = next(e for e in g.edges_of(a)
              if all(abs(p[1]) < 1e-6 for p in g.curve_endpoints(e)))
    eb = next(e for e in g.edges_of(b)
              if any(abs(p[1]) < 1e-6 for p in g.curve_endpoints(e))
              and any(abs(p[1] - 40) < 1e-6 for p in g.curve_endpoints(e)))
    for bulge in (0.5, 1.0, 2.0):
        blend = g.blend_between_edges(fa, ea, fb, eb, bulge=bulge)
        lo, hi = g.bbox(blend)
        assert lo[0] == pytest.approx(0, abs=1e-3), "closes on the apex"
        assert 99 < hi[0] < 110, "reaches the open end, bulge and all"
        assert hi[1] > 30
    ruled = g.blend_between_edges(fa, ea, fb, eb, continuity="G0")
    assert g.surface_area(ruled) == pytest.approx(100 * 40 / 2, rel=0.02)
    with pytest.raises(g.GeometryError, match="lie on each other"):
        g.blend_between_edges(fa, ea, fa, ea)


def test_sections_say_how_many_rows_the_blend_has(win):
    """Fewer sections, fewer rows of control points along the edge to
    pull on; more to hug a wavy edge. A chip you drag, like the bulge."""
    a, b = _two_surfaces_with_a_gap(win.scene)
    win.selection.set_subobjects([(a.id, "edge", _edge_at_y(a, 0)),
                                  (b.id, "edge", _edge_at_y(b, 30))])
    proc = win.processor
    proc.run("blendsrf")
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)][0]
    assert ("Sections", str(g.BLEND_SECTIONS)) in proc.option_chips()
    _, (nu0, nv0) = g.surface_control_points(made.shape)
    proc.set_option("Sections", "4")
    _, (nu1, nv1) = g.surface_control_points(win.scene.get(made.id).shape)
    proc.set_option("Sections", "30")
    _, (nu2, nv2) = g.surface_control_points(win.scene.get(made.id).shape)
    along = lambda nu, nv: max(nu, nv)          # noqa: E731
    assert along(nu1, nv1) < along(nu0, nv0) < along(nu2, nv2)
    assert min(nu1, nv1) == 4, "cubic across the gap, whatever the count"
    proc.provide_text("")
    assert not proc.busy
