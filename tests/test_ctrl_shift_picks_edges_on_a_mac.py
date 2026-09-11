"""Ctrl+Shift-click picks an edge with the key marked Control, on a Mac.

Every doc says Ctrl+Shift-click an edge or a face. On a Mac, Qt hands
the Command key over as Control and the key actually marked Control as
Meta — and turns Ctrl+click into a right click before it reaches the
viewport at all. So someone doing exactly what the README says sent a
right click with Meta+Shift, which the viewport took for a plain right
click: Enter. Nothing picked, nothing said.

Now the chord is the same chord whichever key you reach for: Meta
counts as Ctrl, and the right click macOS fabricates from Ctrl+click
carries the pick when Shift is down with it.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.ui.viewport import subobject_chord

M = Qt.KeyboardModifier


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


def test_either_key_a_mac_has_for_ctrl_makes_the_chord():
    assert subobject_chord(M.ControlModifier | M.ShiftModifier)
    assert subobject_chord(M.MetaModifier | M.ShiftModifier)
    assert not subobject_chord(M.ShiftModifier)
    assert not subobject_chord(M.MetaModifier)
    assert not subobject_chord(M.NoModifier)


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


def _box_edge_on_screen(win):
    """A box, seen from the front, and a screen point on its top edge."""
    vp = win.viewport
    obj = win.scene.add(g.make_box((0, 0, 0), 20, 20, 20), name="Box")
    win.processor.run("front")
    win.processor.run("zoomextents")
    vp.land_flight()
    for _ in range(3):
        QApplication.processEvents()
    on_edge = np.array([[10.0, 0.0, 20.0]])
    px, py = vp.camera.project(on_edge, vp.width(), vp.height())[0][:2]
    assert vp.pick_subobject(px, py) is not None, "the edge is under it"
    return obj, QPointF(float(px), float(py))


def _click(vp, at, button, mods):
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonPress, at, button, button, mods))
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonRelease, at, button, Qt.MouseButton.NoButton,
        mods))


def test_meta_shift_click_picks_the_edge(win):
    obj, at = _box_edge_on_screen(win)
    _click(win.viewport, at, Qt.MouseButton.LeftButton,
           M.MetaModifier | M.ShiftModifier)
    subs = win.selection.subobjects
    assert len(subs) == 1 and subs[0][0] == obj.id and subs[0][1] == "edge"
    assert not win.selection.ids, "the edge, not the box"


def test_the_right_click_macos_makes_of_ctrl_click_picks_too(win):
    obj, at = _box_edge_on_screen(win)
    fired = []
    win.viewport.enterShortcut.connect(lambda: fired.append(1))
    _click(win.viewport, at, Qt.MouseButton.RightButton,
           M.MetaModifier | M.ShiftModifier)
    subs = win.selection.subobjects
    assert len(subs) == 1 and subs[0][1] == "edge"
    assert not fired, "a pick, not an Enter"
    # and again takes it back out
    _click(win.viewport, at, Qt.MouseButton.RightButton,
           M.MetaModifier | M.ShiftModifier)
    assert not win.selection.subobjects


def test_a_plain_right_click_is_still_enter(win):
    _box_edge_on_screen(win)
    fired = []
    win.viewport.enterShortcut.connect(lambda: fired.append(1))
    _click(win.viewport, QPointF(30.0, 30.0), Qt.MouseButton.RightButton,
           M.NoModifier)
    assert fired and not win.selection.subobjects


def test_the_marked_control_key_works_for_every_ctrl_gesture():
    """Ctrl+Shift picks were taught about the Mac's two keys; Ctrl-click
    deselect, the Ctrl nudge and the drag chords still read only the
    one Qt calls Control. One constant, everywhere."""
    from PySide6.QtCore import Qt
    from serpentine3d.ui import gumball, viewport
    assert viewport.CTRL_KEYS is gumball.CTRL_KEYS
    meta = Qt.KeyboardModifier.MetaModifier
    assert gumball._ctrl_held(meta)
    assert gumball._ctrl_held(Qt.KeyboardModifier.ControlModifier)
    assert not gumball._ctrl_held(Qt.KeyboardModifier.ShiftModifier)


def test_a_meta_click_takes_an_object_out_of_the_selection(win):
    from PySide6.QtCore import Qt
    from serpentine3d.core import geometry as g
    a = win.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="A")
    b = win.scene.add(g.make_box((20, 0, 0), 10, 10, 10), name="B")
    win.selection.set([a.id, b.id])
    win._on_object_clicked(b.id, Qt.KeyboardModifier.MetaModifier)
    assert win.selection.ids == [a.id]
