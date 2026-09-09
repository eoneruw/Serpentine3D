"""A picture in the model: an image on a plane, showing a window of itself.

A blueprint sheet has the front, side and top of a car on one page, and
the way to trace it is not to cut the page up in an image editor but to
put the sheet in the model three times and show a different part of it
each time. So a picture keeps the whole image — `origin`, `u` and `v`
place its full extent in the world — and `crop` says which window of it
is shown, as fractions of the width and height. Moving a crop corner
changes the window; moving the picture moves image and window together.

It is a MeshShape underneath (the shown window as two triangles), so
everything that handles a mesh — picking, the gumball, bounding boxes,
transforms, copy and paste, undo — handles a picture without knowing.
What is different is drawn: the viewport paints the image across the
window instead of shading the triangles.
"""

from __future__ import annotations

import os

import numpy as np

from .mesh import MeshShape

FULL = (0.0, 0.0, 1.0, 1.0)


class PictureShape(MeshShape):
    __slots__ = ("path", "origin", "u", "v", "crop", "size_px")

    def __init__(self, path: str, origin, u, v, crop=FULL,
                 size_px: tuple[int, int] | None = None):
        self.path = str(path)
        self.origin = np.asarray(origin, float).copy()
        self.u = np.asarray(u, float).copy()
        self.v = np.asarray(v, float).copy()
        self.crop = tuple(float(c) for c in crop)
        self.size_px = tuple(size_px) if size_px else None
        corners = self.corners()
        super().__init__(corners, np.array([[0, 1, 2], [0, 2, 3]],
                                           np.uint32),
                         normals=np.tile(self.normal(), (4, 1)))

    # -- where it is --

    def normal(self) -> np.ndarray:
        n = np.cross(self.u, self.v)
        length = np.linalg.norm(n)
        return n / length if length > 1e-12 else np.array([0.0, 0.0, 1.0])

    def corners(self) -> np.ndarray:
        """The shown window's four corners in world space, anticlockwise
        from the origin corner: (s0,t0), (s1,t0), (s1,t1), (s0,t1)."""
        s0, t0, s1, t1 = self.crop
        return np.array([self.at(s0, t0), self.at(s1, t0),
                         self.at(s1, t1), self.at(s0, t1)])

    def full_corners(self) -> np.ndarray:
        """The whole image's corners, cropped or not."""
        return np.array([self.at(0, 0), self.at(1, 0),
                         self.at(1, 1), self.at(0, 1)])

    def at(self, s: float, t: float) -> np.ndarray:
        """World point at image fractions (s along u, t along v)."""
        return self.origin + self.u * s + self.v * t

    def uv_corners(self) -> np.ndarray:
        """Texture coordinates for corners(), in the same order."""
        s0, t0, s1, t1 = self.crop
        return np.array([[s0, t0], [s1, t0], [s1, t1], [s0, t1]])

    def fractions_of(self, point) -> tuple[float, float]:
        """(s, t) of a world point projected onto the picture's plane."""
        d = np.asarray(point, float) - self.origin
        uu, vv, uv = self.u @ self.u, self.v @ self.v, self.u @ self.v
        du, dv = d @ self.u, d @ self.v
        det = uu * vv - uv * uv
        if abs(det) < 1e-18:
            return 0.0, 0.0
        s = (du * vv - dv * uv) / det
        t = (dv * uu - du * uv) / det
        return float(s), float(t)

    @property
    def name_hint(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0] or "Picture"

    # -- changed copies --

    def with_crop(self, crop) -> "PictureShape":
        s0, t0, s1, t1 = (min(max(float(c), 0.0), 1.0) for c in crop)
        if s1 - s0 < 1e-4:
            s1 = min(1.0, s0 + 1e-4)
        if t1 - t0 < 1e-4:
            t1 = min(1.0, t0 + 1e-4)
        return PictureShape(self.path, self.origin, self.u, self.v,
                            (s0, t0, s1, t1), self.size_px)

    def with_corner_at(self, index: int, point) -> "PictureShape":
        """The window with corner `index` (see corners()) moved so it sits
        under `point`. A corner owns two edges of the window, so those two
        move and the other two stay; the frame stays square to the image
        and inside it. The corner cannot cross its opposite."""
        s, t = self.fractions_of(point)
        s, t = min(max(s, 0.0), 1.0), min(max(t, 0.0), 1.0)
        s0, t0, s1, t1 = self.crop
        gap = 1e-3
        if index == 0:
            s0, t0 = min(s, s1 - gap), min(t, t1 - gap)
        elif index == 1:
            s1, t0 = max(s, s0 + gap), min(t, t1 - gap)
        elif index == 2:
            s1, t1 = max(s, s0 + gap), max(t, t0 + gap)
        elif index == 3:
            s0, t1 = min(s, s1 - gap), max(t, t0 + gap)
        else:
            raise IndexError(index)
        return self.with_crop((s0, t0, s1, t1))

    def transformed(self, matrix) -> "PictureShape":
        m = np.asarray(matrix, float)
        if m.shape == (3, 3):
            lin, off = m, np.zeros(3)
        else:
            lin, off = m[:3, :3], m[:3, 3]
        return PictureShape(self.path, lin @ self.origin + off,
                            lin @ self.u, lin @ self.v, self.crop,
                            self.size_px)

    def translated(self, offset) -> "PictureShape":
        return PictureShape(self.path, self.origin + np.asarray(offset, float),
                            self.u, self.v, self.crop, self.size_px)

    def copy(self) -> "PictureShape":
        return PictureShape(self.path, self.origin, self.u, self.v,
                            self.crop, self.size_px)

    # -- on and off disk --

    def to_json(self) -> dict:
        return {"path": self.path, "origin": [float(c) for c in self.origin],
                "u": [float(c) for c in self.u],
                "v": [float(c) for c in self.v],
                "crop": list(self.crop),
                "size_px": list(self.size_px) if self.size_px else None}

    @classmethod
    def from_json(cls, d: dict) -> "PictureShape":
        return cls(d["path"], d["origin"], d["u"], d["v"],
                   d.get("crop", FULL), d.get("size_px"))


def image_size(path: str) -> tuple[int, int] | None:
    """(width, height) in pixels, or None if the file is not an image."""
    try:
        from PySide6.QtGui import QImageReader
        size = QImageReader(str(path)).size()
        if size.isValid() and size.width() > 0 and size.height() > 0:
            return int(size.width()), int(size.height())
    except Exception:                                    # noqa: BLE001
        pass
    return None


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff",
              ".webp")


def is_image_path(path: str) -> bool:
    return os.path.splitext(str(path))[1].lower() in IMAGE_EXTS


def picture_on_plane(path: str, cplane, centre, width: float,
                     size_px=None) -> PictureShape:
    """A whole, uncropped picture lying on `cplane`, centred at the world
    point `centre`, `width` wide and as tall as its pixels say."""
    if size_px is None:
        size_px = image_size(path) or (1, 1)
    aspect = size_px[1] / max(size_px[0], 1)
    height = width * aspect
    cu, cv, cw = cplane.from_world(centre)
    o = np.asarray(cplane.to_world(cu - width / 2, cv - height / 2, cw),
                   float)
    u = np.asarray(cplane.to_world(cu + width / 2, cv - height / 2, cw),
                   float) - o
    v = np.asarray(cplane.to_world(cu - width / 2, cv + height / 2, cw),
                   float) - o
    return PictureShape(path, o, u, v, FULL, size_px)
