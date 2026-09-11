"""Image-based lighting for the PBR display mode — the environment and its
prefiltered forms, in numpy, with no GL in sight.

A physically based surface is lit by everything around it, not by three
lamps. The "everything" here is a studio: a soft grey sky, a darker
ground, and three large softboxes — key, fill, rim — the arrangement a
car photographer would put up. It is drawn procedurally, so the app ships
no image and the look is the same on every machine.

The renderer needs the environment two ways. Diffuse lighting wants the
cosine-weighted average of the whole sky around a normal, which nine
spherical-harmonic coefficients hold exactly enough (Ramamoorthi &
Hanrahan 2001). Specular reflection wants the environment blurred by the
surface's roughness, and a ladder of maps blurred more and more, read at
the level the roughness picks, is the standard "split-sum" answer (Karis
2013). Both are computed once per process and cached.

Directions are world space, Z up. Equirectangular maps put the +X
direction at the middle column and +Z at the top row.
"""

from __future__ import annotations

import functools
import math
import os

import numpy as np

#: prefiltered-map resolution at roughness 0; each level halves it
BASE_WIDTH = 256
#: how many rungs the roughness ladder has (roughness 0 … 1 inclusive)
LEVELS = 6


# ------------------------------------------------------------- directions

def equirect_directions(width: int, height: int) -> np.ndarray:
    """(height, width, 3) unit vectors, one per texel centre, Z up."""
    u = (np.arange(width) + 0.5) / width           # 0..1 around
    v = (np.arange(height) + 0.5) / height         # 0..1 top to bottom
    phi = (u - 0.5) * 2.0 * math.pi                # +X at the middle
    theta = v * math.pi                            # +Z at the top
    st, ct = np.sin(theta), np.cos(theta)
    d = np.empty((height, width, 3), np.float64)
    d[..., 0] = st[:, None] * np.cos(phi)[None, :]
    d[..., 1] = st[:, None] * np.sin(phi)[None, :]
    d[..., 2] = ct[:, None]
    return d


def texel_solid_angles(width: int, height: int) -> np.ndarray:
    """(height, width) steradians per texel — rows near the poles are thin."""
    v = (np.arange(height) + 0.5) / height
    theta = v * math.pi
    dw = (2.0 * math.pi / width) * (math.pi / height) * np.sin(theta)
    return np.repeat(dw[:, None], width, axis=1)


# ------------------------------------------------------------ environment

def _softbox(d: np.ndarray, centre, size: float, colour, power: float):
    """A rectangular-ish light: a smooth blob around a direction."""
    c = np.asarray(centre, float)
    c /= np.linalg.norm(c)
    cosang = np.clip(d @ c, -1.0, 1.0)
    # size is the half-angle where the light has fallen to half; a soft
    # edge a few degrees wide keeps the reflection from looking cut out
    edge = np.deg2rad(size)
    ang = np.arccos(cosang)
    fall = 1.0 - _smoothstep(edge * 0.8, edge * 1.2, ang)
    return fall[..., None] * (np.asarray(colour, float) * power)[None, None]


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def studio_environment(width: int = BASE_WIDTH,
                       height: int | None = None) -> np.ndarray:
    """(height, width, 3) linear radiance of the studio, Z up.

    Brightness is in linear units where 1.0 is "white paper in the shade";
    the softboxes are much brighter than that, which is what makes them
    read as highlights after tone mapping.
    """
    height = height or width // 2
    d = equirect_directions(width, height)
    up = d[..., 2]
    # sky: neutral grey, a little brighter overhead; ground: darker and
    # warmer, with a soft horizon so the reflection line is not a hard cut
    # Kept dim: the softboxes do the lighting, and a bright ambient sky
    # fills every shadow until a white body panel is one flat tone.
    sky = np.array([0.13, 0.14, 0.17])
    zenith = np.array([0.22, 0.23, 0.27])
    ground = np.array([0.07, 0.065, 0.06])
    t = np.clip(up, 0.0, 1.0)[..., None]
    above = sky * (1 - t) + zenith * t
    horizon = _smoothstep(-0.08, 0.06, up)[..., None]
    env = ground * (1 - horizon) + above * horizon
    # the three lights: key high and to the front-left, a broad dim fill
    # from the right, a narrow rim behind and above
    env = env + _softbox(d, (-0.45, 0.55, 0.70), 16.0, (1.0, 0.98, 0.94), 7.0)
    env = env + _softbox(d, (0.85, -0.25, 0.35), 30.0, (0.86, 0.90, 1.0), 0.8)
    env = env + _softbox(d, (0.30, -0.80, 0.55), 10.0, (1.0, 1.0, 1.0), 4.0)
    # a strip light straight overhead: the highlight that runs the length
    # of a bonnet. Dim, because every upward face reflects it at once and
    # a hot one turns a red roof white.
    env = env + _softbox(d, (0.0, 0.0, 1.0), 7.0, (1.0, 1.0, 1.0), 1.2)
    return env.astype(np.float32)


