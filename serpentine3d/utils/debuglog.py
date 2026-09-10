"""A rolling log of each run, on disk, for the bug you cannot reproduce.

"The screen went dark" is all anyone can say about a crash that
scrolled past in a terminal they were not looking at. So every launch
writes a log of its own: what the machine is, what was opened, every
line the command line echoed, what was selected when, every warning
Qt printed and every traceback Python did — the last of these being
what a dark screen usually is (an exception in a mouse handler, raised
again on every move). Only the last few runs are kept; a log is the
size of what happened, and ten of them are enough to find the one
from this morning.

The log lives in `log_dir()`: SERP3D_LOG_DIR if set, else `logs/`
beside a source checkout (where whoever is debugging can reach it),
else the user data directory. `latest.log` there always points at the
newest run. Nothing here ever raises into the app: a log that cannot
be written is a log not kept.
"""

from __future__ import annotations

import io
import os
import platform
import sys
import time
import traceback

KEEP = 10                      # runs kept; older logs go when a new one starts
_current = None


def data_log_dir() -> str:
    return os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "serpentine3d", "logs")


def checkout_dir() -> str | None:
    """The source checkout this package runs from, or None if installed."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.dirname(here)
    if os.path.isdir(os.path.join(root, ".git")) and \
            os.path.isfile(os.path.join(root, "pyproject.toml")):
        return root
    return None


def log_dir() -> str:
    env = os.environ.get("SERP3D_LOG_DIR")
    if env:
        return env
    root = checkout_dir()
    if root is not None:
        return os.path.join(root, "logs")
    return data_log_dir()


class _Tee(io.TextIOBase):
    """A stream that writes to the terminal and the log both."""

    def __init__(self, original, log, tag):
        self.original = original
        self.log = log
        self.tag = tag

    def write(self, s):
        try:
            if self.original is not None:
                self.original.write(s)
        except Exception:                                  # noqa: BLE001
            pass
        self.log.raw(self.tag, s)
        return len(s)

    def flush(self):
        try:
            if self.original is not None:
                self.original.flush()
        except Exception:                                  # noqa: BLE001
            pass

    @property
    def encoding(self):
        return getattr(self.original, "encoding", "utf-8")

    def isatty(self):
        try:
            return bool(self.original and self.original.isatty())
        except Exception:                                  # noqa: BLE001
            return False

    def fileno(self):
        return self.original.fileno()


class RunLog:
    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8", buffering=1)
        self._t0 = time.time()
        self._partial: dict[str, str] = {}
        self.broken = False

    # ------------------------------------------------------------ writing

    def _stamp(self) -> str:
        return time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"

    def note(self, kind: str, text: str):
        """One line: what happened, tagged with what kind of thing it is
        (cmd, sel, file, gl, qt, err ...)."""
        if self.broken:
            return
        try:
            for line in str(text).splitlines() or [""]:
                self._fh.write(f"{self._stamp()}  {kind:<5} {line}\n")
        except Exception:                                  # noqa: BLE001
            self.broken = True

    def raw(self, tag: str, s: str):
        """Text as a stream wrote it, folded into lines as they complete."""
        if self.broken or not s:
            return
        buf = self._partial.get(tag, "") + s
        lines = buf.split("\n")
        self._partial[tag] = lines.pop()
        for line in lines:
            if line.strip():
                self.note(tag, line)

    # ------------------------------------------------------- stalls

    STALL_SECONDS = 4.0

    def heartbeat(self):
        """The main thread is alive: arm the stall dump afresh.

        Called from a timer on the event loop. If the loop stops turning
        for STALL_SECONDS — a beach ball — faulthandler, from a thread of
        its own that needs no GIL, writes every thread's Python stack
        into this log. That is the one thing a frozen app cannot say for
        itself, and the one thing that says where it froze.
        """
        if self.broken:
            return
        try:
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
            self._fh.flush()
            faulthandler.dump_traceback_later(self.STALL_SECONDS, repeat=False,
                                              file=self._fh)
        except Exception:                                  # noqa: BLE001
            pass

    def close(self):
        try:
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
        except Exception:                                  # noqa: BLE001
            pass
        try:
            for tag, rest in self._partial.items():
                if rest.strip():
                    self.note(tag, rest)
            self.note("run", "closed")
            self._fh.close()
        except Exception:                                  # noqa: BLE001
            pass

    # ------------------------------------------------------------ hooks

    def install(self):
        """Tee stderr and stdout, catch what nobody catches, and hear Qt."""
        sys.stderr = _Tee(sys.stderr, self, "err")
        sys.stdout = _Tee(sys.stdout, self, "out")
        previous = sys.excepthook

        def hook(exc_type, exc, tb):
            self.note("err", "".join(traceback.format_exception(
                exc_type, exc, tb)))
            previous(exc_type, exc, tb)
        sys.excepthook = hook
        try:
            from PySide6.QtCore import qInstallMessageHandler

            def qt_message(mode, context, message):
                # ours to log, and still the terminal's to show
                self.note("qt", message)
                try:
                    sys.stderr.original.write(message + "\n")
                except Exception:                          # noqa: BLE001
                    pass
            qInstallMessageHandler(qt_message)
        except Exception:                                  # noqa: BLE001
            pass

    def header(self):
        from .. import __version__
        self.note("run", f"Serpentine3D {__version__}  pid {os.getpid()}")
        self.note("run", f"python {platform.python_version()}  "
                         f"{platform.platform()}")
        try:
            from PySide6 import __version__ as pyside
            from PySide6.QtCore import qVersion
            self.note("run", f"PySide6 {pyside}  Qt {qVersion()}")
        except Exception:                                  # noqa: BLE001
            pass
        self.note("run", "argv " + " ".join(sys.argv))
        self.note("run", "cwd " + os.getcwd())


def _prune(directory: str, keep: int):
    """Older logs go, newest `keep` stay. `latest.log` is not counted."""
    logs = sorted(
        (n for n in os.listdir(directory)
         if n.startswith("serp3d-") and n.endswith(".log")))
    for name in logs[:-keep] if keep > 0 else logs:
        try:
            os.unlink(os.path.join(directory, name))
        except OSError:
            pass


def _point_latest(directory: str, path: str):
    latest = os.path.join(directory, "latest.log")
    try:
        if os.path.islink(latest) or os.path.exists(latest):
            os.unlink(latest)
        os.symlink(os.path.basename(path), latest)
    except OSError:
        try:
            with open(latest, "w", encoding="utf-8") as fh:
                fh.write(path + "\n")
        except OSError:
            pass


def start(directory: str | None = None) -> RunLog | None:
    """Begin this run's log, or None if logging is off or cannot start.

    SERP3D_NO_LOG=1 turns it off. Safe to call once per process: a
    second call returns the log already running.
    """
    global _current
    if _current is not None:
        return _current
    if os.environ.get("SERP3D_NO_LOG"):
        return None
    try:
        directory = directory or log_dir()
        os.makedirs(directory, exist_ok=True)
        _prune(directory, KEEP - 1)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(directory, f"serp3d-{stamp}-{os.getpid()}.log")
        log = RunLog(path)
        log.header()
        log.install()
        _point_latest(directory, path)
    except Exception:                                      # noqa: BLE001
        return None
    _current = log
    return log


def current() -> RunLog | None:
    return _current


def heartbeat():
    """See RunLog.heartbeat; nothing when no log is open."""
    if _current is not None:
        _current.heartbeat()


def note(kind: str, text: str):
    """Log a line if a run log is open; nothing otherwise."""
    if _current is not None:
        _current.note(kind, text)


_said: set = set()


def note_once(kind: str, text: str):
    """A line worth one appearance per run: four panes share a driver."""
    if (kind, text) in _said:
        return
    _said.add((kind, text))
    note(kind, text)


def stop():
    global _current
    if _current is not None:
        _current.close()
        _current = None
    _said.clear()
