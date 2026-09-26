"""A screenshot for the assistant must not move the user's viewport.

The assistant looks at the model after every build, and it used to do
that by turning the user's own pane — isometric, shaded, zoom extents —
and leaving it there. The perspective view you were working in was gone
every time it checked its work. A look is not a move: screenshot now
takes a view of its own, renders through a copy of the camera offscreen,
and the pane never finds out.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.ai import tools as T
from serpentine3d.core import geometry as g


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")


@pytest.fixture
def api():
    QApplication.instance() or QApplication([])
    from serpentine3d.api import SerpApi
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    yield SerpApi(w)
    w.mark_saved()
    w.close()


def _gl(api):
    if api.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")


def test_a_screenshot_with_a_view_leaves_the_pane_where_it_was(api):
    _gl(api)
    api.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="Box")
    vp = api.viewport
    vp.set_view("perspective")
    vp.set_display_mode("wireframe")
    vp.camera.azimuth, vp.camera.elevation = 0.7, 0.2      # off any preset
    before = vp.camera.state()

    result = api.screenshot(width=320, view="isometric",
                            display_mode="shaded", zoom_extents=True)

    assert result["width"] == 320
    assert vp.camera.state() == before, "the user's camera moved"
    assert vp.display_mode == "wireframe", "the user's display mode changed"


def test_the_picture_is_of_the_view_asked_for(api):
    """Top of a flat plate is a full rectangle; from the front it is a
    sliver. Enough pixels of the object's colour tell the two apart."""
    _gl(api)
    o = api.scene.add(g.make_box((0, 0, 0), 40, 40, 1), name="Plate")
    api.scene.update_many([o.id], color=(0.9, 0.1, 0.1))

    def red_pixels(view):
        r = api.screenshot(width=200, view=view, zoom_extents=True)
        from PySide6.QtGui import QImage
        img = QImage(r["path"])
        return sum(1 for y in range(0, img.height(), 4)
                   for x in range(0, img.width(), 4)
                   if (c := img.pixelColor(x, y)).red() > c.blue() + 60)

    assert red_pixels("top") > 4 * red_pixels("front")


def test_a_screenshot_with_nothing_asked_is_still_the_users_view(api):
    _gl(api)
    api.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="Box")
    r = api.screenshot(width=200)
    assert r["width"] == 200


def test_an_unknown_view_is_an_error_not_a_crash(api):
    from serpentine3d.api import ApiError
    api.scene.add(g.make_box((0, 0, 0), 10, 10, 10), name="Box")
    with pytest.raises(ApiError):
        api.screenshot(view="sideways")


def test_the_tool_passes_the_view_through(api):
    calls = {}

    def fake(width=None, view=None, display_mode=None, zoom_extents=False):
        calls.update(width=width, view=view, display_mode=display_mode,
                     zoom_extents=zoom_extents)
        import tempfile
        from PySide6.QtGui import QImage
        path = tempfile.mkstemp(suffix=".png")[1]
        QImage(4, 4, QImage.Format.Format_RGB32).save(path)
        return {"path": path, "width": 4, "height": 4}

    api.screenshot = fake
    T.dispatch(api, "screenshot", {"view": "perspective",
                                   "zoom_extents": True})
    assert calls == {"width": 1024, "view": "perspective",
                     "display_mode": None, "zoom_extents": True}


def test_the_tools_tell_the_model_which_one_moves_the_user():
    by_name = {t["name"]: t for t in T.TOOLS}
    assert "view" in by_name["screenshot"]["input_schema"]["properties"]
    assert "leave the user's viewport" in by_name["screenshot"]["description"]
    assert "user's viewport" in by_name["viewport"]["description"]
    assert T.summarize_call("screenshot", {"view": "top"}) == "looking (top)"
