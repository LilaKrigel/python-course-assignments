"""Step 2: pick the photos for the album, finding them by what is in them.

Every group from step 1 is one card, labelled with its subject (subjects.py). The user filters
and orders the cards by subject, picks photos, opens a group to pick the interesting ones (any
number), hides what they don't want to see, and corrects wrong subjects. Picks, hidden photos and
corrections are saved per photo file, so they survive regrouping in step 1.

The first half is the business logic; the second half prepares the web pages and reads their forms.
"""
from collections import Counter
from datetime import datetime
from urllib.parse import urlencode

from .. import subjects
from ..project import Job
from .base import Step
from .group_similar import format_day

SHOW_OPTIONS = [("all", "All"), ("picked", "Picked"), ("unpicked", "Not picked"), ("hidden", "Hidden")]
ORDER_OPTIONS = [("time", "Trip order"), ("subject", "By subject"), ("quality", "Best first")]
CATEGORY_LABELS = {"animals": "Animals", "people": "People", "views": "Views", "other": "Other"}
MAX_SUBJECT_LENGTH = 40
# Large groups often mix subjects (a few warthogs in a group of wildebeest). In groups of at least
# MIXED_MIN photos every photo is also recognised on its own; another subject shown by at least
# MINOR_MIN of them is listed too, so the subject filter finds it.
MIXED_MIN = 10
MINOR_MIN = 2
DEFAULTS = {"subject": "", "show": "all", "order": "time"}


