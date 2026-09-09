"""The Osnap bar speaks for every pane, not only the first.

Each Viewport built its own SnapIndex from the config as it started, and
the bar along the bottom talked to the primary's alone. A pane opened by
4view kept the snaps it was born with: switch End off, and a drag in the
Right pane still landed on ends, with nothing on screen saying why. The
panes now share the one index, and Grid snap and Ortho — which live on
the pane — are set on all of them.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


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
    w.processor.run("4view")
    QApplication.processEvents()
    assert len(w.all_viewports()) == 4
    yield w
    w.mark_saved()
    w.close()


def test_every_pane_shares_the_one_snap_index(win):
    first = win.viewport.snaps
    assert all(vp.snaps is first for vp in win.all_viewports())


def test_switching_a_snap_off_reaches_the_right_pane(win):
    bar = win.osnap_bar
    bar._buttons["end"].setChecked(False)
    right = next(vp for vp in win.all_viewports()
                 if vp._view_name == "right")
    assert right.snaps.types["end"] is False


def test_the_master_toggle_reaches_every_pane(win):
    win.osnap_bar._master.setChecked(False)
    assert all(not vp.snaps.enabled for vp in win.all_viewports())


def test_grid_snap_and_ortho_reach_every_pane(win):
    win.osnap_bar._grid.setChecked(True)
    assert all(vp.grid_snap for vp in win.all_viewports())
    win.osnap_bar._ortho.setChecked(True)
    assert all(vp.ortho for vp in win.all_viewports())


def test_a_pane_opened_later_takes_the_current_settings(win):
    win.osnap_bar._buttons["mid"].setChecked(False)
    win.osnap_bar._grid.setChecked(True)
    vp = win.new_viewport_dock()
    assert vp.snaps is win.viewport.snaps
    assert vp.snaps.types["mid"] is False
    assert vp.grid_snap
