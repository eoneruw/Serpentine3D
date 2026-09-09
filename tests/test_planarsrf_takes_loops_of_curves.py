"""PlanarSrf reads a set of curves the way Rhino does.

Four lines drawn as a box, selected together, gave "Curve must be
closed" four times over and then "Planarsrf cancelled", because each
line was asked to close on its own. Curves that meet end to end are
joined into loops now, every closed loop becomes a surface, and a loop
lying inside another on the same plane is a hole in it.
"""

from __future__ import annotations

import pytest

from serpentine3d.core import geometry as g


def _box():
    return [g.make_line((0, 0, 0), (10, 0, 0)),
            g.make_line((10, 0, 0), (10, 10, 0)),
            g.make_line((10, 10, 0), (0, 10, 0)),
            g.make_line((0, 10, 0), (0, 0, 0))]


def test_four_lines_make_one_surface():
    faces = g.planar_faces_from_curves(_box())
    assert len(faces) == 1
    assert g.surface_area(faces[0]) == pytest.approx(100.0)


def test_a_closed_curve_still_works_on_its_own():
    faces = g.planar_faces_from_curves([g.make_circle((0, 0, 0), 2)])
    assert len(faces) == 1
    assert g.surface_area(faces[0]) == pytest.approx(12.566, abs=1e-2)


def test_a_loop_inside_another_is_a_hole():
    faces = g.planar_faces_from_curves(_box() + [g.make_circle((5, 5, 0), 2)])
    assert len(faces) == 1
    assert g.surface_area(faces[0]) == pytest.approx(100 - 12.566, abs=1e-2)


def test_separate_loops_are_separate_surfaces():
    tri = [g.make_line((20, 0, 0), (30, 0, 0)),
           g.make_line((30, 0, 0), (25, 10, 0)),
           g.make_line((25, 10, 0), (20, 0, 0))]
    faces = g.planar_faces_from_curves(_box() + tri)
    assert sorted(round(g.surface_area(f)) for f in faces) == [50, 100]


def test_curves_that_do_not_close_say_so():
    with pytest.raises(g.GeometryError, match="close"):
        g.planar_faces_from_curves(_box()[:3])


def test_the_command_takes_the_box(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    ids = [w.scene.add(line).id for line in _box()]
    w.selection.set(ids)
    msgs = []
    w.ctx.add_echo_listener(msgs.append)
    w.processor.run("planarsrf")
    assert not w.processor.busy
    assert [o.kind for o in w.scene.all()].count("surface") == 1
    assert not any("cancelled" in m for m in msgs), msgs
    w.mark_saved()
    w.close()
