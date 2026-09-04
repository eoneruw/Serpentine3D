"""Selecting an object must not hide what colour it is.

A selected object used to be painted solid gold — surface and wires — so
the most common thing done to a selection, changing its colour or
material from the Properties panel, showed nothing until the object was
deselected, and then changed all at once. The wires alone go gold now;
the surface keeps the object's own colour with a tint of gold over it.

The maths runs everywhere; the frame-grab test needs a real GL context
and skips on CI's offscreen platform.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.core import geometry as g
from serpentine3d.ui import theme


def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win():
    _qapp()
    w = MainWindow()
    yield w
    w.mark_saved()
    w.close()


# ------------------------------------------------------------- the tint

def test_a_selected_fill_is_still_mostly_its_own_colour():
    red = (0.9, 0.1, 0.1)
    fill = theme.selected_fill(red)
    assert fill != pytest.approx(theme.SELECTION_COLOR), "not solid gold"
    assert fill[0] > fill[1] + 0.3 and fill[0] > fill[2] + 0.3, \
        f"red should still read as red: {fill}"


def test_two_colours_stay_apart_when_both_are_selected():
    """The whole point: a change of colour is visible while selected."""
    red = theme.selected_fill((0.9, 0.1, 0.1))
    blue = theme.selected_fill((0.1, 0.1, 0.9))
    assert max(abs(a - b) for a, b in zip(red, blue)) > 0.4


def test_the_tint_is_noticeable_and_in_range():
    white = theme.selected_fill((1.0, 1.0, 1.0))
    assert white != (1.0, 1.0, 1.0), "white must look picked"
    for c in [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.2, 0.9, 0.3)]:
        fill = theme.selected_fill(c)
        assert len(fill) == 3 and all(0.0 <= x <= 1.0 for x in fill), fill


# ------------------------------------------------------------- the frame

def _gl_available(vp) -> bool:
    return not vp.grabFramebuffer().isNull()


def _centre(vp):
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    img = vp.grabFramebuffer()
    return img.pixelColor(img.width() // 2, img.height() // 2)


def test_recolouring_a_selected_object_shows_at_once(win):
    vp = win.viewport
    if not _gl_available(vp):
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")
    o = win.scene.add(g.make_sphere((0, 0, 0), 20), name="Ball")
    win.scene.update_many([o.id], color=(0.9, 0.1, 0.1))
    win.processor.run("zoomextents")
    vp.set_display_mode("shaded")
    win.selection.set([o.id])
    red = _centre(vp)
    assert red.red() > red.blue() + 60, f"a selected red ball is red: {red}"
    win.scene.update_many([o.id], color=(0.1, 0.1, 0.9))
    blue = _centre(vp)
    assert blue.blue() > blue.red() + 40, \
        f"and turns blue without deselecting: {blue}"
