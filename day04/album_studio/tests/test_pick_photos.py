"""Step 2, picking photos (studio/steps/pick_photos.py)."""
import pytest
from werkzeug.datastructures import MultiDict

from conftest import DAY, LION, PEOPLE, UNKNOWN_ANIMAL, VIEW, WILDEBEEST, ZEBRA, photo, set_groups
from studio import subjects

LIONS, PEOPLE_GROUP, VIEW_GROUP = [0, 1, 2], [3, 4], [5]
HERD = list(range(6, 18))  # 12 photos: wildebeest, with 2 zebra photos (10, 11) and 1 unknown animal (12)


def trip(zebras=(10, 11)):
    photos = [{"emb": photo(*LION), "sharpness": s} for s in (100, 300, 200)]   # photo 1 is the sharpest
    photos += [{"emb": photo(*PEOPLE)}, {"emb": photo(*PEOPLE)}, {"emb": photo(*VIEW)}]
    for i in HERD:  # the herd on day 2
        contents = ZEBRA if i in zebras else UNKNOWN_ANIMAL if i == 12 else WILDEBEEST
        photos.append({"emb": photo(*contents), "taken": DAY + 10 * i})
    return photos


@pytest.fixture
def setup(new_project, steps):
    """The trip's project, its 4 groups, and the steps."""
    project = new_project(trip())
    grouping, picking, _ = steps
    set_groups(project, grouping, [LIONS, PEOPLE_GROUP, VIEW_GROUP, HERD])
    return project, grouping, picking


def card(picking, project, key):
    return next(c for c in picking.cards(project) if c["key"] == key)


def settings(**changes):
    return {"subject": "", "show": "all", "order": "time", **changes}


# ---------- Cards and their subjects ----------

def test_one_card_per_group_with_its_subject(setup):
    project, _, picking = setup
    assert [(c["key"], c["subject"]) for c in picking.cards(project)] == \
        [(0, "lion"), (3, "people"), (5, "views"), (6, "wildebeest")]


def test_a_card_shows_the_best_photo_until_one_is_picked(setup):
    project, _, picking = setup
    assert card(picking, project, 0)["cover"] == 1
    picking.action(project, "pick", {"photo": 2, "on": True})
    assert card(picking, project, 0)["cover"] == 2


def test_a_large_group_also_lists_the_other_subject_its_photos_show(setup):
    project, _, picking = setup
    herd = card(picking, project, 6)
    assert sorted(herd["minor"]) == ["zebra"] and sorted(herd["minor"]["zebra"]) == [10, 11]
    assert herd["labels"][10] == "zebra" and herd["labels"][12] == "wildebeest"  # "other animals" says nothing


def test_one_photo_of_another_subject_is_not_enough(new_project, steps):
    project = new_project(trip(zebras=(10,)))
    grouping, picking, _ = steps
    set_groups(project, grouping, [LIONS, PEOPLE_GROUP, VIEW_GROUP, HERD])
    assert card(picking, project, 6)["minor"] == {}


def test_a_corrected_group_has_one_subject(setup):
    project, _, picking = setup
    picking.action(project, "set_subject", {"group": 6, "subject": "wildebeest"})
    assert card(picking, project, 6)["minor"] == {}


# ---------- Picking ----------

def test_picks_are_saved_by_file_name_and_counted(setup):
    project, _, picking = setup
    picking.action(project, "pick", {"photo": 4, "on": True})
    picking.action(project, "pick", {"photo": 10, "on": True})
    assert project.step_state("pick")["picked"] == ["p04.jpg", "p10.jpg"]
    assert picking.picked_count(project) == 2 and picking.summary(project) == "2 picked"
    picking.action(project, "pick", {"photo": 4, "on": False})
    assert picking.picked_count(project) == 1


def test_a_photo_hidden_in_step_1_leaves_the_album_and_comes_back(setup):
    project, grouping, picking = setup
    picking.action(project, "pick", {"photo": 0, "on": True})
    grouping.action(project, "reject", {"photo": 0, "on": True})
    assert picking.picked_count(project) == 0
    grouping.action(project, "reject", {"photo": 0, "on": False})
    assert picking.picked_count(project) == 1


def test_picks_and_corrections_survive_regrouping(setup):
    project, grouping, picking = setup
    picking.action(project, "pick", {"photo": 1, "on": True})
    picking.action(project, "set_subject", {"group": 3, "subject": "views"})
    grouping.action(project, "ungroup", {"photos": [4]})  # step 1 changes
    assert picking.picked_count(project) == 1
    assert card(picking, project, 3)["subject"] == "views"


# ---------- Hiding (not interesting), with Undo ----------

def test_hiding_a_group_takes_it_and_its_picks_out_and_undo_brings_them_back(setup):
    project, _, picking = setup
    picking.action(project, "pick", {"photo": 1, "on": True})
    message, undo = picking.form_action(project, "hide", MultiDict({"group": "0", "hide": "1"}))
    assert message == "3 photos hidden · 1 picked photo left the album"
    assert card(picking, project, 0)["dismissed"] and picking.picked_count(project) == 0
    picking.form_action(project, "hide", MultiDict(undo))
    assert not card(picking, project, 0)["dismissed"] and picking.picked_count(project) == 1


