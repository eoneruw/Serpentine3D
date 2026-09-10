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


# ----------------------------------------------------------------- cache

@functools.lru_cache(maxsize=1)
def studio_lighting() -> tuple[list[np.ndarray], np.ndarray]:
    """(prefiltered ladder, SH9 coefficients) of the studio, built once."""
    env = studio_environment()
    return prefilter(env), sh9_irradiance(env)
