"""Every run writes a log of itself, and the last ten are kept.

"The screen went dark" was the whole bug report, because the
traceback had scrolled past in a terminal nobody was watching. Now
each launch logs what the machine is, what was opened, every line the
command line echoed, what was held when, every warning Qt printed and
every traceback Python did — to a file in `logs/` beside a source
checkout (or the user data directory), with `latest.log` pointing at
the newest run. Older runs go when the eleventh starts.
"""

from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.utils import debuglog


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


@pytest.fixture
def runlog(tmp_path):
    """A log of this test's own, torn down (streams restored) after."""
    debuglog.stop()
    err, out, hook = sys.stderr, sys.stdout, sys.excepthook
    log = debuglog.start(str(tmp_path / "logs"))
    assert log is not None
    yield log
    debuglog.stop()
    sys.stderr, sys.stdout, sys.excepthook = err, out, hook


def _text(log):
    with open(log.path, encoding="utf-8") as fh:
        return fh.read()


def test_the_log_opens_with_what_the_machine_is(runlog):
    text = _text(runlog)
    assert "Serpentine3D" in text and "python" in text
    assert "Qt" in text


def test_stderr_and_uncaught_exceptions_land_in_it(runlog):
    # pytest holds the streams itself, so the tees are exercised as
    # objects; in the app they stand in for sys.stdout and sys.stderr
    debuglog._Tee(None, runlog, "out").write("hello from stdout\n")
    err = debuglog._Tee(None, runlog, "err")
    err.write("something ")            # a line arrives in pieces
    err.write("went wrong\n")
    try:
        raise ValueError("the thing that broke")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = _text(runlog)
    assert "hello from stdout" in text
    assert "something went wrong" in text
    assert "ValueError: the thing that broke" in text


def test_qt_warnings_land_in_it(runlog):
    from PySide6.QtCore import qWarning
    qWarning("a Qt warning of some kind")
    assert "a Qt warning of some kind" in _text(runlog)


def test_only_the_last_ten_runs_are_kept(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    for i in range(12):
        (d / f"serp3d-2026010{i // 10}-00000{i % 10}-1.log").write_text("x")
    err, out, hook = sys.stderr, sys.stdout, sys.excepthook
    debuglog.stop()
    log = debuglog.start(str(d))
    try:
        names = sorted(n for n in os.listdir(d) if n.startswith("serp3d-"))
        assert len(names) == debuglog.KEEP
        assert os.path.basename(log.path) in names
        latest = d / "latest.log"
        assert latest.exists() or latest.is_symlink()
        assert os.path.basename(os.path.realpath(latest)) == \
            os.path.basename(log.path)
    finally:
        debuglog.stop()
        sys.stderr, sys.stdout, sys.excepthook = err, out, hook


def test_it_lives_beside_a_source_checkout_unless_told_otherwise(
        monkeypatch, tmp_path):
    monkeypatch.delenv("SERP3D_LOG_DIR", raising=False)
    root = debuglog.checkout_dir()
    if root is not None:
        assert debuglog.log_dir() == os.path.join(root, "logs")
    monkeypatch.setenv("SERP3D_LOG_DIR", str(tmp_path / "elsewhere"))
    assert debuglog.log_dir() == str(tmp_path / "elsewhere")


def test_a_log_that_cannot_be_written_is_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_NO_LOG", "1")
    debuglog.stop()
    assert debuglog.start(str(tmp_path / "logs")) is None
    debuglog.note("cmd", "goes nowhere, quietly")


# ---------------------------------------------------------- the window

@pytest.fixture
def win(runlog):
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield w
    w.mark_saved()
    w.close()


def test_the_window_logs_commands_and_what_is_held(win, runlog):
    o = win.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="Box")
    c = win.scene.add(g.make_line((0, 0, 0), (5, 0, 0)), name="L")
    win.selection.set([o.id, c.id])
    win.selection.toggle_subobject(o.id, "edge", 0)
    win.processor.run("zoomextents")
    text = _text(runlog)
    assert "main window up" in text
    assert "1 curve, 1 solid" in text
    assert "1 edge" in text
    assert "> zoomextents" in text


def test_help_has_the_log_folder_and_the_path(win, runlog):
    labels = [a.text().replace("&", "")
              for a in win.menuBar().actions()]
    help_menu = next(a.menu() for a in win.menuBar().actions()
                     if a.text().replace("&", "") == "Help")
    items = [a.text() for a in help_menu.actions()]
    assert "Open Log Folder" in items and "Copy Log Path" in items
    win._copy_log_path()
    assert QApplication.clipboard().text() == runlog.path
    assert "Help" in labels


def test_mouse_and_keys_are_logged_with_what_was_held(win, runlog):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    vp = win.viewport
    M = Qt.KeyboardModifier
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(120, 80),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        M.ControlModifier | M.ShiftModifier))
    QApplication.sendEvent(vp, QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(120, 80),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        M.ControlModifier | M.ShiftModifier))
    QApplication.sendEvent(vp, QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Delete, M.NoModifier))
    text = _text(runlog)
    assert "press Shift+Ctrl+LMB at 120,80" in text
    assert "release Shift+Ctrl+LMB at 120,80" in text
    assert "key Del" in text


def test_a_click_says_what_it_came_to(win, runlog):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    vp = win.viewport
    for kind, b, bs in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton),
                        (QEvent.Type.MouseButtonRelease,
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(vp, QMouseEvent(kind, QPointF(20, 20), b, bs,
                                               Qt.KeyboardModifier.NoModifier))
    text = _text(runlog)
    assert "pick  nothing" in text
    win.processor.run("line")
    for kind, b, bs in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton),
                        (QEvent.Type.MouseButtonRelease,
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(vp, QMouseEvent(kind, QPointF(20, 20), b, bs,
                                               Qt.KeyboardModifier.NoModifier))
    text = _text(runlog)
    assert "point-mode" in text, "a press says the pane was waiting for a point"
    win.processor.cancel()


def test_a_stall_writes_every_threads_stack_into_the_log(runlog):
    """faulthandler's timer fires from its own thread, GIL or no GIL: a
    main thread stuck in a loop still gets its stack written down."""
    import time
    runlog.STALL_SECONDS = 0.3
    runlog.heartbeat()
    time.sleep(0.8)                       # longer than the stall limit
    runlog._fh.flush()
    text = _text(runlog)
    assert "Thread" in text or "File" in text, text[-500:]
    assert "test_a_stall_writes_every_threads_stack" in text
    import faulthandler
    faulthandler.cancel_dump_traceback_later()


def test_a_stall_the_app_came_back_from_is_stamped(tmp_path, monkeypatch):
    """faulthandler's dump has no stamp and says nothing about whether
    the app recovered; the next heartbeat says how long it was gone."""
    monkeypatch.setenv("SERP3D_LOG_DIR", str(tmp_path))
    log = debuglog.start()
    try:
        log.heartbeat()
        log._last_beat -= log.STALL_SECONDS + 2.5      # as if 6.5 s passed
        log.heartbeat()
    finally:
        debuglog.stop()
    text = (tmp_path / "latest.log").read_text()
    assert "stall" in text and "is back" in text
