"""Photo analysis (studio/analysis.py): which photos are bad, how sharp they are, finding them."""
import os
import time

import numpy as np
import pytest
from PIL import Image, ImageFilter

from conftest import LION, make_library, photo
from studio import analysis


def library_with(**values):
    """A library of one photo with these analysis values (the rest are those of a good photo)."""
    return make_library(".", [{"emb": photo(*LION), **values}])


# ---------- Bad photos: Library.problem() ----------

def test_a_good_photo_has_no_problem():
    assert library_with().problem(0) == ""


@pytest.mark.parametrize("values, problem", [
    ({"clipped": 0.95}, "blank"),                         # lens cap, totally burnt out
    ({"brightest": 30}, "dark"),                          # even the brightest parts are dark
    ({"middle_brightness": 16, "brightest": 87}, "dark"),  # a dark room with a bright window
    ({"sharpness": 10}, "blurry"),                        # no sharp detail at all
    ({"blur": 0.06}, "blurry"),                           # the image model sees motion blur
    ({"sharpness": 50, "blur": 0.04}, "blurry"),          # both a little off together
    ({"subject_blur": 0.65}, "unfocused"),                # the animal is soft, the background sharp
    ({"pale_flat": 0.3, "rest_colour": 5}, "overexposed"),
])
def test_each_rule_finds_its_kind_of_bad_photo(values, problem):
    assert library_with(**values).problem(0) == problem


@pytest.mark.parametrize("values", [
    {"sharpness": 50, "blur": 0.02},              # a low-detail landscape, but not blurry-looking
    {"pale_flat": 0.3, "rest_colour": 12},        # a pale sky, but colourful birds under it
    {"subject_blur": np.nan},                     # no animal or person found: focus not judged
    {"subject_area": 0.005, "subject_blur": 0.6},  # a tiny, distant animal may look softer
    {"middle_brightness": 18, "brightest": 228},   # a sunset silhouette: dark, but with a bright sky
    {"middle_brightness": 14, "brightest": 119},   # deep shade next to sunlight
])
def test_borderline_photos_are_not_hidden(values):
    assert library_with(**values).problem(0) == ""


def test_a_small_subject_is_still_caught_when_very_soft():
    assert library_with(subject_area=0.005, subject_blur=0.65).problem(0) == "unfocused"


def test_a_subject_far_softer_than_the_rest_is_out_of_focus():
    # a soft cat on a sharp sofa: under the focus limit for its size (0.60), but 0.32 softer
    # than the sharpest parts of the photo
    assert library_with(subject_area=0.08, subject_blur=0.557, softness=0.233).problem(0) == "unfocused"


def test_dark_is_reported_before_blurry():
    # dark photos also measure as unsharp; "too dark" is the real reason
    assert library_with(brightest=30, sharpness=5).problem(0) == "dark"


# ---------- Soft photos: a hint, never hidden ----------

@pytest.mark.parametrize("softness, soft", [(0.50, True), (0.30, False), (np.nan, False),
                                            (analysis.NOT_CHECKED, False)])
def test_is_soft(softness, soft):
    lib = library_with(softness=softness)
    assert lib.is_soft(0) is soft
    assert lib.problem(0) == ""  # soft photos are only marked, not hidden


@pytest.mark.parametrize("values, soft", [
    ({"subject_area": 0.08, "subject_blur": 0.51, "softness": 0.23}, True),     # the subject 0.28 softer: a hint
    ({"subject_area": 0.08, "subject_blur": 0.48, "softness": 0.23}, False),    # a sharp selfie: smooth skin
    ({"subject_area": 0.02, "subject_blur": 0.50, "softness": 0.23}, False),    # a small subject: not judged
    ({"subject_area": 0.08, "subject_blur": 0.58, "softness": np.nan}, False),  # sharpness not measured
])
def test_a_subject_much_softer_than_the_rest_is_marked_soft(values, soft):
    lib = library_with(**values)
    assert lib.is_soft(0) is soft
    assert lib.problem(0) == ""  # a hint only: smooth subjects measure soft too


# ---------- The library ----------

def test_photos_are_in_the_order_they_were_taken():
    lib = make_library(".", [{"emb": photo(*LION), "taken": t} for t in (30, 10, 20)])
    assert lib.files == ["p01.jpg", "p02.jpg", "p00.jpg"]


def test_sharper_photos_get_a_higher_quality():
    lib = make_library(".", [{"emb": photo(*LION), "sharpness": s} for s in (50, 400, 120)])
    assert lib.quality[1] > lib.quality[2] > lib.quality[0]


def test_rank01_spreads_values_from_0_to_1_in_order():
    assert list(analysis.rank01(np.array([5.0, 1.0, 3.0]))) == [1.0, 0.0, 0.5]
    assert list(analysis.rank01(np.array([7.0]))) == [0.0]


