"""The studio lighting behind the PBR display mode, checked without a GPU.

Three things have to be right for the shader to be right: the directions
an equirectangular map stands for, the spherical harmonics that give
diffuse light around a normal, and the roughness ladder of blurred
environments that gives specular reflection. Each is checked against a
case with a known answer.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from serpentine3d.ui import ibl


def test_directions_are_unit_z_up_x_forward():
    d = ibl.equirect_directions(256, 128)
    assert np.allclose(np.linalg.norm(d, axis=-1), 1.0)
    assert d[0, :, 2].min() > 0.99, "the top row looks straight up"
    assert d[-1, :, 2].max() < -0.99, "the bottom row straight down"
    mid = d[64, 128]
    assert mid[0] > 0.99, "the middle column, on the horizon, is +X"


def test_solid_angles_tile_the_sphere():
    sa = ibl.texel_solid_angles(256, 128)
    assert sa.sum() == pytest.approx(4 * math.pi, rel=1e-3)


def test_the_studio_is_brighter_above_than_below():
    env = ibl.studio_environment(64)
    up = env[:8].mean()
    down = env[-8:].mean()
    assert up > down * 2
    assert env.max() > 1.5, "the softboxes are brighter than white paper"
    assert env.min() > 0.0, "and nothing is pitch black"


def test_a_uniform_sky_gives_the_same_irradiance_everywhere():
    """SH of a constant environment of 1 must evaluate to 1 (irradiance
    over pi) in every direction — the calibration the shader relies on."""
    sh = ibl.sh9_irradiance(np.ones((32, 64, 3), np.float32))
    for n in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (0.3, -0.5, 0.8)):
        assert ibl.evaluate_sh9(sh, n) == pytest.approx([1, 1, 1], abs=2e-3)


def test_the_studio_lights_an_upward_normal_more_than_a_downward_one():
    sh = ibl.sh9_irradiance(ibl.studio_environment(64))
    up = ibl.evaluate_sh9(sh, (0, 0, 1)).mean()
    down = ibl.evaluate_sh9(sh, (0, 0, -1)).mean()
    assert up > down * 3


def test_the_roughness_ladder_gets_smaller_and_smoother():
    env = ibl.studio_environment(64)
    ladder = ibl.prefilter(env, levels=4)
    assert len(ladder) == 4
    assert ladder[0].shape == env.shape
    widths = [m.shape[1] for m in ladder]
    assert widths == sorted(widths, reverse=True)
    # a blur cannot add energy or contrast: the peak falls and the mean
    # holds, rung by rung
    peaks = [float(m.max()) for m in ladder]
    assert peaks == sorted(peaks, reverse=True)
    means = [float(m.mean()) for m in ladder]
    assert max(means) - min(means) < 0.15 * means[0]


def test_the_ladder_is_built_once():
    ibl.studio_lighting.cache_clear()
    a = ibl.studio_lighting()
    b = ibl.studio_lighting()
    assert a is b
    ladder, sh = a
    assert len(ladder) == ibl.LEVELS and sh.shape == (9, 3)
