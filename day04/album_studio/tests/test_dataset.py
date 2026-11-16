"""A photo dataset: photos in folders whose name is the answer the app must give.

Every photo goes through the app's real analysis and the real image model, so this checks the
whole pipeline on actual images: the photos you put in its folders, and the fake photos made from
them by make_dataset.py. Slow the first time (the image models are loaded, every photo is
analysed); the results are cached in the dataset's .album_studio folder, so later runs take seconds.

    python -m pytest tests --dataset               tests/dataset
    python -m pytest tests --dataset=FOLDER        your own (make one with tests/make_dataset.py)

If the dataset folder does not exist yet, a fake one is made first (drawn photos and the fakes
made from them, see make_dataset.py), so the tests work on any computer.
"""
from pathlib import Path

import numpy as np
import pytest

import make_dataset
from studio import analysis, subjects
from studio.steps.group_similar import DEFAULT_SETTINGS, group_photos

pytestmark = pytest.mark.real_model  # skipped unless --dataset is given (see conftest.py)

# quality/<folder>: what the analysis may say (problem() is "" for a photo that is shown).
# Blurry and out of focus both mean "not sharp, hidden": either answer is right for either folder.
QUALITY = {
    "good": {""},               # shown, and not marked soft
    "soft": {""},               # shown, but marked "soft"
    "blurry": {"blurry", "unfocused"},
    "unfocused": {"unfocused", "blurry"},  # the animal or person is soft, the background sharp
    "too_dark": {"dark"},
    "blank": {"blank"},
    "overexposed": {"overexposed"},
}


def dataset_folder(config):
    """The chosen dataset; with --dataset, made as a fake dataset first if it does not exist."""
    option = config.getoption("--dataset")
    folder = Path(option or make_dataset.DEFAULT_DATASET)
    return make_dataset.ensure(folder) if option is not None else folder


def photos_in(dataset, part):
    """(folder name, path relative to the dataset) of every photo under <dataset>/<part>/."""
    return sorted((p.relative_to(dataset / part).parts[0], p.relative_to(dataset).as_posix())
                  for p in analysis.find_images(dataset / part)) if (dataset / part).exists() else []


def pytest_generate_tests(metafunc):
    """One test per photo of the chosen dataset: test_quality for quality/, test_subject for subjects/."""
    part = {"test_quality": "quality", "test_subject": "subjects"}.get(metafunc.function.__name__)
    if part:
        metafunc.parametrize("folder, path", photos_in(dataset_folder(metafunc.config), part), ids=lambda v: v)


@pytest.fixture(scope="session")
def dataset(pytestconfig):
    return dataset_folder(pytestconfig)


@pytest.fixture(scope="session")
def library(dataset):
    """The whole dataset analysed exactly as the app analyses a photo folder (cached in it)."""
    subjects.text.compute(subjects.all_prompts())  # the subject names, if not cached yet
    return analysis.analyse(dataset, lambda *args, **kwargs: None)


def index(library, path):
    assert path in library.files, f"{path} could not be read as a photo"
    return library.files.index(path)


def test_quality(library, folder, path):
    assert folder in QUALITY, f"unknown folder quality/{folder}: use one of {', '.join(QUALITY)}"
    i = index(library, path)
    assert library.problem(i) in QUALITY[folder], \
        (f"sharpness {library.sharpness[i]:.0f}, looks blurry {library.blur[i]:.3f}, brightest "
         f"{library.brightest[i]:.0f}, middle brightness {library.middle_brightness[i]:.0f}, subject "
         f"{library.subject_area[i]:.2f} of the photo with blur {library.subject_blur[i]:.2f}")
    if folder in ("good", "soft"):
        assert library.is_soft(i) == (folder == "soft"), (f"softness {library.softness[i]:.3f} (soft above {analysis.SOFT_ABOVE}), "
                                                       f"subject blur {library.subject_blur[i]:.2f}")


def test_subject(library, folder, path):
    known = subjects.species_names() + ["people", "views", "other", subjects.OTHER_ANIMALS]
    assert folder in known, f"unknown subject {folder!r}: use a name from studio/species_africa.txt, or people, views, other"
    assert subjects.recognise(library.embedding, [[index(library, path)]]) == [folder]


def test_groups(library, dataset):
    """Each folder in groups/ is one burst: its photos must form one group, alone."""
    expected = photos_in(dataset, "groups")
    if not expected:
        pytest.skip("no photos in groups/")
    ids = [index(library, path) for _, path in expected]
    seconds = DEFAULT_SETTINGS["seconds"]
    found = group_photos(library.embedding[ids], library.taken[ids], DEFAULT_SETTINGS["similarity"],
                         np.inf if seconds is None else seconds)
    as_folders = sorted(sorted(expected[j][1] for j in group) for group in found)
    wanted = sorted(sorted(path for f, path in expected if f == folder) for folder in {f for f, _ in expected})
    assert as_folders == wanted
