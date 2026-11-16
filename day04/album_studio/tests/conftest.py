"""Shared helpers for the tests of Album Studio's business logic.

The tests never use real photos or the image model: a Library is built from made-up analysis
values, and the "image model" is replaced by a tiny fake whose answers are known. That keeps the
tests fast (a few seconds) and makes every expected result easy to see.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from studio import project as project_module  # noqa: E402
from studio import subjects  # noqa: E402
from studio.analysis import Library  # noqa: E402
from studio.project import Project  # noqa: E402
from studio.steps.export import ExportStep  # noqa: E402
from studio.steps.group_similar import GroupSimilarStep  # noqa: E402
from studio.steps.pick_photos import PickPhotosStep  # noqa: E402

# ---------- A fake "image model" ----------
# Every subject is one direction in a 10-dimensional space. A photo "shows" a subject when its
# embedding points that way; text descriptions of the subject point the same way.
AXES = {"animals": 0, "people": 1, "views": 2, "other": 3,
        "lion": 4, "zebra": 5, "wildebeest": 6, "unknown species": 7}
DIM = 10
SPECIES = ["lion", "zebra", "wildebeest"]


def axis(name):
    v = np.zeros(DIM)
    v[AXES[name]] = 1.0
    return v


def photo(*names, noise=0.0, seed=0):
    """The embedding of a photo that shows these subjects, e.g. photo("animals", "lion")."""
    v = sum(axis(n) for n in names) + np.random.default_rng(seed).normal(0, noise, DIM)
    return v / np.linalg.norm(v)


LION = ("animals", "lion")
ZEBRA = ("animals", "zebra")
WILDEBEEST = ("animals", "wildebeest")
UNKNOWN_ANIMAL = ("animals", "unknown species")
PEOPLE = ("people",)
VIEW = ("views",)


class FakeText:
    """Stands in for subjects.text (the cached text embeddings of the real model)."""

    def describe(self, prompts):
        prompts = list(prompts)
        for category, category_prompts in subjects.CATEGORY_PROMPTS.items():
            if prompts == category_prompts:
                return axis(category)
        if prompts[0] in subjects.UNKNOWN_SPECIES_PROMPTS:
            return axis("unknown species")
        for name in SPECIES:
            if prompts == [subjects.species_prompt(name)]:
                return axis(name)
        raise KeyError(prompts)


@pytest.fixture(autouse=True)
def fake_model(request, monkeypatch):
    """Every test recognises subjects with the fake model and a 3-species list, except the
    tests of the photo dataset (marked real_model), which use the real image model."""
    if request.node.get_closest_marker("real_model"):
        return
    monkeypatch.setattr(subjects, "text", FakeText())
    monkeypatch.setattr(subjects, "species_names", lambda: list(SPECIES))


# ---------- The photo dataset (tests/dataset/, test_dataset.py): only with --dataset ----------

REPO_DATASET = Path(__file__).resolve().parent / "dataset"


def pytest_addoption(parser):
    parser.addoption("--dataset", nargs="?", const=str(REPO_DATASET), default=None, metavar="FOLDER",
                     help="also check a photo dataset with the real analysis and image model: the one of "
                          "this repository (tests/dataset), or --dataset=FOLDER for your own (made with "
                          "tests/make_dataset.py). Slow the first time, cached afterwards.")


def pytest_configure(config):
    config.addinivalue_line("markers", "real_model: uses the real image model on the photo dataset")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--dataset") is not None:
        return
    skip = pytest.mark.skip(reason="the photo dataset: run with --dataset")
    for item in items:
        if "real_model" in item.keywords:
            item.add_marker(skip)


# ---------- A made-up library of analysed photos ----------
GOOD = {"sharpness": 200.0, "clipped": 0.0, "pixels": 18e6, "pale_flat": 0.0, "rest_colour": 30.0,
        "brightest": 200.0, "middle_brightness": 120.0, "blur": -0.02, "subject_area": 0.1, "subject_blur": 0.3, "softness": 0.3}
DAY = 24 * 3600
START = 1744776000.0  # 16 Apr 2025, morning


def make_library(folder, photos):
    """A Library from a list of dicts: {"emb": embedding, "taken": seconds after START, plus
    any analysis value that differs from a good photo}. Files are named p00.jpg, p01.jpg, ..."""
    n = len(photos)
    data = {field: np.array([p.get(field, GOOD[field]) for p in photos], dtype=float) for field in GOOD}
    data["embedding"] = np.array([p["emb"] for p in photos])
    data["taken"] = np.array([START + p.get("taken", 10 * i) for i, p in enumerate(photos)])
    keys = [f"p{i:02d}.jpg|1000|{i}" for i in range(n)]
    return Library(Path(folder), keys, data)


@pytest.fixture
def new_project(tmp_path, monkeypatch):
    """make a project in an empty temporary folder: new_project(photos) -> Project."""
    monkeypatch.setattr(project_module, "RECENT_FILE", tmp_path / "recent_folders.json")

    def make(photos):
        folder = tmp_path / "photos"
        folder.mkdir(exist_ok=True)
        project = Project(folder)
        project.library = make_library(folder, photos)
        return project
    return make


@pytest.fixture
def steps():
    """Fresh step objects, connected as in the app: step 1 → step 2 → step 3."""
    grouping = GroupSimilarStep()
    picking = PickPhotosStep(grouping)
    return grouping, picking, ExportStep(picking)


def set_groups(project, grouping, groups):
    """Put the photos into these groups (lists of photo ids), as step 1 would."""
    project.step_state("group")["settings"] = {"similarity": 0.9, "seconds": 120}
    grouping.store(project, groups)