# ------------------------------------------------------------- prefilter

def _roughness_for_level(level: int, levels: int = LEVELS) -> float:
    return level / max(levels - 1, 1)


def _lobe_sharpness(roughness: float) -> float:
    """How tight the blur is for a roughness, as the k of exp(k(cos-1)).

    A spherical Gaussian stands in for the GGX lobe: k = 2/alpha^2 with
    alpha = roughness^2 is the usual fit. Clamped at the top so the
    mirror level is a real map rather than one texel, and at the bottom
    so the roughest level is still a directional average, not a constant.
    """
    alpha = max(roughness * roughness, 0.03)
    return float(np.clip(2.0 / (alpha * alpha), 1.5, 4000.0))


def prefilter(env: np.ndarray, levels: int = LEVELS) -> list[np.ndarray]:
    """The roughness ladder: level 0 is the environment itself; each level
    after it is blurred for the roughness `level/(levels-1)` and half the
    size, since a blurrier map needs fewer texels to hold."""
    out = [np.asarray(env, np.float32)]
    full_w = env.shape[1]
    for level in range(1, levels):
        k = _lobe_sharpness(_roughness_for_level(level, levels))
        w = max(full_w >> level, 8)
        h = max(w // 2, 4)
        # A blur this wide cannot see detail finer than its own output, so
        # the source is first box-averaged down to the output's size: the
        # weights are then output x output rather than output x full, and
        # the whole ladder takes a second instead of a quarter of a minute.
        src = _downsample(env, w, h)
        src_d = equirect_directions(w, h).reshape(-1, 3).astype(np.float32)
        src_sa = texel_solid_angles(w, h).reshape(-1).astype(np.float32)
        src_rad = src.reshape(-1, 3).astype(np.float32)
        dst_d = src_d
        acc = np.empty((len(dst_d), 3), np.float32)
        chunk = 1024
        for i in range(0, len(dst_d), chunk):
            cos = dst_d[i:i + chunk] @ src_d.T
            wgt = np.exp(k * (cos - 1.0)) * src_sa[None, :]
            acc[i:i + chunk] = (wgt @ src_rad) / wgt.sum(axis=1)[:, None]
        out.append(acc.reshape(h, w, 3))
    return out


def _downsample(env: np.ndarray, w: int, h: int) -> np.ndarray:
    """Box-average an equirect map to (h, w); sizes divide evenly."""
    H, W = env.shape[:2]
    fy, fx = H // h, W // w
    if fy < 1 or fx < 1:
        return env
    return env[:h * fy, :w * fx].reshape(h, fy, w, fx, 3).mean(axis=(1, 3))


# --------------------------------------------------------- irradiance SH

def sh9_irradiance(env: np.ndarray) -> np.ndarray:
    """(9, 3) coefficients such that the shader's SH evaluation of a normal
    gives the cosine-convolved irradiance around it, divided by pi so it
    multiplies an albedo directly.

    Projection onto the real SH basis, then the band factors A0=pi,
    A1=2pi/3, A2=pi/4 fold the cosine lobe in (Ramamoorthi & Hanrahan).
    """
    h, w = env.shape[:2]
    d = equirect_directions(w, h).reshape(-1, 3)
    sa = texel_solid_angles(w, h).reshape(-1)
    rad = env.reshape(-1, 3).astype(np.float64)
    x, y, z = d[:, 0], d[:, 1], d[:, 2]
    basis = np.stack([
        np.full_like(x, 0.282095),
        0.488603 * y, 0.488603 * z, 0.488603 * x,
        1.092548 * x * y, 1.092548 * y * z,
        0.315392 * (3.0 * z * z - 1.0),
        1.092548 * x * z,
        0.546274 * (x * x - y * y),
    ], axis=1)                                          # (N, 9)
    coeffs = basis.T @ (rad * sa[:, None])              # (9, 3)
    band = np.array([math.pi,
                     2 * math.pi / 3, 2 * math.pi / 3, 2 * math.pi / 3,
                     math.pi / 4, math.pi / 4, math.pi / 4, math.pi / 4,
                     math.pi / 4])
    return (coeffs * band[:, None] / math.pi).astype(np.float32)


def evaluate_sh9(coeffs: np.ndarray, n) -> np.ndarray:
    """The irradiance the shader will compute for normal `n` — for tests
    and for anyone wanting the number without a GPU."""
    x, y, z = np.asarray(n, float) / np.linalg.norm(n)
    basis = np.array([
        0.282095,
        0.488603 * y, 0.488603 * z, 0.488603 * x,
        1.092548 * x * y, 1.092548 * y * z,
        0.315392 * (3.0 * z * z - 1.0),
        1.092548 * x * z,
        0.546274 * (x * x - y * y),
    ])
    return basis @ np.asarray(coeffs, float)


# ------------------------------------------------------ more environments

def _sky_gradient(d, zenith, horizon, ground, soft: float = 0.06):
    """A sky that runs from `zenith` overhead to `horizon` at the line,
    and a `ground` below it, with a soft line between."""
    up = d[..., 2]
    t = np.clip(up, 0.0, 1.0) ** 0.7
    above = np.asarray(horizon, float) * (1 - t[..., None]) \
        + np.asarray(zenith, float) * t[..., None]
    line = _smoothstep(-soft, soft, up)[..., None]
    return np.asarray(ground, float) * (1 - line) + above * line


def _sun(d, elevation_deg: float, azimuth_deg: float, colour, power: float,
         disc_deg: float = 1.5, glow_deg: float = 25.0, glow_power=0.35):
    """A sun: a small very bright disc with a wide soft glow around it."""
    el, az = np.deg2rad(elevation_deg), np.deg2rad(azimuth_deg)
    centre = (np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el))
    disc = _softbox(d, centre, disc_deg, colour, power)
    glow = _softbox(d, centre, glow_deg, colour, power * glow_power)
    return disc + glow


