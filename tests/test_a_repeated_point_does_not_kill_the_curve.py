"""A pick landing on the previous point is not a new point.

Drawing an interpolated curve with the snaps on, the same snap taken
twice — or a double-click — put two coincident points in the list, and
OCCT's interpolator failed on them with "Standard_ConstructionError" for
a message: the curve you had been drawing was gone at Enter. Rhino drops
the repeat; so do curve, interpcrv and polyline now, with a word in the
command line, and the interpolator drops one itself for scripts.
"""

from __future__ import annotations

import pytest

from serpentine3d.core import geometry as g


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


def test_the_interpolator_drops_a_repeated_point():
    c = g.make_interp_curve([(0, 0, 0), (10, 5, 0), (10, 5, 0), (20, 0, 0)])
    assert g.curve_length(c) > 20


def test_all_the_same_point_is_still_refused_plainly():
    with pytest.raises(g.GeometryError, match="distinct"):
        g.make_interp_curve([(0, 0, 0), (0, 0, 0)])


@pytest.fixture
def win():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


@pytest.mark.parametrize("cmd", ["interpcrv", "curve", "polyline"])
def test_the_command_survives_the_same_click_twice(win, cmd):
    msgs = []
    win.ctx.add_echo_listener(msgs.append)
    win.processor.run(cmd)
    for p in ("0,0,0", "10,5,0", "10,5,0", "20,0,0"):
        win.processor.provide_text(p)
    win.processor.provide_text("")
    assert not win.processor.busy
    assert [o.kind for o in win.scene.all()] == ["curve"]
    assert not any("cancelled" in m or "failed" in m for m in msgs), msgs
    assert any("Same point" in m for m in msgs)
    assert len(g.get_control_points(win.scene.all()[0].shape)) >= 3
