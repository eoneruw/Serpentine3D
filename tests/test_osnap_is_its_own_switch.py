"""The word Osnap is the switch: click it and snapping pauses.

The bar had a label, "Osnap:", and beside it an "On" button that read
as one more snap type, and the way to pause snapping went unfound.
Now the word is a button: click it and every snap is off, the type
buttons greyed but keeping their settings; click again and it is all
back. Alt still skips the snaps for a single pick.
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
    yield w
    w.mark_saved()
    w.close()


def test_the_osnap_button_pauses_every_snap_and_keeps_the_settings(win):
    bar = win.osnap_bar
    assert bar._master.text() == "Osnap"
    bar._buttons["end"].setChecked(True)
    bar._buttons["mid"].setChecked(True)
    assert win.viewport.snaps.enabled
    bar._master.click()
    assert not win.viewport.snaps.enabled, "paused"
    assert not bar._buttons["end"].isEnabled(), "greyed, not unset"
    assert win.viewport.snaps.types["end"] and win.viewport.snaps.types["mid"]
    bar._master.click()
    assert win.viewport.snaps.enabled
    assert bar._buttons["end"].isEnabled() and bar._buttons["end"].isChecked()
