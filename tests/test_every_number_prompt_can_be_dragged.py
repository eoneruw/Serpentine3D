"""Every prompt that takes a number gets a chip you drag, and the ghost follows.

A fillet radius, an offset distance, an extrusion height, a pipe
radius, a shell thickness, a count: each was a number to type and
retype until the ghost looked right. Now the prompt itself carries a
chip — press, drag sideways, and the number runs into the input line
with the gold ghost following; Enter takes it. Nothing per command:
the processor reads the request, so it works for all of them at once.
This test walks a couple of dozen commands to their number prompt and
drags.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.commands.base import (IntReq, OptionReq, PointReq,
                                        SelectReq, TextReq, resolve)
from serpentine3d.core import geometry as g


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


@pytest.fixture(scope="module")
def win():
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w.resize(900, 600)
    w.show()
    for _ in range(3):
        QApplication.processEvents()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def _setup(w, kind):
    w.processor.cancel()
    for o in list(w.scene.all()):
        w.scene.remove(o.id)
    w.selection.clear()
    if kind == "curve":
        a = w.scene.add(g.make_line((0, 0, 0), (50, 0, 0)), name="L1")
        w.selection.set([a.id])
    elif kind == "circle":
        a = w.scene.add(g.make_circle((0, 0, 0), 10), name="C")
        w.selection.set([a.id])
    elif kind == "solid":
        a = w.scene.add(g.make_box((0, 0, 0), 20, 20, 20), name="B")
        w.selection.set([a.id])
    elif kind == "surface":
        a = w.scene.add(g.loft([g.make_line((0, 0, 0), (100, 0, 0)),
                                g.make_line((0, 50, 0), (100, 50, 10))]),
                        name="S")
        w.selection.set([a.id])
    elif kind == "edge":
        a = w.scene.add(g.loft([g.make_line((0, 0, 0), (100, 0, 0)),
                                g.make_line((0, 50, 0), (100, 50, 10))]),
                        name="S")
        w.selection.set_subobjects([(a.id, "edge", 0)])
    elif kind == "mesh":
        from serpentine3d.core.mesh import MeshShape
        a = w.scene.add(MeshShape(
            np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [10, 10, 0]],
                     float), np.array([[0, 1, 2], [1, 3, 2]], np.uint32)),
            name="M")
        w.selection.set([a.id])


def _walk_to_the_number(w):
    """Answer the prompts before the number one plainly, and stop there."""
    proc = w.processor
    for step in range(6):
        r = proc.request
        if r is None or proc.number_scrub() is not None:
            return proc.number_scrub()
        if isinstance(r, (SelectReq, OptionReq)):
            proc.provide_text("")
        elif isinstance(r, PointReq):
            proc.provide_text("0,0,0" if step % 2 == 0 else "30,30,0")
        elif isinstance(r, TextReq):
            proc.provide_text("x")
        else:
            proc.provide_text("")
        if not proc.busy:
            return None
    return proc.number_scrub()


def _drag(chip, dx):
    QApplication.sendEvent(chip, QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(10, 8),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier))
    for frac in (0.5, 1.0):
        QApplication.sendEvent(chip, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(10 + dx * frac, 8),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(chip, QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(10 + dx, 8),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier))


#: (command, what to have selected, the label the chip should carry,
#:  whether the prompt draws a ghost of the result while you drag)
CASES = [
    ("offset", "circle", "Offset distance", True),
    ("extrude", "circle", "Extrusion distance", True),
    ("pipe", "curve", "Pipe radius", True),
    ("filletedge", "solid", "Fillet radius", True),
    ("chamferedge", "solid", "Chamfer distance", True),
    ("shell", "solid", "Wall thickness", True),
    ("offsetsrf", "surface", "Offset distance", True),
    ("extendsrf", "edge", "Extension length", True),
    ("extend", "curve", "Extension length", True),
    ("helix", None, "Radius", True),
    ("cylinder", None, "Radius", True),
    ("sphere", None, "Radius", True),
    ("cone", None, "Base radius", True),
    ("torus", None, "Major radius", True),
    ("circle", None, "Radius", True),
    ("box", None, "Opposite corner of base", True),
    ("scale", "solid", "Scale factor", False),
    ("rotate", "solid", "Angle in degrees", False),
    ("rebuild", "curve", "Point count", False),
    ("divide", "curve", "Number of segments", False),
    ("array", "solid", "Count X", False),
    ("arraypolar", "solid", "Number of items", False),
    ("revolve", "curve", "Angle in degrees", False),
    ("twist", "solid", "Total twist angle", False),
    ("bend", "solid", "Bend angle", False),
    ("taper", "solid", "End scale factor", False),
]


@pytest.mark.parametrize("name,kind,label,ghosts", CASES,
                         ids=[c[0] for c in CASES])
def test_the_number_prompt_drags_and_the_ghost_follows(win, name, kind,
                                                        label, ghosts):
    if resolve(name) is None:
        pytest.skip(f"{name} is not in this build")
    _setup(win, kind)
    win.processor.run(name)
    spec = _walk_to_the_number(win)
    assert spec is not None, f"{name} never asked for a number"
    assert spec[0] == label
    QApplication.processEvents()
    chip = win.command_line.number_chip()
    assert chip is not None and chip.name == label
    _drag(chip, 40)
    text = win.command_line.input.text()
    assert text, "the drag wrote a number into the input line"
    value = float(text)
    assert value > spec[1].default or spec[1].integer
    if ghosts:
        assert win.processor.preview_shape(text) is not None, \
            f"{name}: no ghost for {text}"
    win.processor.cancel()


def test_a_prompt_that_takes_no_number_has_no_chip(win):
    _setup(win, "solid")
    win.processor.run("move")
    assert win.processor.number_scrub() is None
    QApplication.processEvents()
    assert win.command_line.number_chip() is None
    win.processor.cancel()


def test_the_dragged_number_is_what_enter_takes(win):
    _setup(win, "circle")
    win.processor.run("extrude")
    _walk_to_the_number(win)
    QApplication.processEvents()
    chip = win.command_line.number_chip()
    _drag(chip, 40)                        # 40 px at the model's step
    typed = float(win.command_line.input.text())
    win.command_line.submit_input()
    assert not win.processor.busy
    made = [o for o in win.scene.all() if o.kind == "solid"]
    assert len(made) == 1
    lo, hi = g.bbox(made[0].shape)
    assert hi[2] - lo[2] == pytest.approx(typed, abs=1e-6)


def test_a_count_drags_in_whole_numbers(win):
    _setup(win, "curve")
    win.processor.run("divide")
    _walk_to_the_number(win)
    QApplication.processEvents()
    chip = win.command_line.number_chip()
    _drag(chip, 17)                       # 0.125 per px: two whole steps
    assert win.command_line.input.text() == "12"
    win.processor.cancel()