def test_hiding_the_last_photo_of_a_group_hides_the_group(setup):
    project, _, picking = setup
    picking.form_action(project, "hide", MultiDict({"photo": "3"}))
    message, _ = picking.form_action(project, "hide", MultiDict({"photo": "4"}))
    assert message == "Photo hidden · that was the last one, so the whole group is hidden now"
    assert card(picking, project, 3)["dismissed"]


def test_hidden_groups_are_only_on_the_hidden_tab(setup):
    project, _, picking = setup
    picking.form_action(project, "hide", MultiDict({"group": "5", "hide": "1"}))
    keys = lambda s: [c["key"] for c, _ in picking.listing(project, s)["listed"]]  # noqa: E731
    assert 5 not in keys(settings())
    assert keys(settings(show="hidden")) == [5]


# ---------- Filters, order, and going through the groups ----------

def test_a_subject_filter_also_finds_the_photos_of_it_inside_a_large_group(setup):
    project, _, picking = setup
    listed = picking.listing(project, settings(subject="zebra"))["listed"]
    assert [(c["key"], focus) for c, focus in listed] == [(6, "zebra")]
    view = picking.card_view(project, listed[0][0], "zebra", settings(subject="zebra"))
    assert view["cover"] in (10, 11) and view["count_text"] == "2 of 12 photos"


def test_category_filters(setup):
    project, _, picking = setup
    keys = lambda subject: [c["key"] for c, _ in picking.listing(project, settings(subject=subject))["listed"]]  # noqa: E731
    assert keys("animals") == [0, 6]
    assert keys("people") == [3]
    assert keys("views") == [5]


def test_show_picked_and_not_picked(setup):
    project, _, picking = setup
    picking.action(project, "pick", {"photo": 5, "on": True})
    keys = lambda show: [c["key"] for c, _ in picking.listing(project, settings(show=show))["listed"]]  # noqa: E731
    assert keys("picked") == [5]
    assert keys("unpicked") == [0, 3, 6]


def test_previous_and_next_group_follow_the_list(setup):
    project, _, picking = setup
    s = settings()
    info = picking.listing(project, s)
    assert picking.neighbours(project, 3, s, info)[:3] == (0, 5, 2)    # before, after, position
    assert picking.neighbours(project, 0, s, info)[:2] == (None, 3)


def test_a_group_that_just_left_the_list_keeps_its_place(setup):
    # picked while showing "Not picked": Next still goes on from where it was
    project, _, picking = setup
    picking.action(project, "pick", {"photo": 4, "on": True})
    s = settings(show="unpicked")
    assert picking.neighbours(project, 3, s, picking.listing(project, s))[:2] == (0, 5)


# ---------- The forms: subjects, target, wrong input ----------

def test_correcting_a_subject_and_going_back(setup):
    project, _, picking = setup
    assert picking.form_action(project, "set_subject", MultiDict({"group": "3", "subject": "lion"})) \
        == "Subject set to Lion"
    assert card(picking, project, 3)["subject"] == "lion" and card(picking, project, 3)["corrected"]
    picking.form_action(project, "set_subject", MultiDict({"group": "3", "subject": ""}))
    assert card(picking, project, 3)["subject"] == "people"


def test_a_typed_animal_is_tidied_up(setup):
    project, _, picking = setup
    picking.form_action(project, "set_subject", MultiDict({"group": "0", "custom": "  Dung   BEETLE ", "subject": "zebra"}))
    assert card(picking, project, 0)["subject"] == "dung beetle"  # the typed name wins over the menu
    picking.form_action(project, "set_subject", MultiDict({"group": "0", "custom": "x" * 100}))
    assert len(card(picking, project, 0)["subject"]) == 40


def test_a_group_that_no_longer_exists_is_refused(setup):
    project, _, picking = setup
    with pytest.raises(KeyError, match="changed"):
        picking.action(project, "set_subject", {"group": 99, "subject": "lion"})


def test_reaching_the_target_is_announced(setup):
    project, _, picking = setup
    picking.form_action(project, "set_target", MultiDict({"target": "2"}))
    assert picking.form_action(project, "toggle_pick", MultiDict({"photo": "0"})) == ""
    assert picking.form_action(project, "toggle_pick", MultiDict({"photo": "3"})) == "That's 2 photos, your target."


@pytest.mark.parametrize("form, error", [
    ({"photo": "abc"}, "No such photo"), ({"photo": "999"}, "No such photo"),
])
def test_picking_a_photo_that_does_not_exist(setup, form, error):
    project, _, picking = setup
    with pytest.raises(ValueError, match=error):
        picking.form_action(project, "toggle_pick", MultiDict(form))


@pytest.mark.parametrize("value, error", [("ten", "whole number"), ("0", "at least 1")])
def test_a_wrong_target_is_refused(setup, value, error):
    project, _, picking = setup
    with pytest.raises(ValueError, match=error):
        picking.form_action(project, "set_target", MultiDict({"target": value}))


def test_labels_of_subjects_in_the_menu(setup):
    project, _, picking = setup
    _, data = picking.group_page(project, 0, {})
    animals = [value for value, _ in data["animal_options"]]
    assert animals[-1] == subjects.OTHER_ANIMALS and "lion" in animals
    assert [value for value, _ in data["other_options"]] == ["people", "views", "other"]
