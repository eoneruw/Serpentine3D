"""What the pane you are in draws: its mode, and what it draws on top.

Rhino puts this beside Properties and people coming from it look there
first. GitHub #5 asked for it by name, wanting isocurves off in a rendered
view; before this the only way to reach a display mode at all was the
viewport's own title, and isocurves could not be reached at all.

The panel holds no state. It reads the active viewport on every refresh
and writes straight back to it, so four panes with four different settings
stay four panes rather than one panel's idea of them.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QSlider, QVBoxLayout,
    QWidget,
)

from ..core import tessellate
from . import ibl

#: The combo's last entry: pick an equirectangular image of your own.
_CUSTOM = "__custom__"

#: Mode id to the label people read, in the order the View menu lists them.
_MODES = [
    ("wireframe", "Wireframe"),
    ("shaded", "Shaded"),
    ("ghosted", "Ghosted"),
    ("rendered", "Rendered"),
    ("pbr", "Rendered (PBR)"),          # keep in step with Viewport.MODE_LABELS
    ("technical", "Technical"),
    ("zebra", "Zebra"),
    ("curvature", "Curvature"),
    ("draft", "Draft angle"),
]

#: Mesh quality id to its label, coarsest first.
_QUALITIES = list(tessellate.MESH_QUALITY_LABELS.items())


class DisplayPanel(QWidget):
    """Display settings for whichever viewport is active."""

    def __init__(self, viewport_source, parent=None, all_panes=None,
                 config=None):
        super().__init__(parent)
        self._source = viewport_source
        # the environment is the scene's, so a change to it redraws every
        # pane; without this, only the active one
        self._all = all_panes or (lambda: [p for p in [viewport_source()]
                                           if p is not None])
        self._config = config
        self._loading = False           # refresh must not look like a click

        self.mode_box = QComboBox()
        for mode_id, label in _MODES:
            self.mode_box.addItem(label, mode_id)
        self.mode_box.currentIndexChanged.connect(self._mode_picked)

        self.iso_box = QCheckBox("Surface isocurves")
        self.iso_box.setToolTip(
            "The wires across a surface. Off in Rendered by default.")
        self.iso_box.toggled.connect(
            lambda on: self._write(lambda vp: vp.set_isocurves(on)))

        self.edge_box = QCheckBox("Surface edges")
        self.edge_box.setToolTip(
            "The outlines of faces. Curves and text are not affected.")
        self.edge_box.toggled.connect(
            lambda on: self._write(lambda vp: vp.set_edges(on)))

        # How finely curved surfaces are cut into triangles. One setting
        # for the whole scene rather than per pane: the mesh is cached on
        # the object, and every pane draws the same one.
        self.quality_box = QComboBox()
        for quality_id, label in _QUALITIES:
            self.quality_box.addItem(label, quality_id)
        self.quality_box.setToolTip(
            "How finely curved surfaces are cut into triangles for the "
            "screen. Fine or Very fine stops a mirror-like reflection in "
            "Rendered from showing the triangles as creases; Coarse keeps "
            "a heavy scene quick.")
        self.quality_box.currentIndexChanged.connect(self._quality_picked)

        form = QFormLayout()
        form.setContentsMargins(8, 8, 8, 4)
        form.addRow("Mode", self.mode_box)
        form.addRow("Mesh", self.quality_box)

        # -- the environment, for the PBR mode --
        self.env_box = QComboBox()
        for name in ibl.environment_names():
            self.env_box.addItem(ibl.environment_label(name), name)
        self.env_box.addItem("Image file…", _CUSTOM)
        self.env_box.setToolTip("What the PBR mode lights and reflects. "
                                "Image file: an equirectangular .hdr, "
                                ".png or .jpg of your own.")
        self.env_box.currentIndexChanged.connect(self._env_picked)

        self.exposure = QSlider(Qt.Orientation.Horizontal)
        self.exposure.setRange(10, 300)          # x0.01
        self.exposure.setToolTip("Brighter or darker, the way a camera's "
                                 "exposure is")
        self.exposure.valueChanged.connect(
            lambda v: self._set_env(exposure=v / 100.0))

        self.rotation = QSlider(Qt.Orientation.Horizontal)
        self.rotation.setRange(0, 359)
        self.rotation.setToolTip("Turn the environment around the model, "
                                 "to move the reflections")
        self.rotation.valueChanged.connect(
            lambda v: self._set_env(rotation=float(v)))

        self.sky_box = QCheckBox("Environment behind the model")
        self.sky_box.setToolTip("Draw the environment as the backdrop")
        self.sky_box.toggled.connect(
            lambda on: self._set_env(background=bool(on)))

        self.env_form = QFormLayout()
        self.env_form.setContentsMargins(8, 4, 8, 4)
        self.env_form.addRow("Environment", self.env_box)
        self.env_form.addRow("Exposure", self.exposure)
        self.env_form.addRow("Rotation", self.rotation)
        self.env_widget = QWidget()
        env_col = QVBoxLayout(self.env_widget)
        env_col.setContentsMargins(0, 0, 0, 0)
        env_col.addLayout(self.env_form)
        env_col.addWidget(self.sky_box)

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addLayout(form)
        box.addWidget(self.iso_box)
        box.addWidget(self.edge_box)
        box.addWidget(self.env_widget)
        box.addStretch(1)

        self.refresh()

    # -- the environment --

    def _scene(self):
        vp = self.viewport()
        return getattr(vp, "scene", None) if vp is not None else None

    def _set_env(self, **changes):
        if self._loading:
            return
        scene = self._scene()
        if scene is None:
            return
        scene.set_environment(**changes)      # every pane hears of it

    def _env_picked(self, _index):
        if self._loading:
            return
        name = self.env_box.currentData()
        if name == _CUSTOM:
            path, _ = QFileDialog.getOpenFileName(
                self, "Environment image",
                filter="Images (*.hdr *.png *.jpg *.jpeg *.exr)")
            if not path:
                self.refresh()          # back to what it was
                return
            name = path
        self._set_env(name=name)
        self.refresh()

    # -- reading the pane --

    def viewport(self):
        return self._source()

    def refresh(self):
        """Point the controls at the active viewport. Called when the active
        pane changes and when one of them changes mode by another route."""
        vp = self.viewport()
        if vp is None:
            return
        self._loading = True
        try:
            i = self.mode_box.findData(vp.display_mode)
            if i >= 0:
                self.mode_box.setCurrentIndex(i)
            self.iso_box.setChecked(vp.shows_isocurves())
            self.edge_box.setChecked(vp.shows_edges())
            self.env_widget.setVisible(vp.display_mode == "pbr")
            env = vp.environment_settings() if hasattr(
                vp, "environment_settings") else {}
            name = str(env.get("name", "studio"))
            i = self.env_box.findData(name)
            if i < 0:
                # a picture of the user's own: shown by its file name
                i = self.env_box.findData(_CUSTOM)
                self.env_box.setItemText(i, ibl.environment_label(name))
            else:
                self.env_box.setItemText(self.env_box.findData(_CUSTOM),
                                         "Image file…")
            self.env_box.setCurrentIndex(i)
            self.exposure.setValue(int(round(
                float(env.get("exposure", 0.8)) * 100)))
            self.rotation.setValue(int(round(
                float(env.get("rotation", 0.0))) % 360))
            self.sky_box.setChecked(bool(env.get("background", False)))
            q = self.quality_box.findData(tessellate.mesh_quality())
            if q >= 0:
                self.quality_box.setCurrentIndex(q)
        finally:
            self._loading = False

    # -- and writing back to it --

    def _write(self, fn):
        vp = self.viewport()
        if vp is not None and not self._loading:
            fn(vp)

    def _mode_picked(self, _index):
        mode = self.mode_box.currentData()
        self._write(lambda vp: vp.set_display_mode(mode))
        self.env_widget.setVisible(mode == "pbr")

    def _quality_picked(self, _index):
        if self._loading:
            return
        name = self.quality_box.currentData()
        if name == tessellate.mesh_quality():
            return
        tessellate.set_mesh_quality(name)
        if self._config is not None:
            self._config.set("display", "mesh_quality", name)
        vp = self.viewport()
        panes = list(self._all()) or ([vp] if vp is not None else [])
        scenes = {id(p.scene): p.scene for p in panes if hasattr(p, "scene")}
        for scene in scenes.values():
            scene.drop_meshes()
        for pane in panes:
            pane.update()

    # -- what the tests and the window talk to --

    def mesh_quality(self) -> str:
        return self.quality_box.currentData()

    def set_mesh_quality(self, name: str):
        i = self.quality_box.findData(name)
        if i >= 0:
            self.quality_box.setCurrentIndex(i)

    def mode(self) -> str:
        return self.mode_box.currentData()

    def set_mode(self, mode: str):
        i = self.mode_box.findData(mode)
        if i >= 0:
            self.mode_box.setCurrentIndex(i)

    def isocurves_checked(self) -> bool:
        return self.iso_box.isChecked()

    def set_isocurves_checked(self, on: bool):
        self.iso_box.setChecked(bool(on))

    def edges_checked(self) -> bool:
        return self.edge_box.isChecked()

    def set_edges_checked(self, on: bool):
        self.edge_box.setChecked(bool(on))
