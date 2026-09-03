"""Colour and material from the Properties panel, for everything selected.

Seen live: two body panels shift-picked, and the Properties panel said
"2 objects selected" and greyed out every row, so there was no way to
colour them together. And there was nowhere in the panel to give a
surface a look at all — only the `material` command, which nobody finds
by looking. The name and the measurement belong to one thing; a colour
and a material are what you give a group, so those two rows stay live
for a multi-selection and act on all of it. The new Material row offers
the same presets the command does.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.commands.edit import _MATERIAL_PRESETS
from serpentine3d.core import geometry as g


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.mark_saved()
    w.close()


def _two(win):
    a = win.scene.add(g.make_box((0, 0, 0), 5, 5, 5), name="Door")
    b = win.scene.add(g.make_sphere((20, 0, 0), 3), name="Mirror")
    win.selection.set([a.id, b.id])
    QApplication.processEvents()
    return a, b


def test_two_selected_can_be_coloured_together(win):
    a, b = _two(win)
    panel = win.properties
    assert panel.header.text() == "2 objects selected"
    assert panel.color_widget.isEnabled()
    panel._set_color((0.9, 0.1, 0.1))
    assert tuple(win.scene.get(a.id).color) == pytest.approx((0.9, 0.1, 0.1))
    assert tuple(win.scene.get(b.id).color) == pytest.approx((0.9, 0.1, 0.1))
    assert not panel.name_edit.isEnabled(), "a name is still one thing's"


def test_by_layer_clears_every_override_in_the_selection(win):
    a, b = _two(win)
    win.scene.update_many([a.id, b.id], color=(0.2, 0.2, 0.9))
    win.properties.refresh()
    assert win.properties.color_reset.isEnabled()
    win.properties._reset_color()
    assert win.scene.get(a.id).color is None
    assert win.scene.get(b.id).color is None


def test_the_material_row_offers_the_presets(win):
    combo = win.properties.material_combo
    names = [combo.itemData(i) for i in range(combo.count())]
    for preset in _MATERIAL_PRESETS:
        assert preset in names
    assert None in names and "Custom" in names


def test_picking_glass_applies_it_to_the_selection(win):
    a, b = _two(win)
    combo = win.properties.material_combo
    assert combo.isEnabled()
    combo.setCurrentIndex(combo.findData("Glass"))
    assert win.scene.get(a.id).material == _MATERIAL_PRESETS["Glass"]
    assert win.scene.get(b.id).material == _MATERIAL_PRESETS["Glass"]
    combo.setCurrentIndex(combo.findData(None))
    assert win.scene.get(a.id).material is None


def test_the_row_shows_what_one_object_has(win):
    a = win.scene.add(g.make_box((0, 0, 0), 5, 5, 5), name="Door")
    a.material = dict(_MATERIAL_PRESETS["Metal"])
    win.selection.set([a.id])
    QApplication.processEvents()
    win.properties.refresh()
    combo = win.properties.material_combo
    assert combo.currentData() == "Metal"


def test_a_disagreeing_selection_shows_no_preset(win):
    a, b = _two(win)
    a.material = dict(_MATERIAL_PRESETS["Metal"])
    win.properties.refresh()
    assert win.properties.material_combo.currentIndex() == -1


def test_the_rows_are_undoable(win):
    a, b = _two(win)
    combo = win.properties.material_combo
    combo.setCurrentIndex(combo.findData("Metal"))
    assert win.scene.get(a.id).material is not None
    win.processor.run("undo")
    assert win.scene.get(a.id).material is None
