"""The AI panel's feed follows new output only while you are reading the end.

While the model was working, every word it streamed and every tool chip
it added yanked the feed to the bottom, so scrolling up to re-read what
it had said a minute ago was a losing fight. A reader at the end of the
feed still follows it; a reader who has scrolled up stays put until they
come back down. Sending a message of your own always jumps to the end.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel():
    _qapp()
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    w.resize(1000, 700)
    w.show()
    p = w.show_ai_panel()
    p.scroll.setFixedHeight(120)        # small enough that 40 lines overflow
    QApplication.processEvents()
    yield p
    w.mark_saved()
    w.close()


def _fill(panel, lines: int):
    for i in range(lines):
        panel._on_text(f"line {i} of a long answer that keeps coming\n")
    _settle()


def _settle():
    for _ in range(4):
        QApplication.processEvents()


def _bar(panel):
    return panel.scroll.verticalScrollBar()


def test_a_reader_at_the_end_follows_new_output(panel):
    _fill(panel, 40)
    bar = _bar(panel)
    assert bar.maximum() > 0, "enough text to scroll"
    assert bar.value() == bar.maximum()
    panel._on_tool_start("run_command", "box")
    _fill(panel, 10)
    assert bar.value() == bar.maximum()


def test_a_reader_who_scrolled_up_is_left_alone(panel):
    _fill(panel, 40)
    bar = _bar(panel)
    bar.setValue(0)                      # gone back to the top to re-read
    _settle()
    panel._on_tool_start("run_command", "sphere")
    _fill(panel, 20)
    panel._on_tool_finish("run_command", True, "")
    _settle()
    assert bar.value() == 0, "the feed yanked the reader to the bottom"


def test_scrolling_back_down_picks_the_feed_up_again(panel):
    _fill(panel, 40)
    bar = _bar(panel)
    bar.setValue(0)
    _settle()
    bar.setValue(bar.maximum())          # back to the end
    _settle()
    _fill(panel, 20)
    assert bar.value() == bar.maximum()


def test_sending_a_message_always_jumps_to_the_end(panel):
    _fill(panel, 40)
    bar = _bar(panel)
    bar.setValue(0)
    _settle()
    panel._add_user_bubble("and now a question")
    _settle()
    assert bar.value() == bar.maximum()
