"""A physically based display mode beside the old rendered one.

`rendered` lights materials with three fixed lamps. The new `pbr` mode
lights the same materials from a studio environment — reflections of
softboxes in a chrome ball, a clearcoat over car paint, filmic tone
mapping — and lives next to `rendered` in every list, so the two can be
compared on the same model rather than one replacing the other.

The GL side needs a context, which CI's offscreen platform does not
have; those tests skip there. The lighting maths (tests/test_ibl.py) and
the plumbing here run everywhere.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.commands.base import resolve
from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui import display_panel
from serpentine3d.ui.viewport import Viewport


def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def vp():
    _qapp()
    scene = Scene()
    return Viewport(scene, SelectionManager(scene))


@pytest.fixture
def win():
    _qapp()
    w = MainWindow()
    yield w
    w.mark_saved()          # or closing asks about the changes, forever
    w.close()


# ------------------------------------------------------------ registered

def test_pbr_is_a_display_mode_beside_rendered(vp):
    assert "pbr" in Viewport.DISPLAY_MODES
    assert "rendered" in Viewport.DISPLAY_MODES, "the old one stays"
    assert Viewport.RENDER_MODES == ("rendered", "pbr")
    vp.set_display_mode("pbr")
    assert vp.display_mode == "pbr"


def test_pbr_is_a_render_and_leaves_the_isocurves_off(vp):
    vp.set_display_mode("pbr")
    assert not vp.shows_isocurves()
    assert not vp.shows_edges(), "a render is not a line drawing"
    vp.set_edges(True)
    assert vp.shows_edges(), "but the panel can put them back"


def test_it_is_called_something_a_person_can_read():
    assert Viewport.mode_label("pbr") == "Rendered (PBR)"
    assert Viewport.mode_label("shaded") == "Shaded"
    panel = dict(display_panel._MODES)
    assert panel["pbr"] == Viewport.mode_label("pbr")


def test_the_display_panel_lists_it_after_rendered():
    ids = [m for m, _ in display_panel._MODES]
    assert ids.index("pbr") == ids.index("rendered") + 1


def test_the_pane_title_uses_the_label(win):
    win.viewport.set_display_mode("pbr")
    assert "Rendered (PBR)" in win._viewport_title(win.viewport)


def test_the_command_switches_to_it(win):
    cd = resolve("pbr")
    assert cd is not None and not cd.mutates
    assert resolve("advancedrender").name == "pbr"
    win.processor.run("pbr")
    assert win.viewport.display_mode == "pbr"
    win.processor.run("rendered")
    assert win.viewport.display_mode == "rendered"


def test_rhinos_raytraced_macro_lands_here():
    from serpentine3d.utils.config import RHINO_MACRO_MAP
    assert RHINO_MACRO_MAP["setdisplaymode raytraced"] == "pbr"


# ------------------------------------------------------------- materials

def test_carpaint_and_chrome_presets_exist():
    from serpentine3d.commands.edit import _MATERIAL_PRESETS
    paint = _MATERIAL_PRESETS["Carpaint"]
    assert paint["clearcoat"] == 1.0
    assert 0 < paint["clearcoat_roughness"] < 0.2, "a glossy film"
    chrome = _MATERIAL_PRESETS["Chrome"]
    assert chrome["metallic"] == 1.0 and chrome["roughness"] < 0.1


def test_the_material_command_offers_them(win):
    win.scene.add(g.make_box((0, 0, 0), 5, 5, 5), name="Panel")
    win.processor.run("material")
    win.processor.provide_text("Panel")
    win.processor.provide_text("")
    req = win.processor.request
    assert "Carpaint" in req.options and "Chrome" in req.options
    win.processor.provide_text("Carpaint")
    mat = win.scene.all()[0].material
    assert mat["clearcoat"] == 1.0


# --------------------------------------------------------- frame stats

def test_frame_statistics_are_off_until_asked(vp):
    assert vp.show_stats is False
    assert vp._stats_label.isHidden()


def test_the_setting_turns_them_on_in_every_pane(win):
    from serpentine3d.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(win)
    dlg.cb_stats.setChecked(True)
    assert win.cfg.get("display", "show_stats") is True
    assert all(vp.show_stats for vp in win.all_viewports())
    dlg.cb_stats.setChecked(False)
    assert not any(vp.show_stats for vp in win.all_viewports())
    dlg.close()


def test_the_viewstats_command_toggles_them(win):
    assert resolve("fps").name == "viewstats"
    win.processor.run("viewstats")
    assert win.viewport.show_stats is True
    assert win.cfg.get("display", "show_stats") is True
    win.processor.run("viewstats")
    assert win.viewport.show_stats is False


def test_a_frame_is_summed_up_in_one_line(vp):
    """Given a frame's numbers, the readout says ms, fps, objects, tris,
    mode — the things you compare two modes by."""
    import time
    vp.set_show_stats(True)
    vp.set_display_mode("pbr")
    vp._frame_tris = 2_106_936
    vp._frame_objs = 4
    vp._stats_shown_at = 0.0
    vp._note_frame(time.perf_counter() - 0.0123)
    text = vp._stats_label.text()
    assert "ms" in text and "fps" in text
    assert "4 obj" in text and "2.11M tri" in text and "pbr" in text
    vp.set_show_stats(False)
    assert vp._stats_label.isHidden()


# ------------------------------------------------------------ with a GPU

def _gl_available(vp) -> bool:
    return not vp.grabFramebuffer().isNull()


def test_the_pbr_shader_compiles_and_draws(win):
    """Real GL only: the shader links, the environment uploads, a frame
    in pbr comes out with the object's colour in it and not black."""
    vp = win.viewport
    if not _gl_available(vp):
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")
    o = win.scene.add(g.make_sphere((0, 0, 0), 20), name="Ball")
    o.color = (0.9, 0.1, 0.1)
    o.material = {"metallic": 0.0, "roughness": 0.4, "opacity": 1.0,
                  "clearcoat": 1.0, "clearcoat_roughness": 0.05}
    win.processor.run("zoomextents")
    vp.set_display_mode("pbr")
    for _ in range(3):
        vp.update()
        QApplication.processEvents()
    img = vp.grabFramebuffer()
    assert vp._env_tex, "the environment texture was uploaded"
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    assert c.red() > 80 and c.red() > c.green() + 30, \
        "a red ball in the middle of the frame"
