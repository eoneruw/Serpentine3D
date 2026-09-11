"""Environments for the PBR mode: a studio, a sunny day, a sunset, and more.

One procedural studio lit everything. Now there are six to choose
from — Studio, Well-lit studio, Sunny day, Sunset, Overcast, Warehouse
— plus any equirectangular image of your own, each with a rotation
about the model, an exposure, and the option of being drawn behind
the model. The choice is the scene's (one sky, however many panes),
is saved with the file, and is reached from the Display panel when
the mode is Rendered (PBR) or from the `environment` command.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.core.scene import DEFAULT_ENVIRONMENT, Scene
from serpentine3d.ui import ibl


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


# ------------------------------------------------------------- the maps

def test_there_are_several_environments_and_they_differ():
    names = ibl.environment_names()
    assert names[0] == "studio"
    assert {"sunny", "sunset", "overcast", "warehouse",
            "bright_studio"} <= set(names)
    small = {n: ibl.ENVIRONMENTS[n][1](64) for n in names}
    for n, env in small.items():
        assert env.shape == (32, 64, 3) and env.dtype == np.float32
        assert np.isfinite(env).all() and (env >= 0).all(), n
    # a sunny day is bluer overhead than a sunset is; a sunset is warmer
    # at the horizon than an overcast day
    top = lambda e: e[2].mean(axis=0)              # noqa: E731
    line = lambda e: e[e.shape[0] // 2 - 1].mean(axis=0)   # noqa: E731
    assert top(small["sunny"])[2] > top(small["sunset"])[2]
    assert line(small["sunset"])[0] > line(small["overcast"])[0]
    # the labels read as English
    assert ibl.environment_label("bright_studio") == "Well-lit studio"


def test_lighting_is_cached_per_name_and_the_studio_alias_holds():
    a = ibl.lighting("overcast")
    b = ibl.lighting("overcast")
    assert a is b
    ladder, sh = ibl.studio_lighting()
    assert len(ladder) == ibl.LEVELS and sh.shape == (9, 3)


def test_an_image_of_your_own_is_an_environment(tmp_path):
    from PySide6.QtGui import QColor, QImage
    QApplication.instance() or QApplication([])
    img = QImage(64, 32, QImage.Format.Format_RGB32)
    img.fill(QColor(40, 90, 200))                 # a blue sky all round
    path = str(tmp_path / "sky.png")
    img.save(path)
    env = ibl.load_equirect(path)
    assert env.shape == (32, 64, 3)
    assert env[..., 2].mean() > env[..., 0].mean(), "blue, and linear"
    ladder, sh = ibl.lighting(path)
    assert len(ladder) == ibl.LEVELS
    with pytest.raises(Exception):
        ibl.load_equirect(str(tmp_path / "missing.png"))


def test_a_radiance_hdr_file_reads(tmp_path):
    # a flat 4x2 RGBE file, written by hand: header, then pixels
    w, h = 4, 2
    header = b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 2 +X 4\n"
    # (1.0, 0.5, 0.25) -> mantissas 128, 64, 32 with exponent 129
    pixel = bytes([128, 64, 32, 129])
    (tmp_path / "flat.hdr").write_bytes(header + pixel * (w * h))
    env = ibl.load_equirect(str(tmp_path / "flat.hdr"))
    assert env.shape == (h, w, 3)
    assert np.allclose(env[0, 0], (1.0, 0.5, 0.25), atol=1e-3)


# ---------------------------------------------------------- the scene

def test_the_environment_is_the_scenes_and_is_saved_with_the_file(tmp_path):
    from serpentine3d.fileio import native
    scene = Scene()
    assert scene.environment == DEFAULT_ENVIRONMENT
    scene.add(g.make_box((0, 0, 0), 1, 1, 1))
    scene.environment = {"name": "sunset", "rotation": 45.0,
                         "exposure": 1.2, "background": True}
    native.save_scene(scene, str(tmp_path / "e.serp"))
    back = Scene()
    native.load_scene(back, str(tmp_path / "e.serp"))
    assert back.environment == scene.environment
    back.clear()
    assert back.environment == DEFAULT_ENVIRONMENT, "a new file, the default"


# ------------------------------------------------------------ the app

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


def test_the_display_panel_offers_the_environments_in_pbr(win):
    panel = win.display_panel
    win.viewport.set_display_mode("shaded")
    panel.refresh()
    assert not panel.env_widget.isVisibleTo(panel)
    win.viewport.set_display_mode("pbr")
    panel.refresh()
    assert panel.env_widget.isVisibleTo(panel)
    labels = [panel.env_box.itemText(i) for i in range(panel.env_box.count())]
    assert "Sunny day" in labels and "Warehouse" in labels
    assert labels[-1] == "Image file…"
    panel.env_box.setCurrentIndex(panel.env_box.findData("sunset"))
    assert win.scene.environment["name"] == "sunset"
    panel.rotation.setValue(90)
    panel.exposure.setValue(150)
    panel.sky_box.setChecked(True)
    env = win.scene.environment
    assert env["rotation"] == 90.0 and env["exposure"] == 1.5
    assert env["background"] is True
    assert win.viewport.environment_settings()["name"] == "sunset"


def test_the_environment_command_sets_it_from_the_chips(win):
    proc = win.processor
    proc.run("environment")
    assert proc.busy
    chips = dict(proc.option_chips())
    assert chips["Environment"] == "Studio"
    proc.set_option("Environment")                   # cycles to the next
    assert win.scene.environment["name"] != "studio"
    proc.set_option("Rotation", "120")
    proc.set_option("Exposure", "1.4")
    proc.set_option("Background", "Yes")
    proc.provide_text("")
    assert not proc.busy
    env = win.scene.environment
    assert env["rotation"] == 120.0 and env["exposure"] == 1.4
    assert env["background"] is True


def test_the_environment_command_takes_an_image_path(win, tmp_path):
    from PySide6.QtGui import QColor, QImage
    img = QImage(32, 16, QImage.Format.Format_RGB32)
    img.fill(QColor(200, 200, 200))
    path = str(tmp_path / "mine.png")
    img.save(path)
    proc = win.processor
    proc.run("environment")
    proc.provide_text("Image")
    proc.provide_text(path)
    proc.provide_text("")
    assert not proc.busy
    assert win.scene.environment["name"] == path


def _gl(win):
    if win.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")


def test_each_environment_draws_and_the_rotation_moves_the_reflection(win):
    _gl(win)
    vp = win.viewport
    ball = win.scene.add(g.make_sphere((0, 0, 0), 20), name="Ball")
    win.scene.update(ball.id, color=(0.9, 0.9, 0.9),
                     material={"metallic": 1.0, "roughness": 0.1})
    win.selection.clear()
    vp.set_display_mode("pbr")
    win.processor.run("zoomextents")
    vp.land_flight()

    def frame():
        for _ in range(3):
            vp.update()
            QApplication.processEvents()
        img = vp.grabFramebuffer()
        return np.frombuffer(img.constBits(), np.uint8).reshape(
            img.height(), img.width(), 4)[..., :3].astype(float)

    seen = {}
    for name in ibl.environment_names():
        win.scene.environment = {"name": name, "rotation": 0.0,
                                 "exposure": 0.8, "background": True}
        seen[name] = frame()
        assert np.isfinite(seen[name]).all()
    assert not np.allclose(seen["sunny"], seen["warehouse"]), \
        "different skies, different pictures"
    win.scene.environment = {"name": "warehouse", "rotation": 180.0,
                             "exposure": 0.8, "background": True}
    turned = frame()
    assert not np.allclose(turned, seen["warehouse"]), \
        "turning the environment moves the reflections"


def test_a_chip_names_the_environment_it_says(win):
    """The chip list put the current environment first but looked the
    id up in the unshuffled list, so with Sunset current a click on
    Studio set Well-lit studio."""
    from serpentine3d.ui import ibl
    win.scene.set_environment(name="sunset")
    win.processor.run("environment")
    win.processor.set_option("Environment", ibl.environment_label("studio"))
    win.processor.provide_text("")
    assert win.scene.environment["name"] == "studio"


def test_changing_the_environment_is_an_edit():
    from serpentine3d.core.scene import Scene
    scene = Scene()
    before = scene.revision
    scene.set_environment(exposure=1.4)
    assert scene.revision > before
    scene.set_environment(exposure=1.4)         # the same again: nothing
    assert scene.environment["exposure"] == 1.4
