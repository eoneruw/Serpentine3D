"""A surface made from a painted surface is painted the same.

Offset a red car-paint panel and the offset came out in the layer's
grey; blend two painted panels and the blend was grey; explode, split
or trim a painted polysurface and the pieces lost the paint. The
layer carried over, the colour and material did not. Every command
that makes a surface from an existing one now adds it with the
scene's add_from, which carries layer, colour, material, annotation
and group across.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g

PAINT = {"metallic": 0.6, "roughness": 0.3, "color": (0.8, 0.05, 0.05)}
RED = (0.8, 0.05, 0.05)


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


def _painted(win, shape, name):
    o = win.scene.add(shape, name=name)
    return win.scene.update(o.id, color=RED, material=dict(PAINT))


def _others(win, *ids):
    return [o for o in win.scene.all() if o.id not in ids]


def _assert_painted(objs):
    assert objs, "something was made"
    for o in objs:
        assert o.color == RED, o.name
        assert o.material == PAINT, o.name


def test_offsetsrf_keeps_the_paint(win):
    a = _painted(win, g.loft([g.make_line((0, 0, 0), (100, 0, 0)),
                              g.make_line((0, 50, 0), (100, 50, 10))]), "A")
    win.selection.set([a.id])
    win.processor.run("offsetsrf")
    win.processor.provide_text("5")
    if win.processor.busy:
        win.processor.provide_text("")
    _assert_painted(_others(win, a.id))


def test_blendsrf_takes_the_first_surfaces_paint(win):
    a = _painted(win, g.loft([g.make_line((0, -50, 0), (100, -50, 10)),
                              g.make_line((0, 0, 0), (100, 0, 0))]), "A")
    b = win.scene.add(g.loft([g.make_line((0, 30, 5), (100, 30, 5)),
                              g.make_line((0, 80, 0), (100, 80, -10))]),
                      name="B")

    def edge_at(o, y):
        for i, e in enumerate(g.edges_of(o.shape)):
            p0, p1 = g.curve_endpoints(e)
            if abs(p0[1] - y) < 1e-6 and abs(p1[1] - y) < 1e-6:
                return i
    win.selection.set_subobjects([(a.id, "edge", edge_at(a, 0)),
                                  (b.id, "edge", edge_at(b, 30))])
    win.processor.run("blendsrf")
    while win.processor.busy:
        win.processor.provide_text("")
    _assert_painted(_others(win, a.id, b.id))


def test_explode_and_split_keep_the_paint(win):
    box = _painted(win, g.make_box((0, 0, 0), 20, 20, 20), "Box")
    win.selection.set([box.id])
    win.processor.run("explode")
    faces = _others(win)
    assert len(faces) == 6
    _assert_painted(faces)


def test_extractsrf_keeps_the_paint(win):
    box = _painted(win, g.make_box((0, 0, 0), 20, 20, 20), "Box")
    win.selection.set_subobjects([(box.id, "face", 0)])
    win.processor.run("extractsrf")
    while win.processor.busy:
        win.processor.provide_text("")
    pulled = [o for o in win.scene.all() if o.kind == "surface"]
    _assert_painted(pulled)
