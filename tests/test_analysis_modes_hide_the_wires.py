"""Zebra, draft and curvature show the surface, not the lines on it.

What an analysis mode shows is read off the surface itself — a stripe
that bends, a colour that changes at a draft angle — and the isocurves
and face edges drawn over the top read as breaks in it: a seam edge
down a cylinder looked like a crease in the stripes. They are off in
those modes unless the display panel's switches put them back.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.viewport import Viewport


@pytest.fixture
def vp():
    QApplication.instance() or QApplication([])
    scene = Scene()
    return Viewport(scene, SelectionManager(scene))


@pytest.mark.parametrize("mode", ["zebra", "draft", "curvature"])
def test_an_analysis_mode_draws_no_wires(vp, mode):
    vp.set_display_mode(mode)
    assert not vp.shows_isocurves()
    assert not vp.shows_edges()


@pytest.mark.parametrize("mode", ["shaded", "wireframe", "ghosted"])
def test_the_working_modes_keep_theirs(vp, mode):
    vp.set_display_mode(mode)
    assert vp.shows_isocurves()
    assert vp.shows_edges()


def test_the_panel_can_put_them_back(vp):
    vp.set_display_mode("zebra")
    vp.set_edges(True)
    vp.set_isocurves(True)
    assert vp.shows_edges() and vp.shows_isocurves()
    vp.set_edges(None)
    assert not vp.shows_edges(), "following the mode again"
