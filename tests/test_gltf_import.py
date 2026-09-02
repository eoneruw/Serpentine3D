"""Opening .glb and .gltf files — meshes, as the OBJ and STL importers make.

glTF is the format the web and every asset store speak, and the one the
app already wrote; a model you exported for Blender could not be opened
again. Now it can, along with anything downloaded: nodes with transforms,
several primitives per mesh, strips and fans, quantised attributes,
buffers in the file or beside it.
"""

from __future__ import annotations

import base64
import json
import struct

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.fileio import gltf
from serpentine3d import fileio


def _bbox(v):
    v = np.asarray(v, float)
    return v.min(axis=0), v.max(axis=0)


# --------------------------------------------------- a hand-made document

_CUBE = np.array([
    [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], np.float32)
_CUBE_TRIS = np.array([
    [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
    [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]],
    np.uint16)


def _doc(*, positions=_CUBE, indices=_CUBE_TRIS, nodes=None, scene_nodes=None,
         mode=None, index_type=5123, materials=None, extra_prims=()):
    """A one-buffer glTF document; the buffer comes back as bytes."""
    blob = bytearray()
    views, accessors = [], []

    def add(arr, target):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        blob.extend(arr.tobytes())
        views.append({"buffer": 0, "byteOffset": off,
                      "byteLength": len(arr.tobytes()), "target": target})
        return len(views) - 1

    pv = add(positions, 34962)
    accessors.append({"bufferView": pv, "componentType": 5126,
                      "count": len(positions), "type": "VEC3",
                      "min": positions.min(0).tolist(),
                      "max": positions.max(0).tolist()})
    prim = {"attributes": {"POSITION": 0}}
    if indices is not None:
        iv = add(indices.astype({5123: np.uint16, 5125: np.uint32,
                                 5121: np.uint8}[index_type]).ravel(), 34963)
        accessors.append({"bufferView": iv, "componentType": index_type,
                          "count": int(indices.size), "type": "SCALAR"})
        prim["indices"] = 1
    if mode is not None:
        prim["mode"] = mode
    if materials:
        prim["material"] = 0
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": scene_nodes if scene_nodes is not None
                    else [0]}],
        "nodes": nodes or [{"name": "Cube", "mesh": 0}],
        "meshes": [{"name": "CubeMesh", "primitives": [prim, *extra_prims]}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    if materials:
        doc["materials"] = materials
    return doc, bytes(blob)


def _write_glb(path, doc, blob):
    js = json.dumps(doc).encode()
    while len(js) % 4:
        js += b" "
    while len(blob) % 4:
        blob += b"\0"
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + blob)


def _write_gltf(path, doc, blob, *, embed: bool):
    doc = dict(doc)
    if embed:
        doc["buffers"] = [{"byteLength": len(blob),
                           "uri": "data:application/octet-stream;base64,"
                                  + base64.b64encode(blob).decode()}]
    else:
        side = path.with_name("cube data.bin")
        side.write_bytes(blob)
        doc["buffers"] = [{"byteLength": len(blob), "uri": "cube%20data.bin"}]
    path.write_text(json.dumps(doc))


# ------------------------------------------------------------ the basics

def test_a_glb_cube_arrives_z_up_in_document_units(tmp_path):
    """A one-metre cube in glTF (Y-up, metres) is a 1000 mm cube here
    (Z-up, millimetres): glTF's Y is our Z, and the size is real."""
    p = tmp_path / "cube.glb"
    doc, blob = _doc()
    _write_glb(p, doc, blob)
    out = gltf.import_gltf(str(p), units="mm")
    assert len(out) == 1
    name, mesh, color = out[0]
    assert name == "Cube"
    assert isinstance(mesh, MeshShape)
    assert len(mesh.triangles) == 12
    lo, hi = _bbox(mesh.vertices)
    assert lo == pytest.approx([0, -1000, 0])
    assert hi == pytest.approx([1000, 0, 1000])
    assert color is None


@pytest.mark.parametrize("units, size", [("m", 1.0), ("cm", 100.0),
                                          ("in", 39.3701)])
def test_metres_become_whatever_the_document_uses(tmp_path, units, size):
    p = tmp_path / "cube.glb"
    _write_glb(p, *_doc())
    _name, mesh, _ = gltf.import_gltf(str(p), units=units)[0]
    lo, hi = _bbox(mesh.vertices)
    assert hi[0] - lo[0] == pytest.approx(size, rel=1e-4)


def test_a_gltf_with_its_buffer_embedded(tmp_path):
    p = tmp_path / "cube.gltf"
    _write_gltf(p, *_doc(), embed=True)
    out = gltf.import_gltf(str(p))
    assert len(out) == 1 and len(out[0][1].triangles) == 12


def test_a_gltf_with_its_buffer_beside_it(tmp_path):
    """The .bin is named by a URI, so a space in its name is escaped."""
    p = tmp_path / "cube.gltf"
    _write_gltf(p, *_doc(), embed=False)
    out = gltf.import_gltf(str(p))
    assert len(out) == 1 and len(out[0][1].triangles) == 12


