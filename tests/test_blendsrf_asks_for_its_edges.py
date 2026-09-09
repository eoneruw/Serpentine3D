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
    assert not win.processor.busy
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)]
    assert len(made) == 1 and made[0].kind == "surface"
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
    win.processor.provide_text("")          # Enter
    assert not win.processor.busy
    made = [o for o in win.scene.all() if o.id not in (a.id, b.id)]
    assert len(made) == 1


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
