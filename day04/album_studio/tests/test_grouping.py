"""Step 1, grouping similar photos (studio/steps/group_similar.py)."""
import numpy as np
import pytest
from werkzeug.datastructures import MultiDict

from conftest import LION, PEOPLE, VIEW, photo, set_groups
from studio.steps.group_similar import group_photos


def unit(degrees):
    """A 2-D embedding at this angle: two of them are cos(difference) similar."""
    a = np.radians(degrees)
    return np.array([np.cos(a), np.sin(a)])


# ---------- group_photos(): the grouping rule ----------

def test_alike_photos_taken_close_together_form_one_group():
    embeddings = np.array([unit(0), unit(5), unit(90), unit(92)])
    taken = np.array([0, 2, 4, 6])
    assert group_photos(embeddings, taken, similarity=0.9, max_gap=60) == [[0, 1], [2, 3]]


def test_a_long_time_gap_starts_a_new_group():
    embeddings = np.array([unit(0), unit(1)])
    assert group_photos(embeddings, np.array([0, 600]), 0.9, max_gap=120) == [[0], [1]]
    assert group_photos(embeddings, np.array([0, 600]), 0.9, max_gap=np.inf) == [[0, 1]]  # "any time"


def test_photos_are_compared_with_the_groups_first_photo():
    # each photo is close to the previous one, but the third is far from the first:
    # no long chains that would merge a whole game drive into one group
    embeddings = np.array([unit(0), unit(20), unit(40)])
    assert group_photos(embeddings, np.array([0, 1, 2]), similarity=np.cos(np.radians(30)),
                        max_gap=60) == [[0, 1], [2]]


def test_a_stricter_similarity_makes_more_groups():
    embeddings = np.array([unit(a) for a in (0, 10, 20, 30)])
    taken = np.arange(4)
    loose = group_photos(embeddings, taken, similarity=0.80, max_gap=60)
    strict = group_photos(embeddings, taken, similarity=0.99, max_gap=60)
    assert len(loose) < len(strict) == 4


# ---------- The step, on a small project ----------

@pytest.fixture
def project(new_project):
    """6 photos: a burst of 3 lion photos, 2 photos of people, 1 view."""
    return new_project([{"emb": photo(*LION, noise=0.01, seed=i)} for i in range(3)]
                       + [{"emb": photo(*PEOPLE, noise=0.01, seed=i)} for i in range(2)]
                       + [{"emb": photo(*VIEW)}])


def test_groups_are_made_automatically_the_first_time(project, steps):
    grouping = steps[0]
    assert grouping.groups(project) == [[0, 1, 2], [3, 4], [5]]
    assert grouping.summary(project) == "3 groups"


def test_groups_are_saved_by_file_name(project, steps):
    steps[0].groups(project)
    assert project.step_state("group")["groups"][0] == ["p00.jpg", "p01.jpg", "p02.jpg"]


def test_merge_split_and_make_single(project, steps):
    grouping = steps[0]
    grouping.groups(project)
    grouping.action(project, "merge", {"groups": [1, 2]})
    assert grouping.groups(project) == [[0, 1, 2], [3, 4, 5]]
    grouping.action(project, "split", {"photos": [1, 2]})
    assert grouping.groups(project) == [[0], [1, 2], [3, 4, 5]]
    grouping.action(project, "ungroup", {"photos": [4, 5]})
    assert grouping.groups(project) == [[0], [1, 2], [3], [4], [5]]
    assert project.step_state("group")["edited"] is True


def test_regrouping_replaces_changes_by_hand(project, steps):
    grouping = steps[0]
    grouping.groups(project)
    grouping.action(project, "ungroup", {"photos": [0]})
    grouping.action(project, "regroup", {"similarity": 0.9, "seconds": 120})
    assert grouping.groups(project) == [[0, 1, 2], [3, 4], [5]]
    assert project.step_state("group")["edited"] is False


def test_bad_photos_are_hidden_unless_kept(new_project, steps):
    grouping = steps[0]
    project = new_project([{"emb": photo(*LION)}, {"emb": photo(*LION), "sharpness": 5}])  # photo 1 is blurry
    assert grouping.hidden(project) == {1}
    grouping.action(project, "keep", {"photo": 1, "on": True})
    assert grouping.hidden(project) == set()


def test_hiding_by_hand_and_keeping_exclude_each_other(project, steps):
    grouping = steps[0]
    grouping.action(project, "reject", {"photo": 0, "on": True})
    assert grouping.hidden(project) == {0}
    grouping.action(project, "keep", {"photo": 0, "on": True})  # changing one's mind
    state = project.step_state("group")
    assert state["keep"] == ["p00.jpg"] and state["rejected"] == []
    assert grouping.hidden(project) == set()


def test_the_switch_shows_all_photos(new_project, steps):
    grouping = steps[0]
    project = new_project([{"emb": photo(*LION), "brightest": 20}])  # too dark
    assert grouping.hidden(project) == {0}
    grouping.action(project, "hide_problems", {"hide": False})
    assert grouping.hidden(project) == set()


# ---------- The forms: wrong input is refused with a message ----------

def test_merging_needs_two_groups(project, steps):
    grouping = steps[0]
    set_groups(project, grouping, [[0, 1, 2], [3, 4], [5]])
    with pytest.raises(ValueError, match="two or more"):
        grouping.form_action(project, "merge", MultiDict([("group", "0")]))
    assert grouping.form_action(project, "merge", MultiDict([("group", "0"), ("group", "3")])) \
        == "Merged 2 groups into one"


def test_moving_photos_needs_some_but_not_all(project, steps):
    grouping = steps[0]
    set_groups(project, grouping, [[0, 1, 2], [3, 4], [5]])
    with pytest.raises(ValueError, match="not all"):
        grouping.form_action(project, "split", MultiDict([("ticked", "3"), ("ticked", "4")]))
    assert grouping.form_action(project, "ungroup", MultiDict([("ticked", "4")])) == "1 photo is now single"


def test_grouping_settings_must_be_numbers(project, steps):
    with pytest.raises(ValueError, match="numbers"):
        steps[0].form_action(project, "regroup", MultiDict({"similarity": "a lot", "seconds": "any"}))
