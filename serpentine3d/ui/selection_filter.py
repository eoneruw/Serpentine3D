"""The selection filter as a row of buttons along the status bar.

Rhino keeps its filter along the bottom of the window — Points, Curves,
Surfaces, Polysurfaces, ... — and you click the kinds you want to be
able to pick. Serpentine3D had the same filter but only by typing
`selfilter`, which made it something you had to know about rather than
something you could see. This is the same SelectionManager state
(filter_kinds, filter_active) with buttons on it: click a kind to make
clicking pick only that kind, click it again to let go; no kinds lit
means the filter is off. The `selfilter` and `sft` commands still work
and the buttons follow them.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from . import theme

#: (object kind, button label, tooltip)
KINDS = (
    ("point", "Pt", "Points"),
    ("curve", "Crv", "Curves"),
    ("surface", "Srf", "Surfaces"),
    ("solid", "Sld", "Solids"),
    ("mesh", "Msh", "Meshes"),
    ("pointcloud", "Cld", "Point clouds"),
)

_BUTTON_STYLE = f"""
QToolButton {{
    padding: 1px 6px; font-size: 11px; border-radius: 3px;
    border: 1px solid transparent; color: {theme.TEXT_MUTED};
}}
QToolButton:hover {{ border-color: #4a4b52; }}
QToolButton:checked {{
    background: #4a3f28; border-color: {theme.ACCENT}; color: #f0d9a8;
}}
"""


class SelectionFilterBar(QWidget):
    """A button per kind. Lit means clicks in the viewport pick only the
    lit kinds; none lit means anything goes."""

    def __init__(self, selection, on_change=None, parent=None):
        super().__init__(parent)
        self.selection = selection
        self._on_change = on_change
        self._syncing = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        label = QLabel("Filter")
        label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        label.setToolTip("Which kinds of object a click can pick. "
                         "Nothing lit: anything.")
        row.addWidget(label)
        self.buttons: dict[str, QToolButton] = {}
        for kind, text, tip in KINDS:
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(f"{tip} — click to pick only these")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_BUTTON_STYLE)
            btn.toggled.connect(
                lambda on, k=kind: self._toggled(k, on))
            row.addWidget(btn)
            self.buttons[kind] = btn
        self.sync()

    # ------------------------------------------------------------ buttons

    def _toggled(self, kind: str, on: bool):
        if self._syncing:
            return
        sel = self.selection
        kinds = set(sel.filter_kinds) if sel.filter_active else set()
        if on:
            kinds.add(kind)
        else:
            kinds.discard(kind)
        sel.filter_kinds = kinds
        sel.filter_active = bool(kinds)
        if self._on_change is not None:
            self._on_change()

    def sync(self):
        """Show what the SelectionManager says, for when a command set
        the filter rather than a click here."""
        sel = self.selection
        lit = set(sel.filter_kinds) if sel.filter_active else set()
        self._syncing = True
        try:
            for kind, btn in self.buttons.items():
                btn.setChecked(kind in lit)
        finally:
            self._syncing = False

    def lit_kinds(self) -> set[str]:
        return {k for k, b in self.buttons.items() if b.isChecked()}
