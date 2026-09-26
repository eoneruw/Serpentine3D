"""A picture saved by a 0.9.x build of the fork still opens.

Those builds kept a picture as a `SPIC` record — image path, plane, a crop
window — in the object list. The picture format has since changed, and a
file with one of these in it refused to open at all ("File was not written
with this version of the topology"), taking a hundred other objects with
it. The old record is read as the picture it was.
"""

import json

import numpy as np

from serpentine3d.core import geometry as g
from serpentine3d.core.picture import PictureShape


def _old_record(crop=(0.0, 0.0, 1.0, 1.0)):
    return b"SPIC\x01" + json.dumps({
        "path": "/nowhere/ref.png",
        "origin": [10.0, 0.0, 0.0], "u": [0.0, 40.0, 0.0],
        "v": [0.0, 0.0, 30.0], "crop": list(crop), "size_px": [400, 300],
    }).encode("utf-8")


def test_an_old_picture_record_reads_as_a_picture():
    shape = g.shape_from_bytes(_old_record())
    assert isinstance(shape, PictureShape)
    assert shape.plane["path"] == "/nowhere/ref.png"
    lo, hi = shape.bbox()
    assert np.allclose(lo, (10, 0, 0)) and np.allclose(hi, (10, 40, 30))


def test_a_cropped_one_shows_only_its_window():
    shape = g.shape_from_bytes(_old_record(crop=(0.25, 0.0, 0.75, 0.5)))
    lo, hi = shape.bbox()
    assert np.allclose(lo, (10, 10, 0)) and np.allclose(hi, (10, 30, 15))
    # the mapping is still the whole image's, so the crop shows its part
    assert np.allclose(shape.plane["u"], (0, 40, 0))


def test_it_survives_a_save_and_reload():
    shape = g.shape_from_bytes(_old_record())
    again = g.shape_from_bytes(g.shape_to_bytes(shape))
    assert isinstance(again, PictureShape)
    assert np.allclose(again.bbox(), shape.bbox())
