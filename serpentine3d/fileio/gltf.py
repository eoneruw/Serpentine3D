"""glTF 2.0 — binary (.glb) export and import, and .gltf import — hand-written,
no dependencies.

Export: one mesh node per object, tessellated, with per-object base colours.
Import: every triangle primitive under the default scene, its node transform
baked in, as one MeshShape each. Y-up conversion (glTF convention) from and
to Serpentine3D's Z-up."""

from __future__ import annotations

import base64
import json
import os
import struct

import numpy as np

from ..core.mesh import MeshShape
from ..core.tessellate import tessellate

# Z-up -> Y-up: (x, y, z) -> (x, z, -y)
_ZUP_TO_YUP = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], np.float32)
# and back: (x, y, z) -> (x, -z, y)
_YUP_TO_ZUP = _ZUP_TO_YUP.T.astype(np.float64)

_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


def export_glb(scene, path: str, only_ids: list | None = None):
    objs = scene.all()
    if only_ids:
        objs = [o for o in objs if o.id in only_ids]

    buffers = bytearray()
    accessors, buffer_views, meshes, nodes, materials = [], [], [], [], []

    def add_view(data: bytes, target: int | None) -> int:
        # 4-byte alignment
        while len(buffers) % 4:
            buffers.append(0)
        offset = len(buffers)
        buffers.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target:
            view["target"] = target
        buffer_views.append(view)
        return len(buffer_views) - 1

    for obj in objs:
        mesh = tessellate(obj.shape)
        if not mesh.has_faces:
            continue
        verts = (mesh.vertices @ _ZUP_TO_YUP.T).astype(np.float32)
        norms = (mesh.normals @ _ZUP_TO_YUP.T).astype(np.float32)
        idx = mesh.triangles.astype(np.uint32).ravel()

        v_view = add_view(verts.tobytes(), 34962)
        n_view = add_view(norms.tobytes(), 34962)
        i_view = add_view(idx.tobytes(), 34963)

        accessors.append({
            "bufferView": v_view, "componentType": 5126,
            "count": len(verts), "type": "VEC3",
            "min": [float(v) for v in verts.min(axis=0)],
            "max": [float(v) for v in verts.max(axis=0)],
        })
        v_acc = len(accessors) - 1
        accessors.append({"bufferView": n_view, "componentType": 5126,
                          "count": len(norms), "type": "VEC3"})
        n_acc = len(accessors) - 1
        accessors.append({"bufferView": i_view, "componentType": 5125,
                          "count": int(len(idx)), "type": "SCALAR"})
        i_acc = len(accessors) - 1

        # The material's own colour where it has one: the rest of this block
        # is that material, and pairing its metal and roughness with the
        # object's display colour exports half of each.
        color = scene.render_color_of(obj)
        m = obj.material or {}
        opacity = float(m.get("opacity", 1.0))
        mat = {
            "name": f"{obj.name} material",
            "pbrMetallicRoughness": {
                "baseColorFactor": [color[0], color[1], color[2], opacity],
                "metallicFactor": float(m.get("metallic", 0.0)),
                "roughnessFactor": float(m.get("roughness", 0.8)),
            },
        }
        if opacity < 1.0:
            mat["alphaMode"] = "BLEND"
        materials.append(mat)
        meshes.append({
            "name": obj.name,
            "primitives": [{
                "attributes": {"POSITION": v_acc, "NORMAL": n_acc},
                "indices": i_acc,
                "material": len(materials) - 1,
            }],
        })
        nodes.append({"name": obj.name, "mesh": len(meshes) - 1})

    doc = {
        "asset": {"version": "2.0", "generator": "Serpentine3D"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes))),
                    "name": "Serpentine3D scene"}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(buffers)}],
    }

    json_bytes = json.dumps(doc, separators=(",", ":")).encode()
    while len(json_bytes) % 4:
        json_bytes += b" "
    bin_bytes = bytes(buffers)
    while len(bin_bytes) % 4:
        bin_bytes += b"\x00"

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", _MAGIC, 2, total))
        f.write(struct.pack("<II", len(json_bytes), _CHUNK_JSON))
        f.write(json_bytes)
        f.write(struct.pack("<II", len(bin_bytes), _CHUNK_BIN))
        f.write(bin_bytes)


# ============================================================== import

class GltfError(ValueError):
    """The file is not glTF we can read; the message says why."""


# glTF is in metres by specification. Serpentine documents are in whatever
# the user chose, so a downloaded car arrives 4.5 m long rather than 4.5 mm.
_METRES_TO = {"mm": 1000.0, "cm": 100.0, "m": 1.0,
              "in": 39.37007874015748, "ft": 3.280839895013123}

_COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
              5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
          "MAT2": 4, "MAT3": 9, "MAT4": 16}
_TRIANGLES, _TRIANGLE_STRIP, _TRIANGLE_FAN = 4, 5, 6


def import_gltf(path: str, units: str = "mm") -> list:
    """Returns [(name, MeshShape, color_or_None)], one per triangle primitive.

    Reads .glb (binary container) and .gltf (JSON, with buffers alongside
    or embedded as data URIs). Every node in the default scene is walked,
    its transform chain baked into the vertices, so what you see in a
    viewer is what you get. Points, lines, and Draco-compressed geometry
    are not read; the last raises, the others are skipped.
    """
    doc, bin_chunk = _read_container(path)
    if not doc.get("asset", {}).get("version", "2.0").startswith("2"):
        raise GltfError("Only glTF 2.0 is supported "
                        f"(file says {doc['asset'].get('version')!r}).")
    for ext in doc.get("extensionsRequired", ()):
        if ext == "KHR_draco_mesh_compression":
            raise GltfError("This glTF uses Draco compression, which is not "
                            "supported — export it uncompressed.")
    buffers = _load_buffers(doc, bin_chunk, os.path.dirname(path))
    read = _AccessorReader(doc, buffers)
    scale = _METRES_TO.get(units, 1000.0)
    base = os.path.splitext(os.path.basename(path))[0] or "gltf"

    out = []
    seen: dict[str, int] = {}
    for node_index, matrix in _walk_nodes(doc):
        node = doc["nodes"][node_index]
        mesh_index = node.get("mesh")
        if mesh_index is None:
            continue
        mesh = doc["meshes"][mesh_index]
        mesh_name = node.get("name") or mesh.get("name") or base
        for prim in mesh.get("primitives", ()):
            got = _primitive(prim, read, matrix, scale)
            if got is None:
                continue
            verts, tris = got
            color = _material_color(doc, prim.get("material"))
            # the same mesh under several nodes, or several primitives in
            # one mesh, would all share a name; number the repeats
            n = seen.get(mesh_name, 0) + 1
            seen[mesh_name] = n
            name = mesh_name if n == 1 else f"{mesh_name} {n:02d}"
            out.append((name, MeshShape(verts, tris), color))
    return out


