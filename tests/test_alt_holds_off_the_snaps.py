"""Hold Alt and the object snaps stand down for that pick or drag.

Dragging a control point in a Right view, the End of something on the far
side of the model sits right under the cursor, and the snap it offers is
the last thing you want. Rhino's answer is Alt: held, the snaps are off
for as long as it is held, without a trip to the Osnap bar. Every snap
lookup the viewport makes goes through one door, so Alt covers point
picks and control-point drags alike.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import Qt
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
    w.resize(900, 600)
    w.show()
    for _ in range(3):
        QApplication.processEvents()
    w._saved_revision = w.scene.revision
    if w.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")
    yield w
    w.mark_saved()
    w.close()


def _with_alt(monkeypatch, held: bool):
    mods = (Qt.KeyboardModifier.AltModifier if held
            else Qt.KeyboardModifier.NoModifier)
    monkeypatch.setattr(QApplication, "queryKeyboardModifiers",
                        staticmethod(lambda: mods))


def _target_pixel(win):
    win.scene.add(g.make_line((60, 0, 0), (60, 40, 0)), name="Target")
    win.processor.run("top")
    win.processor.run("zoomextents")
    vp = win.viewport
    vp.land_flight()
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    vp.snaps.enabled = True
    vp.snaps.types["end"] = True
    s = vp.camera.project(np.array([[60.0, 40.0, 0.0]]),
                          vp.width(), vp.height())
    return float(s[0, 0]) + 4, float(s[0, 1]) - 3       # just off the end


def test_a_pick_lands_on_the_end_without_alt(win, monkeypatch):
    px, py = _target_pixel(win)
    _with_alt(monkeypatch, False)
    pt = win.viewport.world_point_at(px, py)
    assert np.allclose(pt, (60, 40, 0), atol=1e-6)
    assert win.viewport._active_snap is not None


def test_alt_keeps_the_pick_where_the_cursor_is(win, monkeypatch):
    px, py = _target_pixel(win)
    _with_alt(monkeypatch, True)
    pt = win.viewport.world_point_at(px, py)
    assert not np.allclose(pt, (60, 40, 0), atol=1e-3), "it snapped anyway"
    assert np.linalg.norm(np.asarray(pt) - (60, 40, 0)) < 3.0
    assert win.viewport._active_snap is None, "and no marker is offered"


def test_alt_does_not_switch_the_snaps_off_for_good(win, monkeypatch):
    px, py = _target_pixel(win)
    _with_alt(monkeypatch, True)
    win.viewport.world_point_at(px, py)
    _with_alt(monkeypatch, False)
    pt = win.viewport.world_point_at(px, py)
    assert np.allclose(pt, (60, 40, 0), atol=1e-6)
    assert win.viewport.snaps.enabled
