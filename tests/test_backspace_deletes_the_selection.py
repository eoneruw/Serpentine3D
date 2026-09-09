"""The key labelled "delete" on a Mac keyboard deletes the selection.

Seen on a MacBook: an object picked, the delete key pressed, nothing.
That key sends Backspace — a Mac has no forward-Delete key on the board,
it is fn+delete — and the model view only listened for forward Delete.
The sheet view already took either, and Rhino for Mac deletes on that
key, so the model view now takes it too.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.core import geometry as g


def _window_with_a_box():
    w = MainWindow()
    w.resize(1200, 800)
    QApplication.processEvents()
    box = w.scene.add(g.make_box((0, 0, 0), 10, 10, 10))
    w.selection.set([box.id])
    w.viewport.setFocus()
    return w, box


@pytest.mark.parametrize("key", [Qt.Key.Key_Backspace, Qt.Key.Key_Delete])
def test_either_delete_key_deletes_the_selected_object(key):
    w, box = _window_with_a_box()
    QTest.keyClick(w.viewport, key)
    QApplication.processEvents()
    assert w.scene.get(box.id) is None
    assert not w.processor.busy


def test_backspace_with_nothing_selected_does_nothing():
    w, box = _window_with_a_box()
    w.selection.clear()
    QTest.keyClick(w.viewport, Qt.Key.Key_Backspace)
    QApplication.processEvents()
    assert w.scene.get(box.id) is not None
    assert not w.processor.busy


def test_backspace_in_the_command_line_still_edits_text():
    """Typing a command and correcting a typo must not delete the model."""
    w, box = _window_with_a_box()
    w.command_line.focus()
    QTest.keyClicks(w.command_line.input, "boxx")
    QTest.keyClick(w.command_line.input, Qt.Key.Key_Backspace)
    QApplication.processEvents()
    assert w.command_line.input.text() == "box"
    assert w.scene.get(box.id) is not None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
