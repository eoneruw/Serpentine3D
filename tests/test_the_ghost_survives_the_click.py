"""The curve you are drawing does not blink out on every click.

Seen live, drawing a control-point curve: each click made the ghost of
the curve vanish until the mouse moved again, while the rubber band
between the points stayed. The command's state change after a pick
cleared the ghost from every pane, and only the next mouse move (rate
limited, at that) put it back. When the next prompt wants a ghost too,
it is redrawn at once for where the cursor already is.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow


def _window():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    QApplication.processEvents()
    return w


def test_the_ghost_is_redrawn_the_moment_a_point_is_taken():
    w = _window()
    w.processor.run("curve")
    w.processor.provide_text("0,0,0")
    w.processor.provide_text("20,30,0")
    # the cursor has been wandering; the ghost follows it
    w._on_mouse_world((50.0, 10.0, 0.0))
    assert w.viewport._ghost is not None, "a two-point curve plus the cursor"

    # the click: the processor takes the cursor's point and asks the next
    w.processor.provide((50.0, 10.0, 0.0))

    assert w.viewport._ghost is not None, \
        "the curve must not vanish between the click and the next move"
    w.processor.cancel()


def test_a_prompt_without_a_preview_still_clears_it():
    w = _window()
    w.processor.run("curve")
    w.processor.provide_text("0,0,0")
    w.processor.provide_text("20,30,0")
    w._on_mouse_world((50.0, 10.0, 0.0))
    assert w.viewport._ghost is not None
    w.processor.provide_text("Degree")          # an IntReq: nothing to ghost
    assert w.viewport._ghost is None
    w.processor.cancel()


def test_finishing_the_command_clears_it():
    w = _window()
    w.processor.run("curve")
    w.processor.provide_text("0,0,0")
    w.processor.provide_text("20,30,0")
    w._on_mouse_world((50.0, 10.0, 0.0))
    w.processor.provide_text("")                # Enter: done
    assert not w.processor.busy
    assert w.viewport._ghost is None
    w.mark_saved()