def _read_container(path: str):
    """(document dict, embedded BIN chunk or None) for .glb or .gltf."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == b"glTF":
        if len(data) < 12:
            raise GltfError("Truncated .glb header.")
        magic, version, total = struct.unpack_from("<III", data, 0)
        if version != 2:
            raise GltfError(f"Only .glb version 2 is supported (got {version}).")
        pos, doc, bin_chunk = 12, None, None
        while pos + 8 <= min(total, len(data)):
            length, kind = struct.unpack_from("<II", data, pos)
            chunk = data[pos + 8:pos + 8 + length]
            if kind == _CHUNK_JSON:
                doc = json.loads(chunk.decode("utf-8"))
            elif kind == _CHUNK_BIN and bin_chunk is None:
                bin_chunk = chunk
            pos += 8 + length
        if doc is None:
            raise GltfError("The .glb has no JSON chunk.")
        return doc, bin_chunk
    try:
        return json.loads(data.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GltfError(f"Not a glTF file: {exc}") from exc


def _load_buffers(doc, bin_chunk, folder: str) -> list[bytes]:
    out = []
    for i, buf in enumerate(doc.get("buffers", ())):
        uri = buf.get("uri")
        if uri is None:
            if bin_chunk is None:
                raise GltfError(f"Buffer {i} has no data (no uri, no BIN).")
            out.append(bin_chunk)
        elif uri.startswith("data:"):
            _header, _, payload = uri.partition(",")
            out.append(base64.b64decode(payload))
        else:
            from urllib.parse import unquote
            side = os.path.join(folder, unquote(uri))
            if not os.path.exists(side):
                raise GltfError(
                    f"The .gltf needs {os.path.basename(side)} beside it "
                    "and it is not there — copy the whole folder, or use "
                    "the .glb form.")
            with open(side, "rb") as f:
                out.append(f.read())
    return out


class _AccessorReader:
    """Accessors as numpy arrays, byte strides and normalisation honoured."""

    def __init__(self, doc, buffers):
        self.doc = doc
        self.buffers = buffers

    def __call__(self, index: int) -> np.ndarray:
        acc = self.doc["accessors"][index]
        if "sparse" in acc:
            raise GltfError("Sparse accessors are not supported.")
        dtype = np.dtype(_COMPONENT[acc["componentType"]])
        width = _WIDTH[acc["type"]]
        count = int(acc["count"])
        if "bufferView" not in acc:
            arr = np.zeros((count, width), dtype)
        else:
            view = self.doc["bufferViews"][acc["bufferView"]]
            data = self.buffers[view["buffer"]]
            start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            row = dtype.itemsize * width
            stride = view.get("byteStride") or row
            if stride == row:
                arr = np.frombuffer(data, dtype, count * width, start)
                arr = arr.reshape(count, width)
            else:
                raw = np.frombuffer(data, np.uint8,
                                    stride * (count - 1) + row, start)
                strided = np.lib.stride_tricks.as_strided(
                    raw, shape=(count, row), strides=(stride, 1))
                arr = np.ascontiguousarray(strided).view(dtype)
                arr = arr.reshape(count, width)
        if acc.get("normalized") and dtype.kind in "iu":
            # KHR_mesh_quantization: integers standing for [0,1] or [-1,1]
            limit = float(np.iinfo(dtype).max)
            arr = np.maximum(arr.astype(np.float64) / limit, -1.0)
        return arr


def _walk_nodes(doc):
    """(node index, world matrix) for every node reachable from the
    default scene — or from every root when the file names no scene."""
    nodes = doc.get("nodes", [])
    scenes = doc.get("scenes", [])
    if scenes:
        which = doc.get("scene", 0)
        roots = scenes[min(which, len(scenes) - 1)].get("nodes", [])
    else:
        children = {c for n in nodes for c in n.get("children", ())}
        roots = [i for i in range(len(nodes)) if i not in children]
    stack = [(r, np.eye(4)) for r in reversed(roots)]
    seen = set()
    while stack:
        index, parent = stack.pop()
        if index in seen or index >= len(nodes):
            continue                    # a cycle, or a dangling index
        seen.add(index)
        world = parent @ _local_matrix(nodes[index])
        yield index, world
        for child in reversed(nodes[index].get("children", ())):
            stack.append((child, world))


def _local_matrix(node) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], np.float64).reshape(4, 4).T
    m = np.eye(4)
    t = node.get("translation")
    r = node.get("rotation")
    s = node.get("scale")
    if s:
        m = np.diag([s[0], s[1], s[2], 1.0]) @ m
    if r:
        x, y, z, w = r
        rot = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
        rm = np.eye(4)
        rm[:3, :3] = rot
        m = rm @ m
    if t:
        tm = np.eye(4)
        tm[:3, 3] = t
        m = tm @ m
    return m


def _primitive(prim, read, matrix, scale):
    """(vertices in Z-up document units, triangles) or None to skip."""
    mode = prim.get("mode", _TRIANGLES)
    if mode not in (_TRIANGLES, _TRIANGLE_STRIP, _TRIANGLE_FAN):
        return None                     # points and lines: not a mesh
    if "POSITION" not in prim.get("attributes", {}):
        return None
    pos = read(prim["attributes"]["POSITION"]).astype(np.float64)
    if "indices" in prim:
        idx = read(prim["indices"]).ravel().astype(np.int64)
    else:
        idx = np.arange(len(pos), dtype=np.int64)
    tris = _to_triangles(idx, mode)
    if not len(tris):
        return None
    # bake the node transform, then Y-up -> Z-up, then metres -> units
    hom = np.hstack([pos, np.ones((len(pos), 1))])
    world = (hom @ matrix.T)[:, :3]
    verts = (world @ _YUP_TO_ZUP.T) * scale
    # a mirrored transform flips the winding: put it back so the normals
    # the viewport derives still point out
    if np.linalg.det(matrix[:3, :3]) < 0:
        tris = tris[:, [0, 2, 1]]
    return verts, tris.astype(np.uint32)


def _to_triangles(idx: np.ndarray, mode: int) -> np.ndarray:
    if mode == _TRIANGLES:
        n = len(idx) - len(idx) % 3
        return idx[:n].reshape(-1, 3)
    if len(idx) < 3:
        return np.zeros((0, 3), np.int64)
    if mode == _TRIANGLE_STRIP:
        a, b, c = idx[:-2], idx[1:-1], idx[2:]
        tris = np.stack([a, b, c], axis=1)
        tris[1::2] = tris[1::2][:, [1, 0, 2]]      # every other one flips
        return tris
    # fan
    return np.stack([np.full(len(idx) - 2, idx[0]), idx[1:-1], idx[2:]],
                    axis=1)


def _material_color(doc, index):
    if index is None:
        return None
    try:
        pbr = doc["materials"][index].get("pbrMetallicRoughness", {})
        r, g, b = pbr.get("baseColorFactor", [1, 1, 1, 1])[:3]
    except (IndexError, KeyError, ValueError, TypeError):
        return None
    return (float(r), float(g), float(b))
