"""Properties panel: shows and edits the selected object."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ..core import geometry as g
from ..core.layout import DetailView, PaperObject, parse_scale


class CustomMaterialDialog(QDialog):
    """The five numbers of a look, each a slider-less spin box with a plain
    name, prefilled from the first selected object so a tweak starts from
    what is there rather than from zero."""

    FIELDS = (
        ("metallic", "Metallic", 0.0, "0 = paint or plastic, 1 = bare metal"),
        ("roughness", "Roughness", 0.5, "0 = mirror, 1 = chalk"),
        ("opacity", "Opacity", 1.0, "1 = solid, lower for glass"),
        ("clearcoat", "Clearcoat", 0.0,
         "A glossy clear film over the base, as car paint has (PBR display)"),
        ("clearcoat_roughness", "Clearcoat roughness", 0.1,
         "How sharp the film's reflection is (PBR display)"),
    )

    def __init__(self, parent=None, current: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Custom material")
        form = QFormLayout(self)
        self.spins = {}
        current = current or {}
        for key, label, default, tip in self.FIELDS:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(float(current.get(key, default)))
            spin.setToolTip(tip)
            form.addRow(label, spin)
            self.spins[key] = spin
        self.spins["opacity"].setMinimum(0.05)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def material(self) -> dict:
        return {key: round(spin.value(), 3) for key, spin in self.spins.items()}

    @classmethod
    def ask(cls, parent, current: dict | None) -> dict | None:
        """The material chosen, or None if the dialog was dismissed."""
        dlg = cls(parent, current)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.material()
        return None
from ..core.linetype import LINETYPES
from .layout_view import LINE_VISIBLE

# the scales an architect draws at, smallest denominator first; anything else
# is typed in and read by the same rules as the `detailscale` command
SCALE_PRESETS = ["1:1", "1:2", "1:5", "1:10", "1:20", "1:50", "1:100", "1:200"]


class PropertiesPanel(QWidget):
    def __init__(self, scene, selection, history, parent=None,
                 viewport_source=None):
        super().__init__(parent)
        self.scene = scene
        self.selection = selection
        self.history = history
        # What is picked on a sheet is held by the layout view of whichever
        # pane is showing it, so the panel has to be able to go and ask.
        self._viewport_source = viewport_source
        self._updating = False

        self.header = QLabel("No selection")
        self.header.setStyleSheet("font-weight: bold; padding: 4px;")

        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._rename)

        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._change_layer)

        from PySide6.QtWidgets import QHBoxLayout, QPushButton
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(40, 22)
        self.color_btn.setToolTip("Object colour override")
        self.color_btn.clicked.connect(self._pick_color)
        self.color_reset = QPushButton("By layer")
        self.color_reset.setToolTip("Remove the override, use layer colour")
        self.color_reset.clicked.connect(self._reset_color)
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.addWidget(self.color_btn)
        color_row.addWidget(self.color_reset)
        color_row.addStretch(1)
        self.color_widget = QWidget()
        self.color_widget.setLayout(color_row)

        # paper geometry only: a dash pattern and a printed width, both of
        # which the sheet reads straight off the object
        self.linetype_combo = QComboBox()
        self.linetype_combo.addItems(list(LINETYPES))
        self.linetype_combo.currentIndexChanged.connect(self._change_linetype)
        self.lineweight_edit = QLineEdit()
        self.lineweight_edit.setToolTip("Printed width in millimetres")
        self.lineweight_edit.editingFinished.connect(self._change_lineweight)

        # a detail only: its scale, picked from the presets or typed. Picking
        # applies at once; typing applies on Enter, so the half-typed "1:1"
        # on the way to "1:100" is never taken for a choice.
        self.scale_combo = QComboBox()
        self.scale_combo.setEditable(True)
        self.scale_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.scale_combo.addItems(SCALE_PRESETS)
        self.scale_combo.setToolTip("Detail scale, e.g. 1:50")
        self.scale_combo.currentTextChanged.connect(self._scale_chosen)
        self.scale_combo.lineEdit().editingFinished.connect(self._scale_typed)

        # The look for the render modes: the same presets the `material`
        # command offers, picked here without typing anything. Applies to
        # every selected object, as the colour does.
        from ..commands.edit import _MATERIAL_PRESETS
        self.material_combo = QComboBox()
        self.material_combo.addItem("None", None)
        for name in _MATERIAL_PRESETS:
            self.material_combo.addItem(name, name)
        self.material_combo.addItem("Custom…", "Custom")
        self.material_combo.setToolTip(
            "How the surface looks in Rendered and PBR display; "
            "Custom opens the material command for numbers")
        self.material_combo.currentIndexChanged.connect(self._change_material)

        self.kind_label = QLabel("—")
        self.measure_label = QLabel("—")
        self.measure_label.setWordWrap(True)

        self.form = form = QFormLayout()
        form.setContentsMargins(8, 4, 8, 8)
        form.setSpacing(6)
        form.addRow("Name", self.name_edit)
        form.addRow("Layer", self.layer_combo)
        form.addRow("Colour", self.color_widget)
        form.addRow("Material", self.material_combo)
        form.addRow("Linetype", self.linetype_combo)
        form.addRow("Lineweight", self.lineweight_edit)
        form.addRow("Scale", self.scale_combo)
        form.addRow("Type", self.kind_label)
        form.addRow("Info", self.measure_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.header)
        layout.addLayout(form)
        layout.addStretch(1)

        selection.add_listener(self.refresh)
        scene.add_listener(self.refresh, kinds=("objects", "layers",
                                                "layouts"))
        self.refresh()

    # -------------------------------------------------------- what is picked

    def _selected(self):
        objs = self.selection.objects()
        return objs[0] if len(objs) == 1 else None

    def _sheet_picks(self, kind: str) -> list:
        """What is picked on the sheet of one kind: "object" or "detail".

        A sheet's selection lives in the layout view rather than in the
        model-space selection the rest of this panel reads, which is why a
        picked border used to leave the panel saying "No selection".
        """
        src = self._viewport_source
        vp = src() if src is not None else None
        if vp is None or getattr(vp, "space", "model") == "model":
            return []
        lay = vp.layout_view.layout
        # Only what is on the sheet now: an undo swaps the whole sheet for a
        # clone, and a panel still offering to edit the thing that used to
        # be there would be editing something nothing draws.
        on_sheet = () if lay is None else {
            "object": lay.objects, "detail": lay.details}[kind]
        return [o for k, o in vp.layout_view.selected
                if k == kind and any(x is o for x in on_sheet)]

    def _paper_picks(self) -> list:
        """The paper geometry picked on the sheet."""
        return self._sheet_picks("object")

    def _detail_pick(self) -> DetailView | None:
        """The one detail picked on the sheet, or None: the scale row, like
        every other row here, edits a single thing."""
        picks = self._sheet_picks("detail")
        return picks[0] if len(picks) == 1 else None

    def _current(self) -> tuple:
        """What the editors here act on: (object, on_paper).

        None when nothing or more than one thing is picked — every row on this
        panel edits a single object, on paper as in the model.
        """
        papers = self._paper_picks()
        if papers:
            return (papers[0] if len(papers) == 1 else None), True
        return self._selected(), False

    # --------------------------------------------------------------- showing

    def refresh(self):
        self._updating = True
        papers = self._paper_picks()
        detail = self._detail_pick()
        self._show_rows(paper=bool(papers), detail=detail is not None)
        if papers:
            self._refresh_paper(papers)
        elif detail is not None:
            self._refresh_detail(detail)
        else:
            self._refresh_model()
        if detail is not None:
            self._show_scale(detail)
        self._updating = False

    def _show_rows(self, paper: bool, detail: bool):
        """A layer belongs to the model; a lineweight belongs to the paper;
        a scale belongs to a detail.

        Paper geometry is not on a model layer — the sheet is its own ink — and
        a model object has no printed width to give, so each side is only asked
        what it can answer.
        """
        self.form.setRowVisible(self.layer_combo, not (paper or detail))
        self.form.setRowVisible(self.material_combo, not (paper or detail))
        self.form.setRowVisible(self.linetype_combo, paper)
        self.form.setRowVisible(self.lineweight_edit, paper)
        self.form.setRowVisible(self.scale_combo, detail)
        self.color_reset.setText("By sheet" if paper else "By layer")
        self.color_reset.setToolTip(
            "Remove the override, use the sheet's ink" if paper
            else "Remove the override, use layer colour")

    def _refresh_model(self):
        objs = self.selection.objects()
        obj = self._selected()

        self.layer_combo.clear()
        for layer in self.scene.layers.all():
            self.layer_combo.addItem(layer.name, layer.id)

        if obj is None and len(objs) > 1:
            # Several picked: a name and a measurement belong to one thing,
            # but a colour and a material are what you give a group. The
            # swatch shows the first one's; the reset stays live if any of
            # them has an override to remove.
            self.header.setText(f"{len(objs)} objects selected")
            self._blank_editors()
            self.layer_combo.setEnabled(False)
            self.color_widget.setEnabled(True)
            self._show_swatch(self._ink_of(objs[0]))
            self.color_reset.setEnabled(any(o.color is not None for o in objs))
            self.material_combo.setEnabled(True)
            self._show_material(objs)
        elif obj is None:
            self.header.setText("No selection")
            self._blank_editors()
            self.layer_combo.setEnabled(False)
        else:
            self.header.setText(obj.name)
            self.name_edit.setEnabled(True)
            self.name_edit.setText(obj.name)
            self.layer_combo.setEnabled(True)
            idx = self.layer_combo.findData(obj.layer_id)
            if idx >= 0:
                self.layer_combo.setCurrentIndex(idx)
            self.kind_label.setText(obj.kind.capitalize())
            self.measure_label.setText(self._measures(obj))
            self.color_widget.setEnabled(True)
            self._show_swatch(self._ink_of(obj))
            self.color_reset.setEnabled(obj.color is not None)
            self.material_combo.setEnabled(True)
            self._show_material([obj])

    def _refresh_paper(self, papers: list):
        obj = papers[0] if len(papers) == 1 else None
        if obj is None:
            self.header.setText(f"{len(papers)} objects selected")
            self._blank_editors()
            self.linetype_combo.setEnabled(False)
            # blank, not the last one's pattern: a greyed-out "Dashed" reads as
            # something these two have in common
            self.linetype_combo.setCurrentIndex(-1)
            self.lineweight_edit.setEnabled(False)
            self.lineweight_edit.setText("")
            return
        self.header.setText(obj.name)
        self.name_edit.setEnabled(True)
        self.name_edit.setText(obj.name)
        # said out loud, because a curve on the paper and a curve in the model
        # look the same in a one-word row and are not the same thing at all
        self.kind_label.setText(
            f"{g.shape_kind(obj.shape).capitalize()} on paper")
        self.measure_label.setText(self._paper_measures(obj))
        self.color_widget.setEnabled(True)
        self._show_swatch(self._ink_of(obj))
        self.color_reset.setEnabled(obj.color is not None)
        self.linetype_combo.setEnabled(True)
        self.linetype_combo.setCurrentText(obj.linetype or "Continuous")
        self.lineweight_edit.setEnabled(True)
        self.lineweight_edit.setText(f"{obj.lineweight:g}")

    def _refresh_detail(self, detail: DetailView):
        """A detail has no name, layer or ink of its own; what it has is a
        frame on the sheet, in paper millimetres like `_paper_measures`, and
        the scale row below."""
        self.header.setText("Detail")
        self._blank_editors()
        self.kind_label.setText("Detail")
        self.measure_label.setText(f"Frame: {detail.w:g} × {detail.h:g} mm")

    def _show_scale(self, detail: DetailView):
        """Say what the detail's scale is: the list highlights it when it is a
        preset, the text says it either way."""
        text = detail.scale_text()
        self.scale_combo.setCurrentIndex(self.scale_combo.findText(text))
        self.scale_combo.setEditText(text)

    def _blank_editors(self):
        """Nothing to edit: emptied and greyed, not left saying what the last
        pick said."""
        self.name_edit.setText("")
        self.name_edit.setEnabled(False)
        self.color_widget.setEnabled(False)
        self.color_btn.setStyleSheet("")
        self.material_combo.setEnabled(False)
        self.material_combo.setCurrentIndex(-1)
        self.kind_label.setText("—")
        self.measure_label.setText("—")

    def _show_swatch(self, color):
        self.color_btn.setStyleSheet(
            "QPushButton { background: rgb(%d,%d,%d); border: 1px solid"
            " #55565e; }" % tuple(int(c * 255) for c in color))

    def _ink_of(self, obj) -> tuple:
        """The colour the swatch should show.

        With no override of its own, paper geometry falls back to the sheet's
        ink and a model object to its layer's.
        """
        if isinstance(obj, PaperObject):
            return tuple(obj.color) if obj.color else LINE_VISIBLE[:3]
        return self.scene.color_of(obj)

    # -------------------------------------------------------------- editing

    def _paper_edit(self, label: str, obj, **fields):
        """One undo step, then tell the scene its sheet changed.

        Fields are assigned rather than mutated because a checkpoint holds a
        shallow twin of this object (see `PaperObject.__deepcopy__`), and the
        notify is not optional: paper geometry is not in the scene's object
        table, so nothing else would notice it had been edited.
        """
        self.history.checkpoint(label)
        for key, value in fields.items():
            setattr(obj, key, value)
        self.scene.notify("layouts")

    def _model_targets(self) -> list:
        """Every model object the colour and material rows act on."""
        if self._paper_picks():
            return []
        return self.selection.objects()

    def _pick_color(self):
        obj, _paper = self._current()
        targets = self._model_targets()
        if obj is None and not targets:
            return
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        current = QColor.fromRgbF(*self._ink_of(obj or targets[0]))
        color = QColorDialog.getColor(current, self, "Object colour")
        if color.isValid():
            self._set_color((color.redF(), color.greenF(), color.blueF()))

    def _set_color(self, rgb):
        obj, paper = self._current()
        if paper:
            if obj is not None:
                self._paper_edit("object colour", obj, color=tuple(rgb))
            return
        targets = self._model_targets()
        if not targets:
            return
        self.history.checkpoint("object colour")
        self.scene.update_many([o.id for o in targets], color=tuple(rgb))

    def _reset_color(self):
        obj, paper = self._current()
        if paper:
            if obj is not None and obj.color is not None:
                self._paper_edit("object colour", obj, color=None)
            return
        targets = [o for o in self._model_targets() if o.color is not None]
        if not targets:
            return
        self.history.checkpoint("object colour")
        self.scene.update_many([o.id for o in targets], color=None)

    # ------------------------------------------------------------- material

    def _show_material(self, objs):
        """The preset the selection has, blank when they disagree."""
        from ..commands.edit import _MATERIAL_PRESETS
        names = set()
        for o in objs:
            m = o.material
            if not m:
                names.add(None)
                continue
            match = next((n for n, p in _MATERIAL_PRESETS.items() if p == m),
                         "Custom")
            names.add(match)
        if len(names) == 1:
            idx = self.material_combo.findData(names.pop())
            self.material_combo.setCurrentIndex(idx)
        else:
            self.material_combo.setCurrentIndex(-1)

    def _change_material(self, _index):
        if self._updating:
            return
        targets = self._model_targets()
        if not targets:
            return
        choice = self.material_combo.currentData()
        if choice == "Custom":
            # The numbers, in a dialog over the panel. Handing this to the
            # `material` command took the selection as its first answer,
            # which emptied the panel and greyed this very row: a trap.
            mat = CustomMaterialDialog.ask(self, targets[0].material)
            if mat is None:
                self._updating = True
                self._show_material(targets)      # back to what they have
                self._updating = False
                return
        else:
            from ..commands.edit import _MATERIAL_PRESETS
            mat = dict(_MATERIAL_PRESETS[choice]) if choice else None
        self.history.checkpoint("material")
        self.scene.update_many([o.id for o in targets], material=mat)

    def _measures(self, obj) -> str:
        fmt = self.scene.format_length
        u = self.scene.units
        try:
            if obj.kind == "curve":
                return f"Length: {fmt(g.curve_length(obj.shape))}"
            if obj.kind == "surface":
                return f"Area: {g.surface_area(obj.shape):.3f} {u}²"
            if obj.kind == "solid":
                return (f"Volume: {g.volume(obj.shape):.3f} {u}³\n"
                        f"Area: {g.surface_area(obj.shape):.3f} {u}²")
        except Exception:
            pass
        return "—"

    def _paper_measures(self, obj) -> str:
        """Millimetres of paper, not the document's units: a border is 320mm
        around on the sheet whether the model is drawn in metres or inches."""
        try:
            kind = g.shape_kind(obj.shape)
            if kind == "curve":
                return f"Length: {g.curve_length(obj.shape):.2f} mm"
            if kind in ("surface", "solid"):
                return f"Area: {g.surface_area(obj.shape):.2f} mm²"
        except Exception:
            pass
        return "—"

    def _rename(self):
        if self._updating:
            return
        obj, paper = self._current()
        name = self.name_edit.text().strip()
        if obj is None or not name or name == obj.name:
            return
        if paper:
            self._paper_edit("rename", obj, name=name)
        else:
            self.history.checkpoint("rename")
            self.scene.update(obj.id, name=name)

    def _change_layer(self):
        if self._updating:
            return
        obj, paper = self._current()
        if obj is None or paper:            # paper geometry has no layer
            return
        layer_id = self.layer_combo.currentData()
        if layer_id and layer_id != obj.layer_id:
            self.history.checkpoint("change layer")
            self.scene.update(obj.id, layer_id=layer_id)

    def _change_linetype(self):
        if self._updating:
            return
        obj, paper = self._current()
        if obj is None or not paper:
            return
        name = self.linetype_combo.currentText()
        if name and name != obj.linetype:
            self._paper_edit("linetype", obj, linetype=name)

    def _change_lineweight(self):
        if self._updating:
            return
        obj, paper = self._current()
        if obj is None or not paper:
            return
        try:
            mm = float(self.lineweight_edit.text())
        except ValueError:
            mm = 0.0
        if mm > 0.0 and mm != obj.lineweight:
            self._paper_edit("lineweight", obj, lineweight=mm)
        else:
            # nothing typed that is a width, or the width it already had: put
            # back what it still is rather than leaving the box lying
            self.refresh()

    def _scale_chosen(self, text: str):
        """A preset picked from the list, or set on the control outright."""
        if self._updating:
            return
        # the same signal fires for every keystroke: a preset the user is
        # typing through is not yet a choice, and neither is anything off the
        # list — Enter says when either is, and `_scale_typed` takes it then
        if (self.scale_combo.lineEdit().isModified()
                or self.scale_combo.findText(text) < 0):
            return
        self._set_scale(text)

    def _scale_typed(self):
        """A scale typed in and confirmed with Enter, preset or not."""
        if self._updating:
            return
        self._set_scale(self.scale_combo.currentText())

    def _set_scale(self, text: str):
        detail = self._detail_pick()
        if detail is None:
            return
        denom = parse_scale(text)
        if denom is None or denom == detail.scale_denom:
            # not a scale, or the one it already has: put back what it still
            # is rather than leaving the box lying
            self.refresh()
            return
        self._paper_edit("detail scale", detail, scale_denom=denom)
