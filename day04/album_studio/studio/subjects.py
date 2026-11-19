"""Recognising what is in the photos: animals (and which species), people, views or other things.

The photos' CLIP embeddings are already stored by analysis.py. Recognition compares them with
text descriptions ("a photo of a giraffe") embedded by the same model. Only the text needs the
model, so the text embeddings are cached in text_embeddings.npz next to the app: after the first
time, recognising a whole folder takes a fraction of a second.

The prompts and rules come from the day03 album picker, where they were tuned on the real photos:
the species is decided by all photos of a group together, and only when the model is confident.
"""
import logging
from pathlib import Path

import numpy as np

from .analysis import MODEL_NAME, Clip, normalize

log = logging.getLogger(__name__)  # debug lines: shown by the tests when a test fails

APP_DIR = Path(__file__).resolve().parent.parent
TEXT_CACHE = APP_DIR / "text_embeddings.npz"
SPECIES_FILE = Path(__file__).with_name("species_africa.txt")

CATEGORIES = ["animals", "people", "views", "other"]  # in the order the filters show them
CATEGORY_PROMPTS = {
    "animals": ["a photo of a wild animal", "a photo of a bird", "a photo of animals in the grass"],
    "people": ["a photo of people", "a selfie", "a portrait of a person", "a group photo of friends on a trip",
               "a photo of a person sitting in a car", "a photo of people looking through binoculars",
               # with only the prompts above, people in front of the savanna counted as animal photos
               "a photo of people on a safari", "a man standing in the savanna", "a woman standing in the savanna",
               "people looking through binoculars in the savanna", "a tourist taking photos from a safari car",
               "a portrait of a man outdoors", "a portrait of a woman outdoors"],
    "views": ["a landscape photo", "a photo of scenery", "a photo of a sunset",
              "a view of the savanna", "a photo of mountains"],
    # so photos of food, cars, screenshots etc. are not forced into one of the others
    "other": ["a photo of food", "a photo of a car", "a photo of safari jeeps", "a photo of a building",
              "a photo of a hotel room", "a photo of a pet cat or dog at home", "a screenshot",
              "a photo of a document"],
}
# An animal that matches these better than any listed species gets no species name
UNKNOWN_SPECIES_PROMPTS = ["a photo of a bird", "a photo of an animal", "a photo of grass"]
SPECIES_MIN_CONFIDENCE = 0.5
OTHER_ANIMALS = "other animals"   # the subject of animals whose species is not known
LABELS = {"people": "People", "views": "Views", "other": "Other", OTHER_ANIMALS: "Other animals"}


def species_names():
    lines = SPECIES_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def species_prompt(name):
    return f"a photo of a {name}."


def all_prompts():
    prompts = [p for ps in CATEGORY_PROMPTS.values() for p in ps] + UNKNOWN_SPECIES_PROMPTS
    return list(dict.fromkeys(prompts + [species_prompt(s) for s in species_names()]))


def label(subject):
    """How a subject is shown: 'lion' -> 'Lion', 'people' -> 'People'."""
    return LABELS.get(subject) or subject[:1].upper() + subject[1:]


def category_of(subject):
    """people, views and other are categories of their own; every other subject is an animal."""
    return subject if subject in ("people", "views", "other") else "animals"


class TextEmbeddings:
    """Prompt -> embedding, saved in TEXT_CACHE so the model is loaded only for new prompts."""

    def __init__(self):
        self.vectors = {}
        if TEXT_CACHE.exists():
            data = np.load(TEXT_CACHE)
            if str(data["model"]) == MODEL_NAME:
                self.vectors = dict(zip((str(k) for k in data["prompts"]), data["vectors"]))

    def missing(self, prompts):
        return [p for p in prompts if p not in self.vectors]

    def compute(self, prompts):
        """Embed new prompts with the CLIP model (slow the first time: the model is loaded)."""
        todo = self.missing(prompts)
        if todo:
            self.vectors.update(zip(todo, Clip.get().embed_prompts(todo)))
            np.savez(TEXT_CACHE, model=MODEL_NAME, prompts=np.array(list(self.vectors)),
                     vectors=np.array(list(self.vectors.values())))

    def describe(self, prompts):
        """One embedding for a class described by several prompts (their normalised mean)."""
        return normalize(np.mean([self.vectors[p] for p in prompts], axis=0))


text = TextEmbeddings()


def probabilities(embeddings, classes):
    """For each photo, how much it matches each class (rows sum to 1)."""
    logits = 100 * embeddings @ np.array(classes).T
    logits -= logits.max(axis=1, keepdims=True)
    probs = np.exp(logits)
    return probs / probs.sum(axis=1, keepdims=True)


def recognise(embeddings, groups):
    """The subject of every group: a species name, 'other animals', 'people', 'views' or 'other'.

    embeddings: the photos' CLIP embeddings; groups: lists of photo indexes (the visible photos of
    each group). All photos of a group vote together, so one odd frame does not decide."""
    if not groups:
        return []
    names = species_names()
    category_probs = probabilities(embeddings, [text.describe(CATEGORY_PROMPTS[c]) for c in CATEGORIES])
    species_classes = [text.describe([species_prompt(s)]) for s in names] + \
                      [text.describe([p]) for p in UNKNOWN_SPECIES_PROMPTS]
    subjects = []
    for ids in groups:
        mean = category_probs[ids].mean(axis=0)
        category = CATEGORIES[int(mean.argmax())]
        shares = ", ".join(f"{c} {p:.2f}" for c, p in zip(CATEGORIES, mean)) if log.isEnabledFor(logging.DEBUG) else ""
        if category != "animals":
            log.debug("group of photos %s: %s (categories: %s)", ids, category, shares)
            subjects.append(category)
            continue
        animal_ids = [i for i in ids if category_probs[i].argmax() == 0] or ids  # the frames showing animals
        votes = probabilities(embeddings[animal_ids], species_classes).mean(axis=0)
        best = int(votes.argmax())
        known = best < len(names) and votes[best] >= SPECIES_MIN_CONFIDENCE
        best_name = names[best] if best < len(names) else "an unknown species"
        log.debug("group of photos %s: animals (categories: %s); species vote of frames %s: %s %.2f "
                  "(needs %s) -> %s", ids, shares, animal_ids, best_name, votes[best], SPECIES_MIN_CONFIDENCE,
                  names[best] if known else OTHER_ANIMALS)
        subjects.append(names[best] if known else OTHER_ANIMALS)
    return subjects