# ---------- Measuring sharpness on generated images ----------

def noise_image(size=(1024, 768), blur=0, seed=1):
    """Random detail (sharp everywhere), optionally blurred."""
    pixels = np.random.default_rng(seed).integers(0, 256, (size[1], size[0]), dtype=np.uint8)
    img = Image.fromarray(pixels).convert("RGB")
    return img.filter(ImageFilter.GaussianBlur(blur)) if blur else img


def blocks_image(size=(2400, 1600), blur=0, seed=1, block=24):
    """Random grey squares with sharp edges, like the shapes in a photo, optionally blurred.
    (Blurred random noise would turn almost flat, unlike a blurred photo.)"""
    rng = np.random.default_rng(seed)
    h, w = size[1] // block + 1, size[0] // block + 1
    squares = Image.fromarray(rng.integers(0, 256, (h, w), dtype=np.uint8))
    img = squares.resize((w * block, h * block), Image.NEAREST).crop((0, 0) + size).convert("RGB")
    return img.filter(ImageFilter.GaussianBlur(blur)) if blur else img


def test_quality_metrics_sharp_scores_higher_than_blurred():
    sharp, _ = analysis.quality_metrics(noise_image())
    blurred, _ = analysis.quality_metrics(noise_image(blur=4))
    assert sharp > 10 * blurred


def test_quality_metrics_counts_pure_black_and_white_pixels():
    img = Image.new("L", (1024, 768), 0)
    img.paste(255, (0, 0, 512, 768))  # half white, half black
    _, clipped = analysis.quality_metrics(img.convert("RGB"))
    assert clipped == pytest.approx(1.0)
    _, clipped = analysis.quality_metrics(noise_image())
    assert clipped < 0.05


def test_reblur_sharp_detail_is_lost_when_blurred_on_purpose():
    gray = lambda img: np.asarray(img.convert("L"), dtype=np.float32)  # noqa: E731
    everywhere = np.ones((1600, 2400), dtype=bool)
    sharp = analysis.reblur(gray(blocks_image()), everywhere)
    blurred = analysis.reblur(gray(blocks_image(blur=3)), everywhere)
    assert sharp < 0.3 < 0.7 < blurred


def test_softness_metric_tells_sharp_from_soft(tmp_path):
    blocks_image().save(tmp_path / "sharp.png")
    blocks_image(blur=2).save(tmp_path / "soft.png")
    sharp = analysis.softness_metric(tmp_path / "sharp.png")
    soft = analysis.softness_metric(tmp_path / "soft.png")
    assert sharp < analysis.SOFT_ABOVE < soft


def test_softness_metric_ignores_flat_photos(tmp_path):
    Image.new("RGB", (2400, 1600), (120, 160, 220)).save(tmp_path / "sky.png")  # nothing to judge
    assert np.isnan(analysis.softness_metric(tmp_path / "sky.png"))


def test_exposure_metrics():
    pale, colour, _, _ = analysis.exposure_metrics(Image.new("RGB", (480, 320), (235, 235, 235)))
    assert pale == pytest.approx(1.0, abs=0.02)  # a flat, pale, colourless area: burnt-out sky
    _, colour, brightest, _ = analysis.exposure_metrics(Image.new("RGB", (480, 320), (200, 60, 20)))
    assert colour > 100 and brightest < 200
    _, _, brightest, _ = analysis.exposure_metrics(Image.new("RGB", (480, 320), (15, 15, 15)))
    assert brightest < analysis.TOO_DARK_BELOW


def test_middle_brightness_of_a_dark_room_with_a_bright_window():
    room = Image.new("RGB", (480, 320), (10, 10, 10))
    room.paste((200, 200, 200), (0, 0, 60, 320))  # a window: an eighth of the photo
    _, _, brightest, middle = analysis.exposure_metrics(room)
    assert brightest >= analysis.TOO_DARK_BELOW     # the old rule alone would show it
    assert middle < analysis.MOSTLY_DARK_MIDDLE


# ---------- Finding the photos of a folder ----------

def test_find_images_skips_the_apps_own_folders_and_other_files(tmp_path):
    for name in ["a.jpg", "b.PNG", "sub/c.jpeg", "notes.txt", "._a.jpg",
                 ".album_studio/thumbs/x.jpg", "album_export/001 a.jpg"]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x")
    found = [p.relative_to(tmp_path).as_posix() for p in analysis.find_images(tmp_path)]
    assert found == ["a.jpg", "b.PNG", "sub/c.jpeg"]


def test_date_taken_without_exif_is_the_file_date(tmp_path):
    path = tmp_path / "no_exif.jpg"
    Image.new("RGB", (10, 10)).save(path)
    when = time.mktime((2025, 4, 16, 9, 30, 0, 0, 0, -1))
    os.utime(path, (when, when))
    with Image.open(path) as img:
        assert analysis.date_taken(img, path) == when