class PickPhotosStep(Step):
    id = "pick"
    title = "Pick photos"
    tagline = "Find photos by what's in them (animals, people, views) and pick the ones for the album."
    description = "Choose the photos for your album. Click a group to see all its photos; ♡ picks a photo."
    template = "steps/pick_photos.html"

    def __init__(self, grouping):
        self.grouping = grouping  # step 1: its groups and the photos it hides
        self.job = None

    # ---------- Business logic ----------

    def picked_files(self, project):
        return set(project.step_state(self.id).get("picked", []))

    def hidden_files(self, project):
        """Photos the user hid in this step (not interesting); different from step 1's bad photos."""
        return set(project.step_state(self.id).get("hidden", []))

    def cards(self, project):
        """One card per group that has photos left after step 1: its shown photos (best first; if
        the user hid them all, the hidden ones), the photos hidden here, the picked ones, its
        subject (corrected by the user, or recognised from all its photos), the subject of each
        photo ("labels"), and other subjects that a large group also shows ("minor")."""
        lib, state = project.library, project.step_state(self.id)
        bad, groups = self.grouping.hidden(project), self.grouping.groups(project)
        visible = [[i for i in g if i not in bad] for g in groups]
        pairs = [(g, ids) for g, ids in zip(groups, visible) if ids]
        recognised = subjects.recognise(lib.embedding, [ids for _, ids in pairs])
        large = [i for _, ids in pairs if len(ids) >= MIXED_MIN for i in ids]
        per_photo = dict(zip(large, subjects.recognise(lib.embedding, [[i] for i in large])))
        picked, skipped = self.picked_files(project), self.hidden_files(project)
        corrections = state.get("subjects", {})
        cards = []
        for (group, ids), auto in zip(pairs, recognised):
            best_first = sorted(ids, key=lambda i: -lib.quality[i])
            shown = [i for i in best_first if lib.files[i] not in skipped]
            out = [i for i in best_first if lib.files[i] in skipped]
            chosen = [i for i in shown if lib.files[i] in picked]
            corrected = Counter(corrections[lib.files[i]] for i in group if lib.files[i] in corrections)
            subject = corrected.most_common(1)[0][0] if corrected else auto
            labels = {i: subject for i in ids}
            if not corrected and len(ids) >= MIXED_MIN:  # a correction says what the whole group shows
                found = Counter(per_photo[i] for i in ids)
                minors = {s for s, n in found.items() if s != subject and n >= MINOR_MIN
                          and s not in (subjects.OTHER_ANIMALS, "other")}  # not informative
                labels = {i: per_photo[i] if per_photo[i] in minors else subject for i in ids}
            listed = shown or out
            minor = {}
            for i in listed:
                if labels[i] != subject:
                    minor.setdefault(labels[i], []).append(i)
            cards.append({"key": group[0], "photos": listed, "hidden": out, "dismissed": not shown,
                          "all": sorted(ids, key=lambda i: lib.taken[i]), "picked": chosen,
                          "cover": (chosen or shown or out)[0], "subject": subject, "labels": labels,
                          "minor": minor, "recognised": auto, "corrected": bool(corrected)})
        return cards

    def picked_count(self, project):
        """Picked photos that are still shown (a photo hidden in step 1 or here leaves the album)."""
        lib = project.library
        bad = {lib.files[i] for i in self.grouping.hidden(project)}
        return len(self.picked_files(project) & set(lib.files) - bad - self.hidden_files(project))

    def summary(self, project):
        if not project.library:
            return ""
        n = self.picked_count(project)
        return f"{n} picked" if n else ""

    def get(self, project):
        return {"target": project.step_state(self.id).get("target"),
                "groups": [{"key": int(c["key"]), "subject": c["subject"], "photos": [int(i) for i in c["all"]],
                            "picked": [int(i) for i in c["picked"]], "hidden": [int(i) for i in c["hidden"]]}
                           for c in self.cards(project)]}

    def action(self, project, name, payload):
        lib, state = project.library, project.step_state(self.id)
        if name == "pick":  # payload: photo, on
            file = lib.files[payload["photo"]]
            state["picked"] = [f for f in state.get("picked", []) if f != file] + ([file] if payload["on"] else [])
        elif name == "hide":  # payload: photos, on (hide them from this step, or show them again)
            files = {lib.files[i] for i in payload["photos"]}
            kept = [f for f in state.get("hidden", []) if f not in files]
            state["hidden"] = kept + (sorted(files) if payload["on"] else [])
        elif name == "set_subject":  # payload: group (its first photo), subject (None: as recognised)
            group = next((g for g in self.grouping.groups(project) if g[0] == payload["group"]), None)
            if group is None:
                raise KeyError("This group has changed. Open it again from the list.")
            corrections = state.setdefault("subjects", {})
            for i in group:
                if payload["subject"]:
                    corrections[lib.files[i]] = payload["subject"]
                else:
                    corrections.pop(lib.files[i], None)
        elif name == "set_target":  # payload: target (a number, or None)
            state["target"] = payload["target"]
        else:
            return super().action(project, name, payload)
        project.save()
        return self.get(project)

    def prepare(self, project):
        """The first time, the text descriptions of the subjects are embedded (loads the model)."""
        if self.job and not self.job.finished:
            return self.job
        if not subjects.text.missing(subjects.all_prompts()):
            return None

        def work(progress):
            progress(0, 0, "Loading the image model…")
            subjects.text.compute(subjects.all_prompts())

        self.job = Job("Recognising what's in your photos", work,
                       "The image model learns the names of the animals on the species list and what "
                       "people and views look like. This takes about a minute, only the first time.")
        return self.job

    # ---------- The web pages ----------

    def page(self, project, view, args):
        if view is None:
            return self.main_page(project, args)
        if view.startswith("group/") and view[6:].isdigit():
            return self.group_page(project, int(view[6:]), args)
        raise LookupError(f"Page not found: {view}")

    @staticmethod
    def settings(args):
        """The main page's settings (subject, show, order) from a URL's ?query."""
        values = {k: args.get(k, DEFAULTS[k]) for k in DEFAULTS}
        if values["show"] not in dict(SHOW_OPTIONS):
            values["show"] = "all"
        if values["order"] not in dict(ORDER_OPTIONS):
            values["order"] = "time"
        return values

    def address(self, view="", **settings):
        """The URL of the main page (or of a group page) with these settings."""
        query = urlencode({k: v for k, v in settings.items() if k in DEFAULTS and v != DEFAULTS[k]})
        return f"/step/{self.id}" + (f"/{view}" if view else "") + (f"?{query}" if query else "")

    @staticmethod
    def focus(card, subject):
        """Under which subject a card is listed for the subject filter (its own subject, or a
        subject that some of its photos show), or None if it doesn't match."""
        if not subject:
            return card["subject"]
        for s in [card["subject"]] + list(card["minor"]):
            if s == subject or (subject in subjects.CATEGORIES and subjects.category_of(s) == subject):
                return s
        return None

    def listing(self, project, settings):
        """Everything the main page lists for these settings: the subjects with their counts, and
        the cards in the order shown, each with the subject it is listed under."""
        lib = project.library
        cards = self.cards(project)
        subject, show, order = settings["subject"], settings["show"], settings["order"]
        # The Hidden tab counts the hidden groups; everywhere else they are left out
        active = [c for c in cards if not c["dismissed"]]
        pool = [c for c in cards if c["dismissed"]] if show == "hidden" else active
        groups_of, picked_of = Counter(), Counter()
        for c in pool:
            for s in {c["subject"], *c["minor"]}:
                groups_of[s] += 1
        for c in active:
            for i in c["picked"]:
                picked_of[c["labels"][i]] += 1
        in_category = {cat: [s for s in groups_of if subjects.category_of(s) == cat] for cat in subjects.CATEGORIES}
        species = sorted(in_category["animals"], key=lambda s: (s == subjects.OTHER_ANIMALS, -groups_of[s], s))
        subject_order = species + [s for cat in ("people", "views", "other") for s in sorted(in_category[cat])]

        listed = []
        for c in pool:
            focus = self.focus(c, subject)
            if focus is not None and (show in ("all", "hidden") or (show == "picked") == bool(c["picked"])):
                listed.append((c, focus))
        if order == "subject":
            listed.sort(key=lambda pair: subject_order.index(pair[1]))
        elif order == "quality":
            listed.sort(key=lambda pair: -lib.quality[self.cover(pair[0], pair[1])])
        return {"cards": cards, "active": active, "pool": pool, "listed": listed, "groups_of": groups_of,
                "picked_of": picked_of, "in_category": in_category, "species": species,
                "subject_order": subject_order}

    @staticmethod
    def cover(card, focus):
        """The photo a card shows when listed under focus: for a subject that only some of its
        photos show, the picked or best one of those."""
        if focus == card["subject"]:
            return card["cover"]
        ids = card["minor"][focus]
        return next((i for i in ids if i in card["picked"]), ids[0])

    def card_view(self, project, card, focus, settings):
        """What a card shows."""
        lib = project.library
        cover = self.cover(card, focus)
        taken = datetime.fromtimestamp(lib.taken[cover])
        name = subjects.label(focus)
        total, count = len(card["all"]), len(card["photos"])
        if focus != card["subject"]:  # listed for some of its photos
            count_text = f"{len(card['minor'][focus])} of {total} photos"
            count_short = f"{len(card['minor'][focus])} of {total}"
        else:
            count_text = f"{count} photo{'s' if count != 1 else ''}" + (
                f" · {len(card['hidden'])} hidden" if card["hidden"] and not card["dismissed"] else "")
            count_short = str(count)
        if len(card["picked"]) > 1:
            count_text = f"♥ {len(card['picked'])} · " + count_text
        soft = lib.is_soft(cover)
        return {"key": card["key"], "cover": cover, "subject": name, "category": subjects.category_of(focus),
                "count": count, "total": total, "count_text": count_text, "count_short": count_short,
                "dismissed": card["dismissed"],
                "picked": len(card["picked"]), "cover_picked": cover in card["picked"], "soft": soft,
                "link": self.address(f"group/{card['key']}", **settings),
                "time": self.grouping.time_span(project, sorted(card["photos"])),
                "caption": f"{name} · {lib.files[cover]} · {format_day(taken)} {taken:%H:%M}"
                           + (" · looks soft" if soft else "")}

    def main_page(self, project, args):
        lib, state = project.library, project.step_state(self.id)
        settings = self.settings(args)
        subject, show, order = settings["subject"], settings["show"], settings["order"]
        info = self.listing(project, settings)
        pool, listed = info["pool"], info["listed"]

        def link(**changes):
            """This page's address with some of its settings changed."""
            return self.address(**{**settings, **changes})

        def chip(key, name, keys):
            keys = set(keys)
            return {"key": key, "label": name, "groups": sum(1 for c in pool if keys & {c["subject"], *c["minor"]}),
                    "picked": sum(info["picked_of"][s] for s in keys), "link": link(subject=key), "on": key == subject}

        in_category = info["in_category"]
        categories = [chip(cat, CATEGORY_LABELS[cat], in_category[cat]) for cat in subjects.CATEGORIES
                      if in_category[cat]]
        species_chips = [chip(s, subjects.label(s), [s]) for s in info["species"]]
        missing = [chip(s, subjects.label(s), [s]) for s in info["subject_order"]
                   if info["picked_of"][s] == 0 and s not in ("other", subjects.OTHER_ANIMALS)] if show != "hidden" else []

        # The cards, in sections
        sections = []
        if order == "time":
            trip_days = sorted({datetime.fromtimestamp(t).date() for t in lib.taken})
            for c, focus in listed:
                day = datetime.fromtimestamp(lib.taken[min(c["photos"])]).date()
                if not sections or sections[-1]["day"] != day:
                    sections.append({"day": day, "title": f"Day {trip_days.index(day) + 1} · {format_day(day)}",
                                     "cards": []})
                sections[-1]["cards"].append((c, focus))
        elif order == "subject":
            for c, focus in listed:
                if not sections or sections[-1]["subject"] != focus:
                    sections.append({"subject": focus, "title": subjects.label(focus), "cards": []})
                sections[-1]["cards"].append((c, focus))
        elif listed:
            sections.append({"title": "", "cards": listed})
        for section in sections:
            section["cards"] = [self.card_view(project, c, focus, settings) for c, focus in section["cards"]]
            section["picked"] = sum(c["picked"] for c in section["cards"])

        picked = self.picked_count(project)
        target = state.get("target")
        current = next((ch for ch in categories + species_chips if ch["on"]), None)
        first = listed[0][0]["key"] if listed else None
        return self.template, {
            "sections": sections, "categories": categories, "species_chips": species_chips, "missing": missing,
            "subject": subject, "subject_label": current["label"] if current else subjects.label(subject),
            "show": show, "order": order, "show_options": SHOW_OPTIONS, "order_options": ORDER_OPTIONS,
            "link": link, "all_link": link(subject=""), "all_groups": len(pool), "shown_groups": len(listed),
            "hidden_groups": len(info["cards"]) - len(info["active"]), "picked": picked, "target": target,
            "progress": min(100, round(100 * picked / target)) if target else None,
            "review_link": self.address(f"group/{first}", **settings) + "#view-first" if first is not None else None,
            "bad_count": len(self.grouping.hidden(project)),
            # the species only once Animals (or one of them) is chosen: fewer chips to read
            "show_species": bool(subject) and subjects.category_of(subject) == "animals" or subject == "animals",
        }

    def neighbours(self, project, key, settings, info):
        """The groups before and after this one in the main page's list (same settings). A group
        that has just left the list (e.g. picked while showing "Not picked") keeps its place."""
        keys = [c["key"] for c, _ in info["listed"]]
        if key in keys:
            n = keys.index(key)
            return (keys[n - 1] if n else None), (keys[n + 1] if n + 1 < len(keys) else None), n + 1, len(keys)
        everything = [c["key"] for c, _ in self.listing(project, {**settings, "show": "all"})["listed"]]
        if key not in everything:
            return None, None, None, len(keys)
        n, wanted = everything.index(key), set(keys)
        after = next((k for k in everything[n + 1:] if k in wanted), None)
        before = next((k for k in reversed(everything[:n]) if k in wanted), None)
        return before, after, None, len(keys)

    def group_page(self, project, key, args):
        """One group opened: all its photos in the order they were taken (to choose by interest,
        not by quality), each with Pick and Hide, the subject menu, and the way to the groups
        before and after it in the list."""
        settings = self.settings(args)
        info = self.listing(project, settings)
        card = next((c for c in info["cards"] if c["key"] == key), None)
        if card is None:
            raise LookupError("This group has changed. Open it again from the list.")
        lib = project.library
        # Opened from a subject that only some of its photos show: those photos first, all on request
        only = settings["subject"] if settings["subject"] in card["minor"] and not args.get("all") else None
        ids = [i for i in card["all"] if card["labels"][i] == only] if only else card["all"]
        photos = []
        for i in ids:
            photo = self.grouping.describe(project, i, set())
            soft = lib.is_soft(i)
            other = card["labels"][i] != card["subject"]
            photos.append({**photo, "picked": i in card["picked"], "hidden": i in card["hidden"], "soft": soft,
                           "tag": subjects.label(card["labels"][i]) if other else "",
                           "caption": photo["caption"] + (" · looks soft" if soft else "")})
        known = subjects.species_names()
        corrections = set(project.step_state(self.id).get("subjects", {}).values())
        extra = sorted(s for s in corrections if subjects.category_of(s) == "animals"
                       and s not in known and s != subjects.OTHER_ANIMALS)
        taken = datetime.fromtimestamp(lib.taken[min(card["photos"])])
        before, after, position, count = self.neighbours(project, key, settings, info)
        main = self.address(**settings)
        return "steps/pick_photos_group.html", {
            "key": key, "photos": photos, "subject": card["subject"], "subject_label": subjects.label(card["subject"]),
            "corrected": card["corrected"], "recognised_label": subjects.label(card["recognised"]),
            "animal_options": [(s, subjects.label(s)) for s in sorted(known + extra, key=str.lower)]
                              + [(subjects.OTHER_ANIMALS, subjects.label(subjects.OTHER_ANIMALS))],
            "other_options": [(s, subjects.label(s)) for s in ("people", "views", "other")],
            "subtitle": f"{format_day(taken)} · {self.grouping.time_span(project, card['all'])}",
            "picked": len(card["picked"]), "hidden": len(card["hidden"]), "total": len(card["all"]),
            "only": subjects.label(only) if only else "", "all_link": self.address(f"group/{key}", **settings) +
            ("&" if "?" in self.address(f"group/{key}", **settings) else "?") + "all=1",
            "minor": [(subjects.label(s), len(v)) for s, v in card["minor"].items()],
            "main_link": main + f"#g-{key}", "main_page": main,
            "prev_link": self.address(f"group/{before}", **settings) if before is not None else None,
            "next_link": self.address(f"group/{after}", **settings) if after is not None else None,
            "position": position, "count": count,
        }

    # ---------- The forms on the pages ----------

    def form_action(self, project, name, form):
        lib, state = project.library, project.step_state(self.id)
        if name == "toggle_pick":
            try:
                i = int(form.get("photo", ""))
            except ValueError:
                raise ValueError("No such photo.") from None
            if not 0 <= i < len(lib):
                raise ValueError("No such photo.")
            on = lib.files[i] not in self.picked_files(project)
            self.action(project, "pick", {"photo": i, "on": on})
            target = state.get("target")
            if on and target and self.picked_count(project) == target:
                return f"That's {target} photos, your target."
            return ""
        if name == "hide":
            return self.hide_form(project, form)
        if name == "set_subject":
            typed = " ".join(form.get("custom", "").split()).lower()[:MAX_SUBJECT_LENGTH]
            subject = typed or form.get("subject", "")
            try:
                group = int(form.get("group", ""))
            except ValueError:
                raise ValueError("No such group.") from None
            self.action(project, "set_subject", {"group": group, "subject": subject or None})
            return f"Subject set to {subjects.label(subject)}" if subject else "Subject set back to the recognised one"
        if name == "set_target":
            value = form.get("target", "").strip()
            try:
                target = int(value) if value else None
            except ValueError:
                raise ValueError("The target must be a whole number.") from None
            if target is not None and target < 1:
                raise ValueError("The target must be at least 1.")
            self.action(project, "set_target", {"target": target})
            return ""
        return super().form_action(project, name, form)

    def hide_form(self, project, form):
        """Hide photos from this step, or show them again: a whole group (its card's Hide button),
        one photo (in an opened group; toggles) or a list of photos (Undo). Returns the message
        and the form fields that undo it."""
        lib = project.library
        on = {"1": True, "0": False}.get(form.get("hide", ""))
        try:
            if form.get("group"):
                key = int(form["group"])
                card = next((c for c in self.cards(project) if c["key"] == key), None)
                if card is None:
                    raise KeyError("This group has changed. Open it again from the list.")
                on = not card["dismissed"] if on is None else on
                ids = [i for i in card["photos"] if i not in card["hidden"]] if on else card["hidden"]
                if not ids:
                    return "This group is already hidden" if on else "Nothing is hidden in this group"
            else:
                ids = [int(i) for i in (form.get("photos") or form.get("photo", "")).split(",")]
        except ValueError:
            raise ValueError("No such photo.") from None
        if not ids or not all(0 <= i < len(lib) for i in ids):
            raise ValueError("No such photo.")
        if on is None:  # one photo: hide it, or show it again
            on = lib.files[ids[0]] not in self.hidden_files(project)
        picked = len({lib.files[i] for i in ids} & self.picked_files(project))
        self.action(project, "hide", {"photos": ids, "on": on})
        undo = {"action": "hide", "photos": ",".join(map(str, ids)), "hide": "0" if on else "1"}
        n = f"{len(ids)} photos" if len(ids) > 1 else "Photo"
        if not on:
            return f"{n} shown again", undo
        if form.get("photo") and any(c["dismissed"] and ids[0] in c["hidden"] and len(c["all"]) > 1
                                     for c in self.cards(project)):
            return "Photo hidden · that was the last one, so the whole group is hidden now", undo
        left = f" · {picked} picked photo{'s' if picked > 1 else ''} left the album" if picked else ""
        return f"{n} hidden{left}", undo
