"""USD — export as plain-text .usda with no dependencies; import of
.usd / .usda / .usdc / .usdz through Pixar's own library, when installed.

Export: one UsdGeomMesh per object under a root Xform, with display
colours. USD is Y-up by default; we declare Z-up so coordinates pass
through.

Import: every Mesh prim on the stage, its world transform baked in, as one
MeshShape each. The binary crate format (.usdc, and every .usdz) is not
something to parse by hand, so reading needs `usd-core` — an optional
extra (`pip install serpentine3d[usd]`), a large wheel that nobody who
only wants a NURBS modeller should have to carry."""

from __future__ import annotations

import os
import re

import numpy as np

from ..core.mesh import MeshShape
from ..core.tessellate import tessellate


def _safe(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not out or out[0].isdigit():
        out = "_" + out
    return out


def export_usda(scene, path: str, only_ids: list | None = None):
    objs = scene.all()
    if only_ids:
        objs = [o for o in objs if o.id in only_ids]

    lines = [
        "#usda 1.0",
        "(",
        '    upAxis = "Z"',
        '    metersPerUnit = 0.001',
        '    defaultPrim = "Serpentine3D"',
        ")",
        "",
        'def Xform "Serpentine3D"',
        "{",
    ]
    used = set()
    mat_blocks = []
    for obj in objs:
        mesh = tessellate(obj.shape)
        if not mesh.has_faces:
            continue
        name = _safe(obj.name)
        while name in used:
            name += "_"
        used.add(name)
        # What a renderer should show, which is the material's colour when it
        # has one — same reasoning as the glTF exporter.
        color = scene.render_color_of(obj)
        pts = ", ".join(f"({v[0]:.6g}, {v[1]:.6g}, {v[2]:.6g})"
                        for v in mesh.vertices)
        counts = ", ".join("3" for _ in mesh.triangles)
        indices = ", ".join(str(int(i)) for t in mesh.triangles for i in t)
        m = obj.material or {}
        lines.extend([
            f'    def Mesh "{name}" (',
            f'        prepend apiSchemas = ["MaterialBindingAPI"]',
            "    )",
            "    {",
            f"        point3f[] points = [{pts}]",
            f"        int[] faceVertexCounts = [{counts}]",
            f"        int[] faceVertexIndices = [{indices}]",
            f"        color3f[] primvars:displayColor = "
            f"[({color[0]:.4g}, {color[1]:.4g}, {color[2]:.4g})]",
            '        uniform token subdivisionScheme = "none"',
            f"        rel material:binding = "
            f"</Serpentine3D/Materials/{name}_mat>",
            "    }",
        ])
        mat_blocks.append((name, color, m))
    if mat_blocks:
        lines.append('    def Scope "Materials"')
        lines.append("    {")
        for name, color, m in mat_blocks:
            lines.extend([
                f'        def Material "{name}_mat"',
                "        {",
                "            token outputs:surface.connect = "
                f"</Serpentine3D/Materials/{name}_mat/pbr.outputs:surface>",
                f'            def Shader "pbr"',
                "            {",
                '                uniform token info:id = '
                '"UsdPreviewSurface"',
                f"                color3f inputs:diffuseColor = "
                f"({color[0]:.4g}, {color[1]:.4g}, {color[2]:.4g})",
                f"                float inputs:metallic = "
                f"{float(m.get('metallic', 0.0)):.3g}",
                f"                float inputs:roughness = "
                f"{float(m.get('roughness', 0.8)):.3g}",
                f"                float inputs:opacity = "
                f"{float(m.get('opacity', 1.0)):.3g}",
                "                token outputs:surface",
                "            }",
                "        }",
            ])
        lines.append("    }")
    lines.append("}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ============================================================== import

class UsdError(ValueError):
    """The file is not USD we can read; the message says why."""


_INSTALL_HINT = ("Opening USD needs Pixar's usd-core package: "
                 "pip install usd-core   (or serpentine3d[usd])")

_METRES_TO = {"mm": 1000.0, "cm": 100.0, "m": 1.0,
              "in": 39.37007874015748, "ft": 3.280839895013123}
# USD's default is Y-up: (x, y, z) -> (x, -z, y)
_YUP_TO_ZUP = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], np.float64)


def _pxr():
    try:
        from pxr import Usd, UsdGeom, UsdShade, Gf  # noqa: F401
    except ImportError as exc:
        raise UsdError(_INSTALL_HINT) from exc
    return Usd, UsdGeom, UsdShade


def usd_available() -> bool:
    try:
        _pxr()
    except UsdError:
        return False
    return True


