"""Opening .usd / .usda / .usdc / .usdz files — meshes, as OBJ and STL make.

The app wrote USD and could not read it back, and .usdz is what an iPhone
scan or an AR Quick Look model comes as. The binary crate format inside
is Pixar's to parse, so reading goes through their `usd-core` package,
an optional extra: everything here skips when it is not installed,
except the test that says what the user is told in that case.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

from serpentine3d import fileio
from serpentine3d.core import geometry as g
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.fileio import usd


def _bbox(v):
    v = np.asarray(v, float)
    return v.min(axis=0), v.max(axis=0)


# --------------------------------------------------- without the library

def test_the_user_is_told_how_to_get_usd_support(monkeypatch, tmp_path):
    """No usd-core: a plain sentence with the pip command, not an
    ImportError from inside a C++ binding."""
    monkeypatch.setitem(sys.modules, "pxr", None)     # makes the import fail
    p = tmp_path / "thing.usdz"
    p.write_bytes(b"PK\x03\x04")
    with pytest.raises(usd.UsdError, match="pip install usd-core"):
        usd.import_usd(str(p))
    assert usd.usd_available() is False


def test_usd_is_offered_in_the_open_dialog():
    from tests.test_file_filters import _exts_in
    offered = _exts_in(fileio.import_filter())
    for ext in (".usd", ".usda", ".usdc", ".usdz"):
        assert ext in offered


# ------------------------------------------------------ with the library

try:
    import pxr
    from pxr import Gf, Usd, UsdGeom, UsdShade, UsdUtils
    HAVE_PXR = True
except ImportError:                                           # pragma: no cover
    HAVE_PXR = False

needs_pxr = pytest.mark.skipif(not HAVE_PXR, reason="usd-core not installed")


def _quad_stage(path, *, up="Y", meters_per_unit=1.0, translate=None,
                color=None, left_handed=False, material=None):
    """A unit quad in the XY plane at the origin, under an Xform."""
    st = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(st, getattr(UsdGeom.Tokens, up.lower()))
    UsdGeom.SetStageMetersPerUnit(st, meters_per_unit)
    xf = UsdGeom.Xform.Define(st, "/Root")
    if translate:
        xf.AddTranslateOp().Set(Gf.Vec3d(*translate))
    m = UsdGeom.Mesh.Define(st, "/Root/Quad")
    m.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    m.CreateFaceVertexCountsAttr([4])
    m.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    if left_handed:
        m.CreateOrientationAttr(UsdGeom.Tokens.leftHanded)
    if color:
        m.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    if material:
        mat = UsdShade.Material.Define(st, "/Root/Mat")
        sh = UsdShade.Shader.Define(st, "/Root/Mat/pbr")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", pxr.Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*material))
        mat.CreateSurfaceOutput().ConnectToSource(
            sh.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(mat)
    st.GetRootLayer().Save()
    return st


@needs_pxr
def test_a_y_up_metre_quad_arrives_z_up_in_millimetres(tmp_path):
    p = tmp_path / "quad.usda"
    _quad_stage(p)
    out = usd.import_usd(str(p), units="mm")
    assert len(out) == 1
    name, mesh, color = out[0]
    assert name == "Quad"
    assert isinstance(mesh, MeshShape)
    assert len(mesh.triangles) == 2, "the quad was fan-triangulated"
    lo, hi = _bbox(mesh.vertices)
    # USD's Y is our Z: the quad stands up in XZ
    assert lo == pytest.approx([0, 0, 0])
    assert hi == pytest.approx([1000, 0, 1000])
    assert color is None


@needs_pxr
def test_a_z_up_stage_passes_straight_through(tmp_path):
    p = tmp_path / "quad.usda"
    _quad_stage(p, up="Z")
    _, mesh, _ = usd.import_usd(str(p), units="m")[0]
    lo, hi = _bbox(mesh.vertices)
    assert hi == pytest.approx([1, 1, 0])


@pytest.mark.parametrize("mpu, units, size", [
    (1.0, "mm", 1000.0), (0.01, "mm", 10.0), (0.001, "mm", 1.0),
    (1.0, "in", 39.3701), (0.001, "m", 0.001)])
@needs_pxr
def test_meters_per_unit_and_document_units_both_count(tmp_path, mpu,
                                                       units, size):
    p = tmp_path / "quad.usda"
    _quad_stage(p, meters_per_unit=mpu)
    _, mesh, _ = usd.import_usd(str(p), units=units)[0]
    lo, hi = _bbox(mesh.vertices)
    assert hi[0] - lo[0] == pytest.approx(size, rel=1e-4)


@needs_pxr
def test_the_xform_chain_is_baked_in(tmp_path):
    p = tmp_path / "quad.usda"
    _quad_stage(p, translate=(2, 3, 4))
    _, mesh, _ = usd.import_usd(str(p), units="m")[0]
    lo, _hi = _bbox(mesh.vertices)
    # translate (2,3,4) in Y-up is (2,-4,3) here
    assert lo == pytest.approx([2, -4, 3])


@needs_pxr
def test_display_colour_wins_then_the_bound_material(tmp_path):
    p = tmp_path / "a.usda"
    _quad_stage(p, color=(1, 0, 0), material=(0, 0, 1))
    assert usd.import_usd(str(p))[0][2] == pytest.approx((1, 0, 0))
    q = tmp_path / "b.usda"
    _quad_stage(q, material=(0, 0, 1))
    assert usd.import_usd(str(q))[0][2] == pytest.approx((0, 0, 1))


@needs_pxr
def test_a_left_handed_mesh_is_turned_right_way_out(tmp_path):
    """Same index order, opposite orientation token: the author of the
    left-handed file meant the face the other way round, and the viewport
    derives normals right-handedly, so the winding is reversed to match."""
    p = tmp_path / "quad.usda"
    _quad_stage(p, up="Z", left_handed=True)
    q = tmp_path / "quad_rh.usda"
    _quad_stage(q, up="Z")
    lh = usd.import_usd(str(p))[0][1]
    rh = usd.import_usd(str(q))[0][1]

    def normal(mesh):
        v = mesh.vertices[mesh.triangles[0]]
        return np.cross(v[1] - v[0], v[2] - v[0])
    assert np.sign(normal(lh)[2]) == -np.sign(normal(rh)[2])


@needs_pxr
def test_a_usdz_package_opens_like_the_layer_inside_it(tmp_path):
    p = tmp_path / "quad.usda"
    _quad_stage(p, color=(0.2, 0.5, 0.9))
    z = tmp_path / "quad.usdz"
    assert UsdUtils.CreateNewUsdzPackage(str(p), str(z))
    out = usd.import_usd(str(z))
    assert [n for n, _, _ in out] == ["Quad"]
    assert out[0][2] == pytest.approx((0.2, 0.5, 0.9))


@needs_pxr
def test_a_usdc_binary_layer_opens(tmp_path):
    p = tmp_path / "quad.usdc"
    _quad_stage(p)
    assert len(usd.import_usd(str(p))) == 1


@needs_pxr
def test_invisible_and_inactive_prims_are_skipped(tmp_path):
    p = tmp_path / "s.usda"
    st = _quad_stage(p)
    hidden = UsdGeom.Mesh.Define(st, "/Root/Hidden")
    hidden.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    hidden.CreateFaceVertexCountsAttr([3])
    hidden.CreateFaceVertexIndicesAttr([0, 1, 2])
    hidden.MakeInvisible()
    off = UsdGeom.Mesh.Define(st, "/Root/Off")
    off.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    off.CreateFaceVertexCountsAttr([3])
    off.CreateFaceVertexIndicesAttr([0, 1, 2])
    off.GetPrim().SetActive(False)
    st.GetRootLayer().Save()
    assert [n for n, _, _ in usd.import_usd(str(p))] == ["Quad"]


@needs_pxr
def test_instances_are_expanded(tmp_path):
    """Two instances of one prototype are two objects where the instances
    stand, not one prototype nobody placed."""
    p = tmp_path / "inst.usda"
    st = Usd.Stage.CreateNew(str(p))
    UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(st, 1.0)
    st.CreateClassPrim("/Proto")            # a prototype, not a thing shown
    proto = UsdGeom.Mesh.Define(st, "/Proto/Tri")
    proto.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    proto.CreateFaceVertexCountsAttr([3])
    proto.CreateFaceVertexIndicesAttr([0, 1, 2])
    for i, x in enumerate((0.0, 10.0)):
        inst = UsdGeom.Xform.Define(st, f"/World/Inst{i}")
        inst.AddTranslateOp().Set(Gf.Vec3d(x, 0, 0))
        inst.GetPrim().GetReferences().AddInternalReference("/Proto")
        inst.GetPrim().SetInstanceable(True)
    st.GetRootLayer().Save()
    out = usd.import_usd(str(p), units="m")
    xs = sorted(_bbox(m.vertices)[0][0] for _, m, _ in out)
    assert [n for n, _, _ in out] == ["Tri", "Tri 02"]
    assert xs == pytest.approx([0.0, 10.0])


@needs_pxr
def test_a_malformed_mesh_is_skipped_not_fatal(tmp_path):
    p = tmp_path / "bad.usda"
    st = _quad_stage(p)
    bad = UsdGeom.Mesh.Define(st, "/Root/Bad")
    bad.CreatePointsAttr([(0, 0, 0), (1, 0, 0)])
    bad.CreateFaceVertexCountsAttr([3])
    bad.CreateFaceVertexIndicesAttr([0, 1, 7])          # index out of range
    st.GetRootLayer().Save()
    assert [n for n, _, _ in usd.import_usd(str(p))] == ["Quad"]


@needs_pxr
def test_junk_is_refused_with_the_file_name(tmp_path):
    p = tmp_path / "not really.usdz"
    p.write_bytes(b"<html>not a model</html>")
    with pytest.raises(usd.UsdError, match="not really.usdz"):
        usd.import_usd(str(p))


# --------------------------------------------------------- through fileio

@needs_pxr
def test_open_puts_meshes_in_the_scene_with_their_colour(tmp_path):
    p = tmp_path / "quad.usdz"
    src = tmp_path / "quad.usda"
    _quad_stage(src, color=(0.2, 0.6, 0.9))
    UsdUtils.CreateNewUsdzPackage(str(src), str(p))
    scene = Scene()
    assert fileio.import_file(scene, str(p)) == 1
    obj = scene.all()[0]
    assert obj.kind == "mesh"
    assert obj.name == "Quad"
    assert tuple(obj.color) == pytest.approx((0.2, 0.6, 0.9))


@needs_pxr
def test_what_the_app_exported_opens_again_at_the_same_size(tmp_path):
    """The writer declares Z-up and metersPerUnit=0.001, so the reader
    lands the box exactly where it was."""
    scene = Scene()
    scene.units = "mm"
    scene.add(g.make_box((0, 0, 0), 10, 20, 30), name="Block")
    p = tmp_path / "block.usda"
    fileio.export_file(scene, str(p))
    back = Scene()
    back.units = "mm"
    fileio.import_file(back, str(p))
    obj = back.all()[0]
    assert obj.name == "Block"
    lo, hi = _bbox(obj.shape.vertices)
    assert lo == pytest.approx([0, 0, 0], abs=1e-6)
    assert hi == pytest.approx([10, 20, 30], abs=1e-6)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
