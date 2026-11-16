"""Step 3, arranging and saving the album (studio/steps/export.py)."""
import time

import pytest
from werkzeug.datastructures import MultiDict

from conftest import DAY, LION, PEOPLE, VIEW, photo, set_groups
from studio.steps.export import FOLDER_NAME, PAGE_NAME


@pytest.fixture
def setup(new_project, steps):
    """5 photos over 2 days: a lion and a view on day 1; people, a view and a lion on day 2.
    Each photo is its own group, and the photo files really exist (with their own bytes)."""
    contents = [LION, VIEW, PEOPLE, VIEW, LION]
    taken = [0, 60, DAY, DAY + 60, DAY + 120]
    project = new_project([{"emb": photo(*c), "taken": t} for c, t in zip(contents, taken)])
    for i, name in enumerate(project.library.files):
        (project.folder / name).write_bytes(f"photo {i}".encode())
    grouping, picking, export = steps
    set_groups(project, grouping, [[i] for i in range(5)])
    return project, grouping, picking, export


def pick(picking, project, *ids):
    for i in ids:
        picking.action(project, "pick", {"photo": i, "on": True})


def album(export, project):
    """[(section title, [(number, photo id), ...]), ...]"""
    return [(s["title"], [(p["number"], p["id"]) for p in s["photos"]]) for s in export.album(project)]


def wait_for(job):
    for _ in range(100):
        if job.finished:
            return
        time.sleep(0.05)
    raise TimeoutError


def test_the_album_in_trip_order_numbered_across_days(setup):
    project, _, picking, export = setup
    pick(picking, project, 4, 0, 2)
    assert album(export, project) == [("Day 1 · Wed 16 Apr 2025", [(1, 0)]),
                                      ("Day 2 · Thu 17 Apr 2025", [(2, 2), (3, 4)])]


def test_the_album_by_subject_in_the_order_first_met_on_the_trip(setup):
    project, _, picking, export = setup
    pick(picking, project, 0, 1, 2, 3, 4)
    export.action(project, "set_order", {"order": "subject"})
    assert album(export, project) == [("Lion", [(1, 0), (2, 4)]), ("Views", [(3, 1), (4, 3)]),
                                      ("People", [(5, 2)])]


def test_photos_hidden_since_they_were_picked_are_left_out(setup):
    project, grouping, picking, export = setup
    pick(picking, project, 0, 1)
    grouping.action(project, "reject", {"photo": 0, "on": True})            # a bad photo (step 1)
    assert album(export, project) == [("Day 1 · Wed 16 Apr 2025", [(1, 1)])]
    picking.form_action(project, "hide", MultiDict({"group": "1", "hide": "1"}))  # not interesting (step 2)
    assert album(export, project) == []


def test_file_names_start_with_the_album_number(setup):
    project, _, _, export = setup
    assert export.file_name(project, {"number": 7, "id": 2}) == "007 p02.jpg"


def test_saving_copies_the_originals_in_album_order(setup):
    project, _, picking, export = setup
    pick(picking, project, 3, 0)
    export.action(project, "export", {"page": "<html>album</html>"})
    wait_for(export.job)
    folder = project.folder / FOLDER_NAME
    assert sorted(f.name for f in folder.iterdir()) == ["001 p00.jpg", "002 p03.jpg", PAGE_NAME]
    assert (folder / "002 p03.jpg").read_bytes() == b"photo 3"          # the original's bytes
    assert (project.folder / "p03.jpg").read_bytes() == b"photo 3"      # the original is untouched
    assert export.summary(project) == "saved 2 photos"


def test_saving_again_replaces_only_the_earlier_export(setup):
    project, _, picking, export = setup
    pick(picking, project, 0, 1)
    export.action(project, "export", {"page": "first"})
    wait_for(export.job)
    folder = project.folder / FOLDER_NAME
    (folder / "my notes.txt").write_text("not the app's")
    picking.action(project, "pick", {"photo": 0, "on": False})
    export.action(project, "export", {"page": "second"})
    wait_for(export.job)
    assert sorted(f.name for f in folder.iterdir()) == ["001 p01.jpg", PAGE_NAME, "my notes.txt"]
    assert (folder / PAGE_NAME).read_text() == "second"


def test_nothing_to_save_without_picks(setup):
    project, _, _, export = setup
    with pytest.raises(ValueError, match="Pick some photos"):
        export.action(project, "export", {"page": ""})


def test_an_unknown_order_is_refused(setup):
    project, _, _, export = setup
    with pytest.raises(ValueError, match="Unknown order"):
        export.form_action(project, "set_order", MultiDict({"order": "random"}))
