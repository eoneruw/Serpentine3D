"""A held edge on a plain surface leaves the gumball an ordinary gumball.

Ctrl+Shift-click an edge and the gumball becomes a fillet handle — on a
solid, where the edge sits between two faces to round between. On a
surface the border edge has one face, and dragging the handle asked
OCCT to fillet it anyway: Standard_Failure ("no suitable edges") from
inside mouseMoveEvent, once per pixel, a hundred and fifty times in
one drag. Now the handle is offered only for an edge two faces share,
and fillet_edges turns OCCT's raise into a GeometryError the gumball
already knows to swallow.
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


def _sheet():
    return g.loft([g.make_line((0, 0, 0), (100, 0, 0)),
                   g.make_line((0, 50, 0), (100, 50, 10))])


def test_a_border_edge_is_not_shared_and_a_box_edge_is():
    sheet = _sheet()
    assert len(g.edge_faces(sheet, 0)) < 2
    box = g.make_box((0, 0, 0), 10, 10, 10)
    assert len(g.edge_faces(box, 0)) == 2


def test_filleting_a_border_edge_is_a_geometry_error_not_a_crash():
    sheet = _sheet()
    with pytest.raises(g.GeometryError):
        g.fillet_edges(sheet, 2.0, edges=[g.edges_of(sheet)[0]])


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w.resize(900, 600)
    w.show()
    for _ in range(3):
        QApplication.processEvents()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def test_the_gumball_offers_no_fillet_handle_on_a_surface_edge(win):
    o = win.scene.add(_sheet(), name="Sheet")
    win.selection.set_subobjects([(o.id, "edge", 0)])
    gb = win.viewport.gumball
    assert gb._fillet_target() is None
    assert not gb._fillet_mode()
    box = win.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="Box")
    win.selection.set_subobjects([(box.id, "edge", 0)])
    assert gb._fillet_target() is not None, "a solid's edge still fillets"