def import_usd(path: str, units: str = "mm") -> list:
    """Returns [(name, MeshShape, color_or_None)], one per Mesh prim.

    Reads .usda, .usdc, .usd and .usdz (the zip that iPhone scans and AR
    Quick Look models come as). Instances are expanded, inactive and
    invisible prims skipped, polygons triangulated, the stage's up axis
    and metersPerUnit honoured so the model arrives Z-up at real size.
    """
    Usd, UsdGeom, UsdShade = _pxr()
    if not os.path.exists(path):
        raise UsdError(f"No such file: {path}")
    try:
        stage = Usd.Stage.Open(path)
    except Exception as exc:                                  # noqa: BLE001
        # pxr raises Tf.ErrorException with a C++ source location in it;
        # the file name is the part anyone needs
        raise UsdError(
            f"Not a USD file we can open: {os.path.basename(path)}") from exc
    if stage is None:
        raise UsdError(f"Not a USD file we can open: {os.path.basename(path)}")
    scale = (UsdGeom.GetStageMetersPerUnit(stage) or 1.0) \
        * _METRES_TO.get(units, 1000.0)
    y_up = UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z
    time = Usd.TimeCode.EarliestTime()

    out = []
    seen: dict[str, int] = {}
    it = iter(Usd.PrimRange.Stage(
        stage, Usd.TraverseInstanceProxies(Usd.PrimIsActive
                                           & Usd.PrimIsDefined
                                           & ~Usd.PrimIsAbstract)))
    for prim in it:
        imageable = UsdGeom.Imageable(prim)
        if imageable and imageable.ComputeVisibility(time) \
                == UsdGeom.Tokens.invisible:
            it.PruneChildren()
            continue
        if not prim.IsA(UsdGeom.Mesh):
            continue
        got = _mesh(UsdGeom.Mesh(prim), time)
        if got is None:
            continue
        verts, tris = got
        xf = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(time)
        m = np.array([[xf[r][c] for c in range(4)] for r in range(4)])
        # Gf matrices are row-vector: p' = p @ M
        verts = (np.hstack([verts, np.ones((len(verts), 1))]) @ m)[:, :3]
        if np.linalg.det(m[:3, :3]) < 0:
            tris = tris[:, [0, 2, 1]]
        if y_up:
            verts = verts @ _YUP_TO_ZUP.T
        verts = verts * scale
        name = prim.GetName()
        n = seen.get(name, 0) + 1
        seen[name] = n
        if n > 1:
            name = f"{name} {n:02d}"
        out.append((name, MeshShape(verts, tris.astype(np.uint32)),
                    _color(prim, UsdGeom, UsdShade, time)))
    return out


def _mesh(mesh, time):
    """(points, triangles) or None for an empty or degenerate mesh."""
    pts = mesh.GetPointsAttr().Get(time)
    counts = mesh.GetFaceVertexCountsAttr().Get(time)
    idx = mesh.GetFaceVertexIndicesAttr().Get(time)
    if not pts or not counts or not idx:
        return None
    verts = np.asarray(pts, np.float64).reshape(-1, 3)
    counts = np.asarray(counts, np.int64)
    idx = np.asarray(idx, np.int64)
    if counts.sum() != len(idx) or (idx >= len(verts)).any() or (idx < 0).any():
        return None                     # a malformed mesh: skip, not crash
    tris = _triangulate(counts, idx)
    if not len(tris):
        return None
    orient = mesh.GetOrientationAttr().Get(time)
    if orient == "leftHanded":
        tris = tris[:, [0, 2, 1]]
    return verts, tris


def _triangulate(counts: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Fan-triangulate every polygon; quads are the common case."""
    if (counts == 3).all():
        return idx.reshape(-1, 3)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    tris = []
    for start, n in zip(starts, counts):
        if n < 3:
            continue
        poly = idx[start:start + n]
        tris.append(np.stack([np.full(n - 2, poly[0]), poly[1:-1], poly[2:]],
                             axis=1))
    return np.vstack(tris) if tris else np.zeros((0, 3), np.int64)


def _bound_material(prim, UsdShade):
    """The material bound to a prim, by the book when the book was
    followed and by the relationship when it was not.

    Files converted from glTF (Sketchfab exports, for one) write the
    material:binding relationship without applying the MaterialBindingAPI
    schema. Pixar's resolver then prints a warning per prim and gives up,
    and a hundred-part car is a hundred warnings and no colours. The
    relationship is right there, so it is read directly in that case.
    """
    if prim.HasAPI(UsdShade.MaterialBindingAPI):
        mat, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        return mat if mat else None
    rel = prim.GetRelationship("material:binding")
    if not rel:
        return None
    for target in rel.GetTargets():
        found = prim.GetStage().GetPrimAtPath(target)
        if found and found.IsA(UsdShade.Material):
            return UsdShade.Material(found)
    return None


def _color(prim, UsdGeom, UsdShade, time):
    """displayColor if authored, else the bound preview surface's diffuse."""
    try:
        pv = UsdGeom.PrimvarsAPI(prim).GetPrimvar("displayColor")
        if pv and pv.HasAuthoredValue():
            vals = pv.Get(time)
            if vals:
                r, g, b = vals[0]
                return (float(r), float(g), float(b))
        mat = _bound_material(prim, UsdShade)
        if mat:
            shader, _, _ = mat.ComputeSurfaceSource()
            if shader:
                inp = shader.GetInput("diffuseColor")
                val = inp.Get(time) if inp else None
                if val is not None:
                    r, g, b = val
                    return (float(r), float(g), float(b))
    except Exception:                                         # noqa: BLE001
        pass
    return None
