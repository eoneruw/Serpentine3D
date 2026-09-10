"""Slim osnap toggle bar shown under the command line (Rhino-style)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from ..core.snaps import SNAP_TYPES

_LABELS = {
    "end": "End", "mid": "Mid", "center": "Cen", "quad": "Quad",
    "int": "Int", "appint": "AppInt", "perp": "Perp", "near": "Near",
    "vertex": "Vert",
}
_TIPS = {
    "end": "Snap to curve endpoints",
    "mid": "Snap to curve midpoints",
    "center": "Snap to circle/arc centers",
    "quad": "Snap to circle quadrant points",
    "int": "Snap to curve-curve intersections",
    "appint": "Snap where two curves cross on screen without meeting",
    "perp": "Snap perpendicular from the previous point",
    "near": "Snap to the nearest point on a curve",
    "vertex": "Snap to mesh vertices (a scan has one under every pixel; "
              "keep this off unless you want them)",
}


class OsnapBar(QWidget):
    def __init__(self, viewport, config, parent=None):
        super().__init__(parent)
        self.viewport = viewport
        self.config = config
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 8, 3)
        layout.setSpacing(2)

        # The word itself is the master switch: click Osnap and every
        # snap is off until it is clicked again, the type buttons greyed
        # meanwhile but keeping their settings. A separate "On" button
        # beside a label read as one more snap type, and people looking
        # for the way to pause snapping did not find it.
        self._master = self._button(
            "Osnap", "Object snaps on or off — click to pause every snap "
            "and keep the settings — hold Alt to skip them for one pick)")
        self._master.setStyleSheet(
            "QToolButton { font-size: 11px; padding: 1px 7px; "
            "font-weight: bold; }"
            "QToolButton:!checked { color: #8a8b90; }")
        self._master.setChecked(viewport.snaps.enabled)
        self._master.toggled.connect(self._master_toggled)
        layout.addWidget(self._master)

        self._buttons = {}
        for t in SNAP_TYPES:
            btn = self._button(_LABELS[t], _TIPS[t])
            btn.setChecked(viewport.snaps.types.get(t, False))
            btn.toggled.connect(
                lambda on, kind=t: self._type_toggled(kind, on))
            layout.addWidget(btn)
            self._buttons[t] = btn
        for btn in self._buttons.values():
            btn.setEnabled(viewport.snaps.enabled)

        layout.addSpacing(12)
        self._grid = self._button("Grid", "Snap picked points to the grid")
        self._grid.setChecked(viewport.grid_snap)
        self._grid.toggled.connect(self._grid_toggled)
        layout.addWidget(self._grid)
        self._ortho = self._button(
            "Ortho", "Constrain picks to CPlane axes (Shift overrides)")
        self._ortho.setChecked(viewport.ortho)
        self._ortho.toggled.connect(self._ortho_toggled)
        layout.addWidget(self._ortho)
        layout.addStretch(1)

    def _button(self, text: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tip)
        btn.setCheckable(True)
        # The theme colours every tool button the same, disabled or not,
        # so a paused snap looked exactly like a live one. Paused is dim:
        # the text goes grey, a lit one keeps a ghost of its gold.
        btn.setStyleSheet(
            "QToolButton { font-size: 11px; padding: 1px 7px; }"
            "QToolButton:disabled { color: #56575c; background: #232427;"
            " border-color: transparent; }"
            "QToolButton:checked:disabled { color: #7a6a4a;"
            " background: #2c2a26; border-color: #4a4230; }")
        return btn

    def _master_toggled(self, on: bool):
        self.viewport.snaps.enabled = on
        for btn in self._buttons.values():
            btn.setEnabled(on)
        if self.config:
            self.config.set("osnaps", "enabled", on)

    def _type_toggled(self, kind: str, on: bool):
        self.viewport.snaps.types[kind] = on
        if self.config:
            self.config.set("osnaps", kind, on)

    def _panes(self) -> list:
        """Every pane the window has, when the viewport belongs to a window
        that keeps several; just the one otherwise. Grid snap and Ortho
        live on the pane, so a toggle here has to reach all of them."""
        win = self.viewport.window()
        listing = getattr(win, "all_viewports", None)
        return list(listing()) if listing is not None else [self.viewport]

    def _grid_toggled(self, on: bool):
        for vp in self._panes():
            vp.grid_snap = on
        if self.config:
            self.config.set("grid_snap", on)

    def _ortho_toggled(self, on: bool):
        for vp in self._panes():
            vp.ortho = on
        if self.config:
            self.config.set("ortho", on)

    def refresh(self):
        """Sync button states from viewport (after commands toggle them)."""
        self._master.setChecked(self.viewport.snaps.enabled)
        for t, btn in self._buttons.items():
            btn.setChecked(self.viewport.snaps.types.get(t, False))
        self._grid.setChecked(self.viewport.grid_snap)
        self._ortho.setChecked(self.viewport.ortho)
