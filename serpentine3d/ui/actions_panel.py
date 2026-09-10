"""The Actions panel: what you can do to what you have picked, as buttons.

Two hundred commands are in the command line, and the way to find the
one you want was to know its name. This panel reads the selection and
shows the commands that apply — draw something when nothing is picked,
extrude and loft for curves, booleans for solids, crop for a picture —
in groups, each a button with the command's own description for a
tooltip. A search box at the top finds any command by name or by what
it does, for the ones that are not on the list.

It is the precursor to a right-click menu: the same table of what suits
what, shown where you can read it before you need it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from ..commands.base import all_commands, resolve
from . import theme

#: (group title, [(command, label)]) for each situation. A command that
#: is not registered (an optional plugin, an older build) is skipped, so
#: the table can name what it likes.
NOTHING = [
    ("Draw", [("line", "Line"), ("polyline", "Polyline"),
              ("curve", "Curve"), ("interpcrv", "Interp Curve"),
              ("circle", "Circle"), ("arc", "Arc"),
              ("rectangle", "Rectangle"), ("ellipse", "Ellipse"),
              ("point", "Point")]),
    ("Solids", [("box", "Box"), ("sphere", "Sphere"),
                ("cylinder", "Cylinder"), ("cone", "Cone"),
                ("torus", "Torus")]),
    ("Bring in", [("pictureframe", "Picture"), ("import", "Import…"),
                  ("open", "Open…")]),
    ("Select", [("selall", "All"), ("selcrv", "Curves"),
                ("selsrf", "Surfaces"), ("selsolid", "Solids"),
                ("selpicture", "Pictures"), ("sellast", "Last made")]),
]

CURVES = [
    ("Edit curve", [("pointson", "Points On"), ("insertknot", "Insert Point"),
                    ("removeknot", "Remove Point"), ("weight", "Weight"),
                    ("changedegree", "Degree"), ("rebuild", "Rebuild"),
                    ("join", "Join"), ("explode", "Explode"),
                    ("offset", "Offset"), ("fillet", "Fillet"),
                    ("extend", "Extend"), ("trim", "Trim"),
                    ("split", "Split"), ("divide", "Divide"),
                    ("closecrv", "Close"), ("blendcrv", "Blend"),
                    ("matchcrv", "Match")]),
    ("Surface from curves", [("extrude", "Extrude"),
                             ("planarsrf", "Planar Surface"),
                             ("revolve", "Revolve"), ("sweep1", "Sweep 1"),
                             ("sweep2", "Sweep 2"), ("loft", "Loft"),
                             ("edgesrf", "Edge Surface"), ("pipe", "Pipe"),
                             ("patch", "Patch")]),
]

SURFACES = [
    ("Edit surface", [("pointson", "Points On"),
                      ("insertknot", "Insert Row"),
                      ("insertknot Direction V", "Insert Column"),
                      ("insertknot Direction Both", "Insert Both"),
                      ("removeknot", "Remove Row"),
                      ("removeknot Direction V", "Remove Column"),
                      ("weight", "Weight"), ("changedegree", "Degree"),
                      ("untrim", "Untrim"),
                      ("trim", "Trim"), ("split", "Split"),
                      ("join", "Join"), ("offsetsrf", "Offset"),
                      ("extendsrf", "Extend"), ("flip", "Flip"),
                      ("blendsrf", "Blend"), ("extractisocurve", "Isocurve"),
                      ("dupborder", "Border Curves"),
                      ("pushpull", "Push/Pull")]),
    ("To solid", [("extrude", "Extrude"), ("cap", "Cap"),
                  ("shell", "Shell")]),
    ("Inspect", [("zebra", "Zebra"), ("curvatureanalysis", "Curvature"),
                 ("draftanalysis", "Draft")]),
]

SOLIDS = [
    ("Boolean", [("booleanunion", "Union"),
                 ("booleandifference", "Difference"),
                 ("booleanintersection", "Intersection"),
                 ("booleansplit", "Split")]),
    ("Edit solid", [("filletedge", "Fillet Edge"),
                    ("chamferedge", "Chamfer Edge"), ("shell", "Shell"),
                    ("explode", "Explode"), ("extractsrf", "Extract Face"),
                    ("pushpull", "Push/Pull"), ("section", "Section"),
                    ("contour", "Contour"),
                    ("mergeallcoplanarfaces", "Merge Faces")]),
    ("Inspect", [("zebra", "Zebra"), ("volume", "Volume"),
                 ("draftanalysis", "Draft")]),
]

MESHES = [
    ("Mesh", [("meshtobrep", "To Surfaces"), ("smooth", "Smooth"),
              ("explode", "Explode")]),
]

POINTCLOUDS = [
    ("Point cloud", [("pointcloud", "Info / Subsample")]),
]

PICTURES = [
    ("Picture", [("pointson", "Crop Corners"), ("pointsoff", "Hide Corners"),
                 ("pictureframe", "Another Picture")]),
]

#: Ctrl+Shift-picked edges and faces are a selection of their own, with
#: their own commands; these show whenever any are held.
EDGES = [
    ("Picked edges", [("blendsrf", "Blend Surface"),
                      ("dupedge", "Edge to Curve"),
                      ("extendsrf", "Extend Surface"),
                      ("filletedge", "Fillet Edge"),
                      ("chamferedge", "Chamfer Edge")]),
]
POINTS = [
    ("Held points", [("weight", "Weight"),
                     ("removecontrolpoint", "Remove Point")]),
]
FACES = [
    ("Picked faces", [("extractsrf", "Extract Face"),
                      ("pushpull", "Push/Pull"),
                      ("dupfaceborder", "Face Border"),
                      ("delete", "Delete Face")]),
]

#: Two kinds held together open up what one alone cannot: a surface and
#: a solid are a cut, curves and a surface are a trim or a projection.
#: (the two kinds held, group title, items); the same kind twice means
#: two or more objects of it
TOGETHER = [
    (("solid", "surface"),
     "Solid & surface", [("booleansplit", "Split Solid"),
                         ("trim", "Trim"), ("split", "Split"),
                         ("intersect", "Intersect")]),
    (("curve", "surface"),
     "Curve & surface", [("trim", "Trim"), ("split", "Split"),
                         ("project", "Project"), ("pull", "Pull"),
                         ("extrude", "Extrude")]),
    (("curve", "solid"),
     "Curve & solid", [("split", "Split"), ("project", "Project"),
                       ("extrude", "Extrude")]),
    (("surface", "surface"),
     "Surfaces", [("join", "Join"), ("trim", "Trim"),
                  ("intersect", "Intersect"), ("split", "Split")]),
    (("curve", "curve"),
     "Curves", [("loft", "Loft"), ("sweep2", "Sweep 2"),
                ("edgesrf", "Edge Surface"), ("join", "Join"),
                ("blendcrv", "Blend"), ("matchcrv", "Match")]),
    (("mesh", "surface"),
     "Mesh & surface", [("intersect", "Intersect")]),
]

ANY = [
    ("Transform", [("move", "Move"), ("copy", "Copy"), ("rotate", "Rotate"),
                   ("rotate3d", "Rotate 3D"), ("scale", "Scale"),
                   ("scale1d", "Scale 1D"), ("mirror", "Mirror"),
                   ("array", "Array"), ("arraypolar", "Polar Array"),
                   ("orient", "Orient")]),
    ("Organise", [("group", "Group"), ("ungroup", "Ungroup"),
                  ("hide", "Hide"), ("lock", "Lock"), ("isolate", "Isolate"),
                  ("changelayer", "Layer…"), ("matchprops", "Match Props"),
                  ("delete", "Delete")]),
]

BY_KIND = {"curve": CURVES, "surface": SURFACES, "solid": SOLIDS,
           "mesh": MESHES, "pointcloud": POINTCLOUDS, "picture": PICTURES}

_TITLE_STYLE = (f"color: {theme.TEXT_MUTED}; font-size: 11px; "
                "font-weight: bold; padding-top: 6px;")
_BUTTON_STYLE = """
QToolButton {
    background: #35363c; border: 1px solid #45464d; border-radius: 4px;
    padding: 4px 8px; font-size: 12px; text-align: left;
}
QToolButton:hover { background: #3f4047; border-color: #d9a441; }
QToolButton:pressed { background: #2b2c30; }
"""
COLUMNS = 2
PANEL_MIN_WIDTH = 240        # two buttons of a long-ish label, side by side


def groups_for(kinds, subkinds=(), counts=None) -> list:
    """The groups the panel shows for a selection of these kinds.

    `kinds` are the kinds of the objects held, `subkinds` those of any
    Ctrl+Shift-picked edges or faces, and `counts` how many of each
    object kind, so two curves offer a loft where one does not.
    """
    kinds = set(kinds)
    subkinds = set(subkinds)
    counts = counts or {}
    out: list = []
    seen = set()

    def add(title, items):
        if title not in seen:
            seen.add(title)
            out.append((title, items))

    if "edge" in subkinds:
        for title, items in EDGES:
            add(title, items)
    if "face" in subkinds:
        for title, items in FACES:
            add(title, items)
    if "cv" in subkinds:
        for title, items in POINTS:
            add(title, items)
    if not kinds:
        if not subkinds:
            return list(NOTHING)
        return out
    for (one, other), title, items in TOGETHER:
        if one == other:
            if counts.get(one, 0) >= 2:
                add(title, items)
        elif one in kinds and other in kinds:
            add(title, items)
    for kind in ("curve", "surface", "solid", "mesh", "pointcloud",
                 "picture"):
        if kind in kinds:
            for title, items in BY_KIND[kind]:
                add(title, items)
    out.extend(ANY)
    return out


def command_of(name: str):
    """The command a button runs: `insertknot Direction V` is a macro,
    insertknot with its first two prompts answered."""
    return resolve(name.split()[0]) if name.strip() else None


def describe(name: str) -> str:
    """The command's own first line, for a tooltip."""
    cd = command_of(name)
    doc = (cd.fn.__doc__ or "").strip() if cd else ""
    first = doc.split("\n", 1)[0].strip() if doc else ""
    head = name.split()[0]
    return f"{head}: {first}" if first else head


class ActionsPanel(QWidget):
    def __init__(self, scene, selection, run_command, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.selection = selection
        self.run_command = run_command

        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a command…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(PANEL_MIN_WIDTH)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(6, 2, 6, 6)
        self.body_layout.setSpacing(4)
        self.scroll.setWidget(self.body)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 0)
        root.setSpacing(4)
        root.addWidget(self.search)
        root.addWidget(self.scroll, 1)

        self.buttons: dict[str, QToolButton] = {}
        selection.add_listener(self.refresh)
        scene.add_listener(self.refresh, kinds=("objects",))
        self.refresh()

    # ------------------------------------------------------------ building

    def _clear(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # out of the tree now, not at the next event: a widget
                # left for deleteLater still paints until then, and the
                # old groups showed through the new ones
                w.setParent(None)
                w.deleteLater()
        self.buttons = {}

    def kinds(self) -> set[str]:
        return {o.kind for o in self.selection.objects()}

    def subkinds(self) -> set[str]:
        return {k for (_, k, _) in getattr(self.selection, "subobjects", [])}

    def counts(self) -> dict:
        out: dict = {}
        for o in self.selection.objects():
            out[o.kind] = out.get(o.kind, 0) + 1
        return out

    def refresh(self, *_):
        self._clear()
        query = self.search.text().strip().lower()
        if query:
            self._show_search(query)
        else:
            for title, items in groups_for(self.kinds(), self.subkinds(),
                                           self.counts()):
                self._add_group(title, items)
        self.body_layout.addStretch(1)

    def _add_group(self, title: str, items: list):
        live = [(name, label) for name, label in items
                if command_of(name) is not None]
        if not live:
            return
        head = QLabel(title)
        head.setStyleSheet(_TITLE_STYLE)
        self.body_layout.addWidget(head)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        for i, (name, label) in enumerate(live):
            grid.addWidget(self._button(name, label), i // COLUMNS,
                           i % COLUMNS)
        host = QWidget()
        host.setLayout(grid)
        self.body_layout.addWidget(host)

    def _show_search(self, query: str):
        hits = []
        for cd in all_commands():
            hay = " ".join([cd.name, *cd.aliases,
                            (cd.fn.__doc__ or "").split("\n", 1)[0]]).lower()
            if query in hay:
                hits.append(cd.name)
        if not hits:
            note = QLabel("Nothing matches.")
            note.setStyleSheet(_TITLE_STYLE)
            self.body_layout.addWidget(note)
            return
        head = QLabel(f"{len(hits)} command{'' if len(hits) == 1 else 's'}")
        head.setStyleSheet(_TITLE_STYLE)
        self.body_layout.addWidget(head)
        for name in hits[:60]:
            self.body_layout.addWidget(self._button(name, name))

    def _button(self, name: str, label: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(label)
        btn.setToolTip(describe(name))
        btn.setStyleSheet(_BUTTON_STYLE)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding,
                          QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda checked=False, n=name: self.run_command(n))
        self.buttons[name] = btn
        return btn

    def visible_commands(self) -> list[str]:
        return list(self.buttons)