def bright_studio_environment(width: int = BASE_WIDTH,
                              height: int | None = None) -> np.ndarray:
    """A white cove studio: bright everywhere, big soft lights, the kind
    that shows a panel's shape as long even gradients."""
    height = height or width // 2
    d = equirect_directions(width, height)
    env = _sky_gradient(d, (0.9, 0.9, 0.92), (0.75, 0.75, 0.78),
                        (0.55, 0.55, 0.56), soft=0.15)
    env = env + _softbox(d, (-0.4, 0.5, 0.75), 28.0, (1.0, 0.99, 0.97), 3.0)
    env = env + _softbox(d, (0.8, -0.3, 0.5), 32.0, (0.95, 0.97, 1.0), 1.6)
    env = env + _softbox(d, (0.2, -0.85, 0.45), 18.0, (1.0, 1.0, 1.0), 2.2)
    env = env + _softbox(d, (0.0, 0.0, 1.0), 40.0, (1.0, 1.0, 1.0), 1.0)
    return env.astype(np.float32)


def sunny_environment(width: int = BASE_WIDTH,
                      height: int | None = None) -> np.ndarray:
    """A clear day: deep blue overhead, pale at the horizon, a hard sun
    high to the front-left, grey-green ground."""
    height = height or width // 2
    d = equirect_directions(width, height)
    env = _sky_gradient(d, (0.18, 0.32, 0.75), (0.62, 0.72, 0.88),
                        (0.20, 0.20, 0.17))
    env = env + _sun(d, 48.0, 140.0, (1.0, 0.97, 0.90), 60.0)
    return env.astype(np.float32)


