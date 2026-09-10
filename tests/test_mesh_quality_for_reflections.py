"""A Mesh quality setting, for reflections that showed the triangles.

A bonnet lofted through a few curves looked wrinkled in Rendered: bands
of light bending along lines that were not in the surface. They were the
display mesh. A mirror-like reflection is read off the normal at each
pixel, and between a triangle's corners the normal is only interpolated,
so a big triangle across a gently curved panel reflects the room with a
kink at each of its edges. The surface was fine; the mesh was coarse.

So the mesh has a quality now — Coarse, Normal, Fine, Very fine — in the
Display panel, as a `meshquality` command, and remembered in settings.
Normal is what every mode used to get.
"""

import pytest

from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry, tessellate
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


@pytest.fixture(autouse=True)
def _normal_again():
    yield
    tessellate.set_mesh_quality("normal")


def _bonnet():
    rails = [geometry.make_interp_curve([(0, y, 0), (50, y, 12), (100, y, 8)])
             for y in (0, 40, 80)]
    return geometry.loft(rails)


def _triangles(shape):
    return len(tessellate.tessellate(shape).triangles)


# -- the setting itself --

def test_normal_is_the_default():
    assert tessellate.mesh_quality() == "normal"


def test_finer_qualities_cut_more_triangles():
    shape = _bonnet()
    counts = []
    for name in ("coarse", "normal", "fine", "very fine"):
        tessellate.set_mesh_quality(name)
        counts.append(_triangles(shape))
    assert counts == sorted(counts), counts
    assert counts[0] < counts[1] < counts[2] < counts[3], counts


def test_an_unknown_quality_is_refused():
    with pytest.raises(ValueError):
        tessellate.set_mesh_quality("ludicrous")
    assert tessellate.mesh_quality() == "normal"


def test_dropping_meshes_recuts_at_the_new_quality():
    scene = Scene()
    obj = scene.add(_bonnet(), name="bonnet")
    before = len(obj.mesh.triangles)
    tessellate.set_mesh_quality("fine")
    assert len(obj.mesh.triangles) == before      # cached: still coarse
    scene.drop_meshes()
    assert len(obj.mesh.triangles) > before


# -- the command --

def _run(scene, text):
    ctx = CommandContext(scene, SelectionManager(scene), History(scene))
    echoes = []
    ctx.add_echo_listener(echoes.append)
    proc = CommandProcessor(ctx)
    proc.run(text)
    return echoes


def test_the_command_changes_it_and_says_so():
    scene = Scene()
    obj = scene.add(_bonnet(), name="bonnet")
    before = len(obj.mesh.triangles)
    echoes = _run(scene, "meshquality VeryFine")
    assert tessellate.mesh_quality() == "very fine"
    assert any("VeryFine" in e for e in echoes), echoes
    assert len(obj.mesh.triangles) > before       # meshes were dropped


def test_the_command_ignores_nonsense():
    echoes = _run(Scene(), "meshquality Ludicrous")
    assert tessellate.mesh_quality() == "normal"
    # the prompt refuses it and lists what it does take
    assert any("Coarse, Normal, Fine, VeryFine" in e for e in echoes), echoes


# -- the panel and the settings file --

@pytest.fixture
def win(_qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    from serpentine3d.app import MainWindow
    w = MainWindow()
    yield w
    w.mark_saved()          # no "save changes?" dialog on the way out
    w.close()


def test_the_panel_shows_the_current_quality(win):
    assert win.display_panel.mesh_quality() == "normal"


def test_picking_fine_in_the_panel_recuts_and_remembers(win):
    obj = win.scene.add(_bonnet(), name="bonnet")
    before = len(obj.mesh.triangles)
    win.display_panel.set_mesh_quality("fine")
    assert tessellate.mesh_quality() == "fine"
    assert len(obj.mesh.triangles) > before
    assert win.cfg.get("display", "mesh_quality") == "fine"


def test_the_saved_quality_comes_back_on_launch(_qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    from serpentine3d.utils.config import Config
    Config().set("display", "mesh_quality", "very fine")
    from serpentine3d.app import MainWindow
    w = MainWindow()
    try:
        assert tessellate.mesh_quality() == "very fine"
        assert w.display_panel.mesh_quality() == "very fine"
    finally:
        w.close()


def test_the_command_updates_the_panel(win):
    win.processor.run("meshquality Coarse")
    assert win.display_panel.mesh_quality() == "coarse"
