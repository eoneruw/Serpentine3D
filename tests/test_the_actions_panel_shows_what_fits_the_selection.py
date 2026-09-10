"""The Actions panel: what you can do to what you have picked, as buttons.

Two hundred commands are in the command line, and the way to find the
one you want was to know its name. The panel reads the selection and
shows the commands that apply, in groups, each button carrying the
command's own description; a search box finds the rest.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.ui import actions_panel as ap


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


def test_every_command_the_table_names_exists_or_is_skipped_quietly():
    from serpentine3d.commands.base import resolve
    named = {name for groups in (ap.NOTHING, ap.CURVES, ap.SURFACES,
                                 ap.SOLIDS, ap.MESHES, ap.POINTCLOUDS,
                                 ap.PICTURES, ap.ANY, ap.EDGES, ap.FACES,
                                 ap.POINTS)
             for _, items in groups for name, _ in items}
    named |= {name for _, _, items in ap.TOGETHER for name, _ in items}
    missing = sorted(n for n in named if resolve(n.split()[0]) is None)
    # a name the build does not have is skipped when drawn, but the
    # table should not drift far from what exists
    assert len(missing) <= 2, missing


def test_nothing_selected_offers_drawing(win):
    panel = win.actions_panel
    shown = panel.visible_commands()
    assert "line" in shown and "box" in shown
    assert "extrude" not in shown


def test_a_curve_offers_surfaces_from_it_and_transforms(win):
    o = win.scene.add(g.make_line((0, 0, 0), (10, 0, 0)), name="L")
    win.selection.set([o.id])
    shown = win.actions_panel.visible_commands()
    assert "extrude" in shown and "loft" in shown and "insertknot" in shown
    assert "move" in shown and "delete" in shown
    assert "booleanunion" not in shown


def test_a_solid_offers_booleans(win):
    o = win.scene.add(g.make_box((0, 0, 0), 5, 5, 5), name="B")
    win.selection.set([o.id])
    shown = win.actions_panel.visible_commands()
    assert "booleanunion" in shown and "filletedge" in shown
    assert "loft" not in shown


def test_a_mixed_selection_shows_both(win):
    a = win.scene.add(g.make_line((0, 0, 0), (10, 0, 0)), name="L")
    b = win.scene.add(g.make_box((0, 0, 0), 5, 5, 5), name="B")
    win.selection.set([a.id, b.id])
    shown = win.actions_panel.visible_commands()
    assert "extrude" in shown and "booleanunion" in shown


def test_a_button_runs_its_command(win):
    win.scene.add(g.make_line((0, 0, 0), (10, 0, 0)), name="L")
    win.actions_panel.buttons["selall"].click()
    assert len(win.selection.ids) == 1


def test_the_tooltip_is_the_commands_own_words(win):
    tip = win.actions_panel.buttons["line"].toolTip()
    assert tip.startswith("line")


def test_search_finds_by_name_or_by_what_it_does(win):
    panel = win.actions_panel
    panel.search.setText("loft")
    assert "loft" in panel.visible_commands()
    panel.search.setText("knot")
    shown = panel.visible_commands()
    assert "insertknot" in shown and "removeknot" in shown
    panel.search.setText("")
    assert "line" in panel.visible_commands(), "back to the context"


def test_the_panel_is_docked_and_named_for_layout_saving(win):
    assert win._actions_dock.objectName() == "actionsDock"


# --------------------------------------------- picked edges, and pairs

def test_picked_edges_bring_their_own_commands(win):
    o = win.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="B")
    win.selection.set_subobjects([(o.id, "edge", 0)])
    shown = win.actions_panel.visible_commands()
    assert "blendsrf" in shown and "dupedge" in shown
    assert "filletedge" in shown
    assert "line" not in shown, "not the nothing-picked list"
    win.selection.set_subobjects([(o.id, "face", 0)])
    shown = win.actions_panel.visible_commands()
    assert "extractsrf" in shown and "pushpull" in shown
    assert "blendsrf" not in shown


def test_a_solid_and_a_surface_together_offer_a_cut(win):
    box = win.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="B")
    srf = win.scene.add(g.loft([g.make_line((-5, -5, 5), (15, -5, 5)),
                                g.make_line((-5, 15, 5), (15, 15, 5))]),
                        name="S")
    win.selection.set([box.id, srf.id])
    shown = win.actions_panel.visible_commands()
    assert "booleansplit" in shown and "trim" in shown
    titles = [t for t, _ in ap.groups_for({"solid", "surface"})]
    assert titles[0] == "Solid & surface", "the pair's group comes first"


def test_two_curves_offer_a_loft_where_one_does_not():
    one = [t for t, _ in ap.groups_for({"curve"}, counts={"curve": 1})]
    two = [t for t, _ in ap.groups_for({"curve"}, counts={"curve": 2})]
    assert "Curves" not in one and "Curves" in two


def test_insert_column_is_the_same_command_with_its_direction_answered(win):
    srf = win.scene.add(g.loft([g.make_line((0, 0, 0), (10, 0, 0)),
                                g.make_line((0, 10, 0), (10, 10, 0))]),
                        name="S")
    win.selection.set([srf.id])
    shown = win.actions_panel.visible_commands()
    assert "insertknot" in shown and "insertknot Direction V" in shown
    assert ap.describe("insertknot Direction V").startswith("insertknot:")


def test_held_control_points_offer_weight(win):
    o = win.scene.add(g.make_line((0, 0, 0), (10, 0, 0)), name="L")
    win.selection.set_subobjects([(o.id, "cv", 0)])
    shown = win.actions_panel.visible_commands()
    assert "removecontrolpoint" in shown
    # weight itself lives on another branch; the panel skips what the
    # build does not have and shows it when it does
    from serpentine3d.commands.base import resolve
    assert ("weight" in shown) == (resolve("weight") is not None)
