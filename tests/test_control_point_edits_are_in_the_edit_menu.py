"""Insert, remove and rebuild control points are in the Edit menu.

They were typed-only, next to Control Points On/Off which had menu
entries and keys, so the one way to give a curve or a surface more
handles was to know the command's name.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


def _menu_labels(win, title):
    for act in win.menuBar().actions():
        if act.text().replace("&", "") == title:
            return [a.text() for a in act.menu().actions() if a.text()]
    raise AssertionError(title)


def test_the_edit_menu_offers_the_point_edits():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    labels = _menu_labels(w, "Edit")
    for want in ("Insert Control Point…", "Remove Control Point…",
                 "Rebuild Curve…"):
        assert want in labels, labels
    on = labels.index("Control Points On")
    assert labels.index("Insert Control Point…") > on, "beside the switch"
    w.mark_saved()
    w.close()
