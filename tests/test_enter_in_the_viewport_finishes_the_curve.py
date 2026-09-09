"""Enter with the cursor in the viewport finishes the curve being drawn.

Seen in the live app: drawing a curve, the prompt says "Next control point
(Enter to finish)", and pressing Enter with the cursor over the canvas did
nothing — the curve only finished after clicking into the command line and
pressing Enter there. Escape worked from the canvas, and threw the whole
curve away, so the one key that responded was the one that lost the work.

A right-click in the viewport already acts as Enter (Rhino-style) in both
states — mid-command it commits, idle it repeats — and the keyboard's Enter
should mean exactly the same thing from the same place.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow


def _window():
    w = MainWindow()
    w.resize(1200, 800)
    QApplication.processEvents()
    return w


def _draw_three_points(w, name: str):
    w.processor.run(name)
    for p in ("0,0,0", "20,30,0", "50,10,0"):
        w.processor.provide_text(p)
    assert w.processor.busy and w.processor.active.name == name
    assert "Enter to finish" in w.processor.prompt_text()


@pytest.mark.parametrize("name", ["curve", "interpcrv", "polyline"])
def test_enter_over_the_canvas_finishes_the_curve(name):
    w = _window()
    before = len(w.scene.objects)
    _draw_three_points(w, name)
    w.viewport.setFocus()

    QTest.keyClick(w.viewport, Qt.Key.Key_Return)
    QApplication.processEvents()

    assert not w.processor.busy, "Enter over the canvas must finish the command"
    assert len(w.scene.objects) == before + 1, "and keep what was drawn"


def test_enter_over_the_canvas_with_too_few_points_keeps_asking():
    """One point is not a curve: the prompt has no empty answer yet, so
    Enter does not finish and does not cancel either."""
    w = _window()
    w.processor.run("curve")
    w.processor.provide_text("0,0,0")
    w.viewport.setFocus()

    QTest.keyClick(w.viewport, Qt.Key.Key_Return)
    QApplication.processEvents()

    assert w.processor.busy and w.processor.active.name == "curve"


def test_enter_over_the_canvas_commits_a_value_typed_at_the_prompt():
    """Typing focuses the command line, but if focus has gone back to the
    canvas (a click to orbit, say) Enter still commits what was typed."""
    w = _window()
    w.processor.run("curve")
    w.processor.provide_text("0,0,0")
    w.command_line.input.setText("40,40,0")
    w.viewport.setFocus()

    QTest.keyClick(w.viewport, Qt.Key.Key_Return)
    QApplication.processEvents()

    assert w.processor.busy
    assert w.processor.picked_points[-1] == pytest.approx((40.0, 40.0, 0.0))


def test_escape_over_the_canvas_still_cancels():
    w = _window()
    before = len(w.scene.objects)
    _draw_three_points(w, "curve")
    w.viewport.setFocus()

    QTest.keyClick(w.viewport, Qt.Key.Key_Escape)
    QApplication.processEvents()

    assert not w.processor.busy
    assert len(w.scene.objects) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
