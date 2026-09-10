"""Ctrl+Shift-clicking a mesh picks a "face"; the view must survive it.

A mesh has faces of a kind — pick_subobject finds the triangle under
the cursor and holds (id, "face", n) — but none the B-rep tools know.
The gumball asked g.faces_of for the push/pull target on every mouse
move, TopExp_Explorer refused the MeshShape with a TypeError, and with
mouseMoveEvent raising on every move the viewport stopped drawing:
the screen went dark. Now the topology walkers hand back nothing for a
mesh, the gumball stays an ordinary gumball, and Delete on the held
"face" says why it cannot rather than deleting the whole mesh.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.core.mesh import MeshShape


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


def _mesh():
    return MeshShape(np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0],
                               [0, 10, 0]], float),
                     np.array([[0, 1, 2], [0, 2, 3]], np.uint32))


def test_the_topology_walkers_hand_back_nothing_for_a_mesh():
    m = _mesh()
    assert g.faces_of(m) == []
    assert g.edges_of(m) == []
    with pytest.raises(g.GeometryError, match="triangles"):
        g.remove_faces(m, [0])


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


def test_moving_the_mouse_with_a_mesh_face_held_does_not_raise(win):
    o = win.scene.add(_mesh(), name="Scan")
    win.selection.set_subobjects([(o.id, "face", 0)])
    vp = win.viewport
    # the gumball hit-tests on every move; this used to raise TypeError
    for x in (100, 200, 300, 400):
        ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(x, 300),
                         Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        vp.mouseMoveEvent(ev)
    vp.gumball.hit_test(200, 300)                       # no exception
    assert vp.gumball._pushpull_target() is None, "an ordinary gumball"


def test_delete_on_a_held_mesh_face_keeps_the_mesh(win):
    o = win.scene.add(_mesh(), name="Scan")
    win.selection.set_subobjects([(o.id, "face", 1)])
    said = []
    win.processor.ctx.add_echo_listener(said.append)
    win.processor.run("delete")
    assert win.scene.get(o.id) is not None, "the mesh is still there"
    assert any("triangles" in line for line in said), said