def sunset_environment(width: int = BASE_WIDTH,
                       height: int | None = None) -> np.ndarray:
    """Golden hour: an orange horizon under a violet-blue sky, the sun a
    hand above the line and warm, the ground already in shadow."""
    height = height or width // 2
    d = equirect_directions(width, height)
    env = _sky_gradient(d, (0.16, 0.14, 0.38), (0.95, 0.52, 0.28),
                        (0.12, 0.09, 0.08), soft=0.04)
    # the band of colour along the horizon, brightest toward the sun
    az = np.arctan2(d[..., 1], d[..., 0])
    toward = 0.5 + 0.5 * np.cos(az - np.deg2rad(200.0))
    band = np.exp(-((d[..., 2] - 0.03) / 0.09) ** 2) * toward
    env = env + band[..., None] * np.array([0.9, 0.35, 0.10])
    env = env + _sun(d, 7.0, 200.0, (1.0, 0.62, 0.30), 18.0, disc_deg=2.0,
                     glow_deg=30.0, glow_power=0.4)
    return env.astype(np.float32)


def overcast_environment(width: int = BASE_WIDTH,
                         height: int | None = None) -> np.ndarray:
    """A grey day: one enormous soft light overhead and nothing else —
    reflections become gradients, which is what a shape read wants."""
    height = height or width // 2
    d = equirect_directions(width, height)
    env = _sky_gradient(d, (1.6, 1.62, 1.7), (0.85, 0.87, 0.92),
                        (0.22, 0.22, 0.21), soft=0.12)
    return env.astype(np.float32)


def warehouse_environment(width: int = BASE_WIDTH,
                          height: int | None = None) -> np.ndarray:
    """A workshop: dim grey walls, a concrete floor, and a grid of strip
    lights across the ceiling that a bonnet reflects as parallel bars."""
    height = height or width // 2
    d = equirect_directions(width, height)
    env = _sky_gradient(d, (0.10, 0.10, 0.11), (0.16, 0.15, 0.14),
                        (0.14, 0.13, 0.12), soft=0.2)
    # strip lights: three long bars across the ceiling, each a run of
    # small blobs so it reads as one tube in a reflection
    for y in (-0.7, 0.0, 0.7):
        for x in np.linspace(-1.6, 1.6, 9):
            env = env + _softbox(d, (x, y, 1.5), 3.5, (0.95, 0.97, 1.0), 6.0)
    # a roller door open at one end: a slab of daylight low on one side
    env = env + _softbox(d, (0.95, 0.15, 0.10), 22.0, (0.7, 0.78, 0.95), 1.4)
    return env.astype(np.float32)


#: The environments on offer: id -> (label, builder). The first is the
#: default. Ids are what the command line and the saved settings use.
ENVIRONMENTS = {
    "studio": ("Studio", studio_environment),
    "bright_studio": ("Well-lit studio", bright_studio_environment),
    "sunny": ("Sunny day", sunny_environment),
    "sunset": ("Sunset", sunset_environment),
    "overcast": ("Overcast", overcast_environment),
    "warehouse": ("Warehouse", warehouse_environment),
}


def environment_names() -> list[str]:
    return list(ENVIRONMENTS)