def test_the_material_colour_comes_along(tmp_path):
    p = tmp_path / "cube.glb"
    _write_glb(p, *_doc(materials=[{"pbrMetallicRoughness": {
        "baseColorFactor": [0.8, 0.1, 0.1, 1.0]}}]))
    _name, _mesh, color = gltf.import_gltf(str(p))[0]
    assert color == pytest.approx((0.8, 0.1, 0.1))


# --------------------------------------------------------- scene graph

def test_node_transforms_are_baked_in(tmp_path):
    """A child node translated 2 m under a parent scaled by 3: the cube
    lands where a viewer would draw it, 6 m along and 3 m big."""
    nodes = [
        {"name": "Root", "scale": [3, 3, 3], "children": [1]},
        {"name": "Child", "translation": [2, 0, 0], "mesh": 0},
    ]
    p = tmp_path / "cube.glb"
    _write_glb(p, *_doc(nodes=nodes, scene_nodes=[0]))
    out = gltf.import_gltf(str(p), units="m")
    assert [n for n, _, _ in out] == ["Child"]
    lo, hi = _bbox(out[0][1].vertices)
    assert lo == pytest.approx([6, -3, 0])
    assert hi == pytest.approx([9, 0, 3])


def test_a_matrix_node_and_a_quaternion_node_agree(tmp_path):
    """90° about glTF's Y, once as a quaternion and once as the matrix."""
    s = np.sqrt(0.5)
    quat = [{"name": "Q", "rotation": [0, s, 0, s], "mesh": 0}]
    mat = [{"name": "M", "mesh": 0,
            "matrix": [0, 0, -1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1]}]
    got = []
    for i, nodes in enumerate((quat, mat)):
        p = tmp_path / f"cube{i}.glb"
        _write_glb(p, *_doc(nodes=nodes))
        got.append(np.sort(gltf.import_gltf(str(p), units="m")[0][1].vertices,
                           axis=0))
    assert got[0] == pytest.approx(got[1], abs=1e-9)


def test_a_mirrored_node_keeps_its_faces_outward(tmp_path):
    nodes = [{"name": "Mirror", "scale": [-1, 1, 1], "mesh": 0}]
    p = tmp_path / "cube.glb"
    _write_glb(p, *_doc(nodes=nodes))
    mesh = gltf.import_gltf(str(p), units="m")[0][1]
    centre = mesh.vertices.mean(axis=0)
    v = mesh.vertices[mesh.triangles]
    normals = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    outward = np.einsum("ij,ij->i", normals, v[:, 0] - centre)
    assert (outward > 0).all(), "a mirror flips winding; it was put back"


def test_the_same_mesh_under_two_nodes_is_two_objects(tmp_path):
    nodes = [{"name": "Wheel", "mesh": 0},
             {"name": "Wheel", "mesh": 0, "translation": [5, 0, 0]}]
    p = tmp_path / "cube.glb"
    _write_glb(p, *_doc(nodes=nodes, scene_nodes=[0, 1]))
    names = [n for n, _, _ in gltf.import_gltf(str(p))]
    assert names == ["Wheel", "Wheel 02"]


def test_only_the_default_scene_is_read(tmp_path):
    doc, blob = _doc(nodes=[{"name": "Shown", "mesh": 0},
                            {"name": "Hidden", "mesh": 0}])
    doc["scenes"] = [{"nodes": [0]}, {"nodes": [1]}]
    p = tmp_path / "cube.glb"
    _write_glb(p, doc, blob)
    assert [n for n, _, _ in gltf.import_gltf(str(p))] == ["Shown"]


# ---------------------------------------------------- primitive shapes

def test_a_triangle_strip_is_unrolled(tmp_path):
    quad = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], np.float32)
    p = tmp_path / "strip.glb"
    _write_glb(p, *_doc(positions=quad, indices=np.arange(4, dtype=np.uint16),
                        mode=5))
    mesh = gltf.import_gltf(str(p), units="m")[0][1]
    assert len(mesh.triangles) == 2
    v = mesh.vertices[mesh.triangles]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    assert np.sign(n[0]) == pytest.approx(np.sign(n[1])), \
        "both triangles wind the same way once the strip is unrolled"


def test_a_triangle_fan_is_unrolled(tmp_path):
    hexa = np.array([[0, 0, 0]] + [[np.cos(a), np.sin(a), 0]
                                   for a in np.linspace(0, 2 * np.pi, 7)[:-1]],
                    np.float32)
    p = tmp_path / "fan.glb"
    _write_glb(p, *_doc(positions=hexa, indices=np.arange(7, dtype=np.uint16),
                        mode=6))
    assert len(gltf.import_gltf(str(p))[0][1].triangles) == 5


def test_unindexed_triangles(tmp_path):
    tri = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
    p = tmp_path / "tri.glb"
    _write_glb(p, *_doc(positions=tri, indices=None))
    assert len(gltf.import_gltf(str(p))[0][1].triangles) == 1


