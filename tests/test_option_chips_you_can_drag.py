"""An option that is a number is a chip you drag, and the command hears it.

Option chips beside the prompt cycled a list on a click — Cap=Yes,
Cap=No. A number had no chip at all: Bulge lived in the prompt text and
changed by typing. Now a `Scrub(...)` value in `choices` makes a chip
you press and drag sideways, the value running between its limits as
you go; a request's `on_option` is called on every change, so a command
can rebuild what it is making while you look at it, and the history is
told once, when you let go. A list chip still cycles on a click.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.commands.base import PointReq, Scrub, command, resolve


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


HEARD: list = []


if resolve("_scrubtest") is None:
    @command("_scrubtest")
    def _cmd(ctx):
        """A prompt with a number chip and a list chip, for the tests."""
        HEARD.clear()

        def hear(name, value):
            HEARD.append((name, value))
        while True:
            p = yield PointReq(
                "Look at it (Enter to keep)", allow_empty=True,
                choices={"Bulge": Scrub(1.0, 0.1, 3.0, step=0.01),
                         "Side": ["Left", "Right"]},
                on_option=hear)
            if p is None:
                break
        ctx.echo(f"kept bulge {ctx.options.get('Bulge', '1')} "
                 f"side {ctx.options.get('Side', 'Left')}")


@pytest.fixture
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


def test_a_scrub_takes_numbers_and_tells_the_command(win):
    proc = win.processor
    proc.run("_scrubtest")
    assert [n for n, _ in proc.option_chips()] == ["Bulge", "Side"]
    assert proc.option_chips()[0] == ("Bulge", "1")
    assert proc.set_option("Bulge", "2.5")
    assert HEARD[-1] == ("Bulge", "2.5")
    assert proc.set_option("Bulge", "99"), "clamped, not refused"
    assert proc.option("Bulge", "1") == "3"
    assert not proc.set_option("Bulge"), "a number has nothing to cycle"
    assert not proc.set_option("Bulge", "lots")
    assert proc.set_option("Side"), "a list still cycles"
    assert HEARD[-1] == ("Side", "Right")
    proc.provide_text("")
    assert not proc.busy


def test_typing_name_equals_value_still_works(win):
    proc = win.processor
    proc.run("_scrubtest")
    proc.provide_text("Bulge=0.4")
    assert proc.option("Bulge", "1") == "0.4"
    assert HEARD[-1] == ("Bulge", "0.4")
    proc.provide_text("")


def _drag(chip, dx, final=True):
    at = QPointF(10, 8)
    QApplication.sendEvent(chip, QMouseEvent(
        QEvent.Type.MouseButtonPress, at, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    for frac in (0.3, 0.6, 1.0):
        QApplication.sendEvent(chip, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(10 + dx * frac, 8),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
    if final:
        QApplication.sendEvent(chip, QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(10 + dx, 8),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))


def test_dragging_the_chip_runs_the_value_and_echoes_once(win):
    from serpentine3d.ui.command_line import ScrubChip
    proc = win.processor
    said = []
    proc.ctx.add_echo_listener(said.append)
    proc.run("_scrubtest")
    QApplication.processEvents()
    chips = win.command_line._chips
    bulge = next(c for c in chips if isinstance(c, ScrubChip))
    assert bulge.text() == "Bulge=1"
    heard_before = len(HEARD)
    _drag(bulge, 100)                     # 100 px * 0.01 = +1.0
    assert proc.option("Bulge", "1") == "2"
    assert bulge.text() == "Bulge=2"
    assert len(HEARD) - heard_before >= 3, "heard on the way, not once"
    assert said.count("Bulge=2") == 1, "the history hears it once"
    _drag(bulge, -500)
    assert proc.option("Bulge", "1") == "0.1", "held at the floor"
    proc.provide_text("")
    assert "kept bulge 0.1" in said[-1]


def test_a_click_that_never_moved_leaves_the_value_alone(win):
    from serpentine3d.ui.command_line import ScrubChip
    proc = win.processor
    proc.run("_scrubtest")
    QApplication.processEvents()
    bulge = next(c for c in win.command_line._chips
                 if isinstance(c, ScrubChip))
    _drag(bulge, 0)
    assert proc.option("Bulge", "1") == "1"
    proc.provide_text("")


def test_the_list_chip_cycles_on_a_click(win):
    from serpentine3d.ui.command_line import ScrubChip
    proc = win.processor
    proc.run("_scrubtest")
    QApplication.processEvents()
    side = next(c for c in win.command_line._chips
                if not isinstance(c, ScrubChip))
    assert side.text() == "Side=Left"
    side.click()
    assert proc.option("Side", "Left") == "Right"
    QApplication.processEvents()
    assert side.text() == "Side=Right"
    proc.provide_text("")