def environment_label(name: str) -> str:
    if name in ENVIRONMENTS:
        return ENVIRONMENTS[name][0]
    return os.path.basename(name)


# ------------------------------------------------------- image files

def load_equirect(path: str) -> np.ndarray:
    """An environment from an image file: a Radiance .hdr read for
    what it is, anything else (png, jpg...) taken as sRGB and decoded
    to linear. Equirectangular, wide side across."""
    low = path.lower()
    if low.endswith(".hdr"):
        return _read_rgbe(path)
    from PySide6.QtGui import QImage
    img = QImage(path)
    if img.isNull():
        raise ValueError(f"Could not read {path}")
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    buf = img.constBits()
    arr = np.frombuffer(buf, np.uint8, count=h * img.bytesPerLine())
    arr = arr.reshape(h, img.bytesPerLine())[:, :w * 3].reshape(h, w, 3)
    lin = (arr.astype(np.float32) / 255.0) ** 2.2
    # an LDR picture of a sky has no sun brighter than white; lift it so
    # a bright patch still reads as a light after tone mapping
    return (lin * 2.5).astype(np.float32)


def _read_rgbe(path: str) -> np.ndarray:
    """Radiance RGBE (.hdr), the flat and the run-length encoded kinds."""
    with open(path, "rb") as fh:
        data = fh.read()
    pos = 0
    width = height = None
    while True:
        end = data.index(b"\n", pos)
        line = data[pos:end].decode("latin-1").strip()
        pos = end + 1
        if line.startswith("-Y") or line.startswith("+Y"):
            parts = line.split()
            height, width = int(parts[1]), int(parts[3])
            break
        if pos >= len(data):
            raise ValueError("Not a Radiance .hdr file")
    body = np.frombuffer(data, np.uint8, offset=pos)
    out = np.empty((height, width, 4), np.uint8)
    i = 0
    for y in range(height):
        if (width >= 8 and width < 32768 and body[i] == 2 and body[i + 1] == 2
                and (body[i + 2] << 8 | body[i + 3]) == width):
            i += 4
            for c in range(4):
                x = 0
                while x < width:
                    n = int(body[i])
                    i += 1
                    if n > 128:
                        n -= 128
                        out[y, x:x + n, c] = body[i]
                        i += 1
                    else:
                        out[y, x:x + n, c] = body[i:i + n]
                        i += n
                    x += n
        else:
            out[y] = body[i:i + width * 4].reshape(width, 4)
            i += width * 4
    rgb = out[..., :3].astype(np.float32)
    e = out[..., 3].astype(np.int32)
    scale = np.where(e > 0, np.ldexp(1.0, e - 136), 0.0).astype(np.float32)
    return (rgb * scale[..., None]).astype(np.float32)


def _fit_equirect(env: np.ndarray, width: int = BASE_WIDTH) -> np.ndarray:
    """Resample a loaded map to the ladder's base size (nearest)."""
    h, w = env.shape[:2]
    height = width // 2
    ys = (np.arange(height) + 0.5) / height * h
    xs = (np.arange(width) + 0.5) / width * w
    return env[ys.astype(int).clip(0, h - 1)][:, xs.astype(int).clip(0, w - 1)]


# ----------------------------------------------------------------- cache

@functools.lru_cache(maxsize=8)
def lighting(name: str) -> tuple[list[np.ndarray], np.ndarray]:
    """(prefiltered ladder, SH9 coefficients) of an environment, built
    once per name. `name` is an id from ENVIRONMENTS or the path of an
    image file."""
    if name in ENVIRONMENTS:
        env = ENVIRONMENTS[name][1]()
    else:
        env = _fit_equirect(load_equirect(name))
    return prefilter(env), sh9_irradiance(env)


def studio_lighting() -> tuple[list[np.ndarray], np.ndarray]:
    """(prefiltered ladder, SH9 coefficients) of the studio, built once."""
    return lighting("studio")