def test_lines_and_points_are_skipped_not_choked_on(tmp_path):
    doc, blob = _doc(extra_prims=[{"attributes": {"POSITION": 0}, "mode": 1}])
    p = tmp_path / "cube.glb"
    _write_glb(p, doc, blob)
    assert len(gltf.import_gltf(str(p))) == 1


def test_uint32_and_uint8_indices(tmp_path):
    for ctype in (5125, 5121):
        p = tmp_path / f"cube{ctype}.glb"
        _write_glb(p, *_doc(index_type=ctype))
        assert len(gltf.import_gltf(str(p))[0][1].triangles) == 12


def test_a_strided_interleaved_buffer(tmp_path):
    """Positions interleaved with normals, as many exporters pack them."""
    inter = np.zeros((8, 6), np.float32)
    inter[:, :3] = _CUBE
    doc, blob = _doc(positions=inter)      # 24-byte rows, POSITION first
    doc["bufferViews"][0]["byteStride"] = 24
    doc["accessors"][0]["count"] = 8
    p = tmp_path / "cube.glb"
    _write_glb(p, doc, blob)
    mesh = gltf.import_gltf(str(p), units="m")[0][1]
    lo, hi = _bbox(mesh.vertices)
    assert hi - lo == pytest.approx([1, 1, 1])


def test_quantised_positions_are_scaled_back(tmp_path):
    """KHR_mesh_quantization: normalised uint16 stands for [0, 1]."""
    doc, blob = _doc()
    q = (_CUBE * 65535).astype(np.uint16)
    blob = q.tobytes() + blob[len(_CUBE.tobytes()):]
    doc["bufferViews"][0]["byteLength"] = len(q.tobytes())
    # the index view followed the positions: shift it by the size change
    shift = len(_CUBE.tobytes()) - len(q.tobytes())
    doc["bufferViews"][1]["byteOffset"] -= shift
    doc["accessors"][0].update({"componentType": 5123, "normalized": True})
    p = tmp_path / "q.glb"
    _write_glb(p, doc, blob)
    mesh = gltf.import_gltf(str(p), units="m")[0][1]
    lo, hi = _bbox(mesh.vertices)
    assert hi - lo == pytest.approx([1, 1, 1], abs=1e-4)


# ------------------------------------------------------------ refusals

def test_draco_is_refused_with_a_reason(tmp_path):
    doc, blob = _doc()
    doc["extensionsRequired"] = ["KHR_draco_mesh_compression"]
    p = tmp_path / "draco.glb"
    _write_glb(p, doc, blob)
    with pytest.raises(gltf.GltfError, match="Draco"):
        gltf.import_gltf(str(p))


def test_a_missing_sidecar_bin_is_named(tmp_path):
    """A .gltf downloaded without its .bin is the commonest broken file."""
    p = tmp_path / "cube.gltf"
    _write_gltf(p, *_doc(), embed=False)
    p.with_name("cube data.bin").unlink()
    with pytest.raises(gltf.GltfError, match="cube data.bin"):
        gltf.import_gltf(str(p))


def test_garbage_is_refused_with_a_reason(tmp_path):
    p = tmp_path / "nope.gltf"
    p.write_bytes(b"\x00\x01not json")
    with pytest.raises(gltf.GltfError, match="Not a glTF"):
        gltf.import_gltf(str(p))


# --------------------------------------------------------- through fileio

def test_open_puts_meshes_in_the_scene_with_their_colour(tmp_path):
    p = tmp_path / "cube.glb"
    _write_glb(p, *_doc(materials=[{"pbrMetallicRoughness": {
        "baseColorFactor": [0.2, 0.6, 0.9, 1.0]}}]))
    scene = Scene()
    assert fileio.import_file(scene, str(p)) == 1
    obj = scene.all()[0]
    assert obj.kind == "mesh"
    assert obj.name == "Cube"
    assert tuple(obj.color) == pytest.approx((0.2, 0.6, 0.9))


def test_what_the_app_exported_opens_again(tmp_path):
    """The writer puts document units in the file unscaled, so read it back
    as metres to compare like with like; the shape must survive intact."""
    scene = Scene()
    scene.add(g.make_box((0, 0, 0), 10, 20, 30), name="Block")
    p = tmp_path / "block.glb"
    fileio.export_file(scene, str(p))
    out = gltf.import_gltf(str(p), units="m")
    assert [n for n, _, _ in out] == ["Block"]
    lo, hi = _bbox(out[0][1].vertices)
    assert lo == pytest.approx([0, 0, 0], abs=1e-6)
    assert hi == pytest.approx([10, 20, 30], abs=1e-6)


def test_glb_is_offered_in_the_open_dialog():
    from tests.test_file_filters import _exts_in
    offered = _exts_in(fileio.import_filter())
    assert ".glb" in offered and ".gltf" in offered


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
