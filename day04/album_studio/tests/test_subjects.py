"""Recognising what is in the photos (studio/subjects.py), with the fake model of conftest.py."""
import numpy as np

from conftest import LION, PEOPLE, UNKNOWN_ANIMAL, VIEW, WILDEBEEST, ZEBRA, photo
from studio import subjects


def recognise(*groups):
    """Recognise groups given as lists of photo contents, e.g. recognise([LION, LION], [VIEW])."""
    embeddings, ids = [], []
    for group in groups:
        ids.append(list(range(len(embeddings), len(embeddings) + len(group))))
        embeddings += [photo(*contents) for contents in group]
    return subjects.recognise(np.array(embeddings), ids)


def test_each_kind_of_subject_is_recognised():
    assert recognise([LION], [ZEBRA], [PEOPLE], [VIEW]) == ["lion", "zebra", "people", "views"]


def test_an_animal_of_no_known_species_is_other_animals():
    assert recognise([UNKNOWN_ANIMAL]) == [subjects.OTHER_ANIMALS]


def test_an_uncertain_species_is_other_animals():
    # as much lion as zebra as wildebeest: no species reaches the 50% needed
    assert recognise([("animals", "lion", "zebra", "wildebeest")]) == [subjects.OTHER_ANIMALS]


def test_all_photos_of_a_group_decide_together():
    # one odd frame does not change the subject of a burst
    assert recognise([LION, LION, LION, ZEBRA]) == ["lion"]
    assert recognise([PEOPLE, PEOPLE, VIEW]) == ["people"]


def test_frames_without_animals_do_not_vote_on_the_species():
    # 2 wildebeest frames and 5 frames that are a bit of everything except animals. Animals is
    # still the strongest category; if the 5 frames voted on the species too, wildebeest would
    # fall below 50% (2 + 5 x 0.25 out of 7) and the group would be "other animals".
    unclear = ("people", "views", "other")
    assert recognise([WILDEBEEST, WILDEBEEST] + [unclear] * 5) == ["wildebeest"]


def test_no_groups_no_work():
    assert subjects.recognise(np.zeros((0, 10)), []) == []


def test_probabilities_sum_to_one_and_follow_similarity():
    embeddings = np.array([photo(*LION)])
    probs = subjects.probabilities(embeddings, [photo("animals"), photo("people")])
    assert abs(probs.sum() - 1) < 1e-9
    assert probs[0, 0] > 0.99  # an animal photo matches "animals" far better than "people"


def test_labels_and_categories():
    assert subjects.label("lion") == "Lion"
    assert subjects.label("grey crowned crane") == "Grey crowned crane"
    assert subjects.label(subjects.OTHER_ANIMALS) == "Other animals"
    assert subjects.label("people") == "People"
    assert [subjects.category_of(s) for s in ("lion", "dung beetle", "people", "views", "other")] \
        == ["animals", "animals", "people", "views", "other"]


def test_the_species_list_file(monkeypatch):
    monkeypatch.undo()  # the real species list, not the 3 test species
    names = subjects.species_names()
    assert "lion" in names and "warthog" in names
    assert not any(n.startswith("#") or not n for n in names)
    prompts = subjects.all_prompts()
    assert len(prompts) == len(set(prompts))  # no description twice
    assert subjects.species_prompt("lion") in prompts
