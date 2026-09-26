"""Selecting by kind, and filtering what a click can pick, from the UI.

Both existed only as typed commands: `selcrv` and friends, and
`selfilter`, which restricts viewport picking to one kind. Neither could
be found without knowing the name. Now the Edit menu has a Select by
Type submenu, and the status bar carries the filter as a row of buttons
— Pt Crv Srf Sld Msh Cld — that light up for the kinds a click may pick.
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
    w.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="Box")
    w.scene.add(g.make_line((0, 0, 0), (20, 0, 0)), name="Line")
    yield w
    w.mark_saved()
    w.close()


def _menu(win, *path):
    menu = win.menuBar()
    for title in path:
        for act in menu.actions():
            if act.text().replace("&", "") == title:
                menu = act.menu() if act.menu() is not None else act
                break
        else:
            raise AssertionError(f"no menu item {title!r} in {path}")
    return menu


# ---------------------------------------------------------------- the menu

def test_edit_has_a_select_by_type_submenu(win):
    sub = _menu(win, "Edit", "Select by Type")
    labels = [a.text() for a in sub.actions() if a.text()]
    for want in ("Points", "Curves", "Surfaces", "Solids", "Meshes"):
        assert want in labels


def test_the_menu_selects_only_that_kind(win):
    _menu(win, "Edit", "Select by Type", "Curves").trigger()
    picked = [win.scene.get(i).kind for i in win.selection.ids]
    assert picked == ["curve"]
    _menu(win, "Edit", "Select by Type", "Solids").trigger()
    picked = [win.scene.get(i).kind for i in win.selection.ids]
    assert picked == ["solid"]


def test_selmesh_is_a_command_now():
    from serpentine3d.commands.base import resolve
    assert resolve("selmesh") is not None
    assert resolve("selmeshes").name == "selmesh"


# ----------------------------------------------------------- the filter bar

def test_the_status_bar_carries_the_filter(win):
    bar = win.filter_bar
    assert bar.parent() is not None, "it is somewhere in the window"
    assert set(bar.buttons) >= {"point", "curve", "surface", "solid",
                                "mesh", "pointcloud"}
    assert not bar.lit_kinds(), "off to begin with"
    assert not win.selection.filter_active


def test_lighting_a_kind_filters_what_a_click_can_pick(win):
    bar = win.filter_bar
    bar.buttons["curve"].setChecked(True)
    assert win.selection.filter_active
    assert win.selection.filter_kinds == {"curve"}
    assert win.selection.filter_allows("curve")
    assert not win.selection.filter_allows("solid")
    bar.buttons["solid"].setChecked(True)
    assert win.selection.filter_kinds == {"curve", "solid"}
    bar.buttons["curve"].setChecked(False)
    bar.buttons["solid"].setChecked(False)
    assert not win.selection.filter_active, "no kinds lit means anything"
    assert win.selection.filter_allows("surface")


def test_the_buttons_follow_the_typed_command(win):
    win.selection.filter_kinds = {"surface"}
    win.selection.filter_active = True
    win._update_status()
    assert win.filter_bar.lit_kinds() == {"surface"}
    win.selection.filter_active = False        # paused with `sft`
    win._update_status()
    assert win.filter_bar.lit_kinds() == set()


def test_a_lit_filter_shows_in_the_status_text(win):
    win.filter_bar.buttons["curve"].setChecked(True)
    assert "filter: curve" in win.statusBar().currentMessage()
