"""Step 1: stack photos that look almost the same (bursts, retakes) into one group.

The first half is the business logic (grouping, hiding bad photos, fixing groups by hand);
the second half prepares the step's web pages and reads their forms."""
import logging
from datetime import datetime

import numpy as np

from .base import Step

log = logging.getLogger(__name__)  # debug lines: shown by the tests when a test fails

DEFAULT_SETTINGS = {"similarity": 0.90, "seconds": 120}  # seconds=None means "any time"
TIME_OPTIONS = [(30, "30 s"), (120, "2 min"), (600, "10 min"), (3600, "1 hour"), (None, "Any time")]
PROBLEM_LABELS = {"blurry": "Blurry", "blank": "Too dark or bright", "dark": "Too dark",
                  "unfocused": "Out of focus", "overexposed": "Overexposed"}
SHOW_OPTIONS = [("all", "All"), ("stacks", "Stacks"), ("singles", "Single photos")]
# Groups bigger than this mix different moments and animals: step 2 shows them as one card with
# one subject. The warning suggests at least STRICTER (88% within 2 minutes made the largest
# group 67 photos instead of 118 on the trip photos, 92% made it 52).
LARGE_GROUP = 30
STRICTER = {"similarity": 0.88, "seconds": 120}


def group_photos(embeddings, taken, similarity, max_gap):
    """Group photos that look alike. Photos must be sorted by the time they were taken.

    A photo joins the most similar group if it looks at least `similarity` (0-1) like the
    group's first photo and was taken at most max_gap seconds after the group's last photo.
    Comparing with the first photo, not the previous one, stops long chains of 'each looks a
    bit like the next' from merging a whole game drive into one group."""
    anchors = np.zeros_like(embeddings)
    last_time = np.zeros(len(embeddings))
    groups = []
    for i, emb in enumerate(embeddings):
        n = len(groups)
        if n:
            sims = anchors[:n] @ emb
            sims[taken[i] - last_time[:n] > max_gap] = -1
            best = int(np.argmax(sims))
            if sims[best] >= similarity:
                log.debug("photo %d joins group %d (starts with photo %d): %.3f alike (needs %s)",
                          i, best, groups[best][0], sims[best], similarity)
                groups[best].append(i)
                last_time[best] = taken[i]
                continue
            log.debug("photo %d starts group %d: the most alike group in time is only %.3f alike (needs %s)",
                      i, n, sims[best], similarity)
        anchors[n], last_time[n] = emb, taken[i]
        groups.append([i])
    log.debug("%d photos -> %d groups (similarity %s, max gap %s s)", len(embeddings), len(groups), similarity, max_gap)
    return groups


class GroupSimilarStep(Step):
    id = "group"
    title = "Group similar photos"
    tagline = "Bursts and retakes are stacked, so you choose between groups, not 2000 photos."
    description = ("Photos that look almost the same, like bursts and retakes, are stacked into one "
                   "group, so the next steps only have to choose between groups. Adjust the sliders "
                   "until the groups look right, then fix single photos by hand if needed.")
    template = "steps/group_similar.html"

    def summary(self, project):
        groups = project.step_state(self.id).get("groups")
        if not groups or not project.library:
            return ""
        hidden = {project.library.files[i] for i in self.hidden(project)}
        return f"{sum(any(f not in hidden for f in g) for g in groups)} groups"

    def groups(self, project):
        """The current groups as lists of photo ids; computed automatically the first time."""
        lib, state = project.library, project.step_state(self.id)
        if set(f for g in state.get("groups", []) for f in g) != set(lib.files):
            self.regroup(project, state.get("settings", DEFAULT_SETTINGS))  # first time, or photos changed
        ids = {f: i for i, f in enumerate(lib.files)}
        return [[ids[f] for f in g] for g in state["groups"]]

    def regroup(self, project, settings):
        lib, state = project.library, project.step_state(self.id)
        max_gap = np.inf if settings["seconds"] is None else settings["seconds"]
        groups = group_photos(lib.embedding, lib.taken, settings["similarity"], max_gap)
        state.update(settings=settings, edited=False)
        self.store(project, groups)

    def store(self, project, groups):
        """Save groups (lists of photo ids), sorted by time and without empty groups."""
        groups = sorted((sorted(g) for g in groups if g), key=lambda g: g[0])
        project.step_state(self.id)["groups"] = [[project.library.files[i] for i in g] for g in groups]
        project.save()

    def hidden(self, project):
        """Ids of photos hidden as blurry, out of focus, blank, too dark or overexposed (unless the user kept them),
        and photos the user hid by hand. Later steps use this to leave bad photos out of the album too."""
        lib, state = project.library, project.step_state(self.id)
        if not state.get("hide_problems", True):
            log.debug("hidden: none (the switch is off)")
            return set()
        keep, rejected = set(state.get("keep", [])), set(state.get("rejected", []))
        hidden = {i for i, f in enumerate(lib.files) if lib.problem(i) and f not in keep or f in rejected}
        log.debug("hidden: %s (kept by the user: %s, hidden by the user: %s)", sorted(hidden), sorted(keep), sorted(rejected))
        return hidden

    def get(self, project):
        lib, state = project.library, project.step_state(self.id)
        groups = self.groups(project)
        stacks = [g for g in groups if len(g) > 1]
        ids = {f: i for i, f in enumerate(lib.files)}
        return {
            "settings": state["settings"], "edited": state.get("edited", False),
            "hide_problems": state.get("hide_problems", True),
            "kept": [ids[f] for f in state.get("keep", []) if f in ids],
            "rejected": [ids[f] for f in state.get("rejected", []) if f in ids],
            "broken": lib.broken,
            "groups": [{"photos": g, "cover": max(g, key=lambda i: lib.quality[i])} for g in groups],
            "stats": {"photos": len(lib), "groups": len(groups), "stacks": len(stacks),
                      "singles": len(groups) - len(stacks), "stacked_away": len(lib) - len(groups)},
        }

    def action(self, project, name, payload):
        log.debug("step 1 action %r %s", name, payload)
        groups = self.groups(project) if project.library else []
        state = project.step_state(self.id)
        if name == "hide_problems":  # the "Hide blurry and bad photos" switch
            state["hide_problems"] = bool(payload["hide"])
            project.save()
            return self.get(project)
        if name in ("keep", "reject"):  # the user overrides the checks: a flagged photo is fine, or a photo is bad
            file = project.library.files[payload["photo"]]
            lists = {key: [f for f in state.get(key, []) if f != file] for key in ("keep", "rejected")}
            if payload["on"]:
                lists["keep" if name == "keep" else "rejected"].append(file)  # being in one list removes it from the other
            state.update(lists)
            project.save()
            return self.get(project)
        if name == "regroup":
            self.regroup(project, {"similarity": float(payload["similarity"]), "seconds": payload["seconds"]})
            return self.get(project)
        if name in ("split", "ungroup"):  # take photos out of their groups
            chosen = set(payload["photos"])
            groups = [[i for i in g if i not in chosen] for g in groups]
            groups += [sorted(chosen)] if name == "split" else [[i] for i in chosen]
        elif name == "merge":
            chosen = set(payload["groups"])
            merged = [i for k in chosen for i in groups[k]]
            groups = [g for k, g in enumerate(groups) if k not in chosen] + [merged]
        else:
            return super().action(project, name, payload)
        project.step_state(self.id)["edited"] = True
        self.store(project, groups)
        log.debug("groups after %r: %s", name, self.groups(project))
        return self.get(project)

    # ---------- The web pages ----------

    def page(self, project, view, args):
        if view is None:
            return self.main_page(project, args.get("show", "all"))
        if view == "review":
            return self.review_page(project)
        if view.startswith("stack/") and view[6:].isdigit():
            return self.stack_page(project, int(view[6:]))
        raise LookupError(f"Page not found: {view}")

    def user_lists(self, project):
        """Photo ids the user kept (fine after all) and rejected (hid by hand)."""
        state, ids = project.step_state(self.id), {f: i for i, f in enumerate(project.library.files)}
        return ({ids[f] for f in state.get("keep", []) if f in ids},
                {ids[f] for f in state.get("rejected", []) if f in ids})

    def describe(self, project, i, rejected):
        """What the pages show about photo i."""
        lib = project.library
        taken = datetime.fromtimestamp(lib.taken[i])
        megapixels = round(float(lib.pixels[i]) / 1e6, 1)
        flag = PROBLEM_LABELS.get(lib.problem(i)) or ("Hidden by you" if i in rejected else "")
        return {"id": i, "file": lib.files[i], "time": f"{taken:%H:%M}", "seconds": f"{taken:%H:%M:%S}",
                "megapixels": megapixels, "flag": flag, "problem": bool(lib.problem(i)), "rejected": i in rejected,
                "caption": f"{lib.files[i]} · {format_day(taken)} {taken:%H:%M:%S} · {megapixels} MP"
                           + (f" · {flag}" if flag else "")}

    def time_span(self, project, ids):
        first, last = (datetime.fromtimestamp(project.library.taken[i]) for i in (ids[0], ids[-1]))
        return f"{first:%H:%M}–{last:%H:%M}" if f"{first:%H:%M}" != f"{last:%H:%M}" else f"{first:%H:%M}"

    def main_page(self, project, show):
        """All groups by day, without hidden photos (and without groups that had only hidden photos)."""
        lib, state = project.library, project.step_state(self.id)
        groups, hidden = self.groups(project), self.hidden(project)
        kept, rejected = self.user_lists(project)
        shown = []
        for g in groups:
            ids = [i for i in g if i not in hidden]
            if ids:
                cover = max(ids, key=lambda i: lib.quality[i])
                shown.append({"key": g[0], "photos": ids, "cover": self.describe(project, cover, rejected),
                              "time_span": self.time_span(project, ids)})
        photo_count = sum(len(g["photos"]) for g in shown)
        stacks = sum(len(g["photos"]) > 1 for g in shown)
        if show not in dict(SHOW_OPTIONS):
            show = "all"
        listed = [g for g in shown if show == "all" or (show == "stacks") == (len(g["photos"]) > 1)]

        trip_days = sorted({datetime.fromtimestamp(t).date() for t in lib.taken})
        days = []
        for g in listed:
            day = datetime.fromtimestamp(lib.taken[g["photos"][0]]).date()
            if not days or days[-1]["date"] != day:
                days.append({"date": day, "title": f"Day {trip_days.index(day) + 1} · {format_day(day)}",
                             "groups": []})
            days[-1]["groups"].append(g)
        for day in days:
            day["photo_count"] = sum(len(g["photos"]) for g in day["groups"])

        bad = sum(1 for i in range(len(lib)) if lib.problem(i) and i not in kept or i in rejected)
        settings = state["settings"]
        large = sorted((len(g["photos"]) for g in shown if len(g["photos"]) > LARGE_GROUP), reverse=True)
        seconds = settings["seconds"]
        stricter = {"similarity": max(settings["similarity"], STRICTER["similarity"]),
                    "seconds": STRICTER["seconds"] if seconds is None or seconds > STRICTER["seconds"] else seconds}
        return self.template, {
            "settings": settings, "similarity_label": similarity_label(settings["similarity"]),
            "time_options": TIME_OPTIONS, "show_options": SHOW_OPTIONS, "show": show,
            "edited": state.get("edited", False), "hide_problems": state.get("hide_problems", True),
            "bad_count": bad + len(lib.broken), "days": days,
            "large": {"count": len(large), "largest": large[0] if large else 0,
                      "photos": sum(large), "share": round(100 * sum(large) / max(photo_count, 1)),
                      "limit": LARGE_GROUP, "stricter": stricter,
                      "stricter_label": f"{round(stricter['similarity'] * 100)}% within "
                                        + dict(TIME_OPTIONS)[stricter["seconds"]],
                      "can_be_stricter": stricter != settings} if large else None,
            "stats": {"photos": photo_count, "hidden": len(lib) - photo_count, "groups": len(shown),
                      "stacks": stacks, "singles": len(shown) - stacks, "tucked_away": photo_count - len(shown)},
        }

    def stack_page(self, project, key):
        """One group opened: all its photos, best first. Photos the user hid stay visible (dimmed)
        here so that hiding can be undone right away."""
        lib = project.library
        group = next((g for g in self.groups(project) if g[0] == key), None)
        if group is None:
            raise LookupError("This group has changed. Open it again from the list.")
        hidden, (kept, rejected) = self.hidden(project), self.user_lists(project)
        ids = sorted((i for i in group if i not in hidden or i in rejected), key=lambda i: -lib.quality[i])
        taken = datetime.fromtimestamp(lib.taken[group[0]])
        return "steps/group_similar_stack.html", {
            "key": key, "photos": [self.describe(project, i, rejected) for i in ids],
            "subtitle": f"{format_day(taken)} · {self.time_span(project, group)}",
            "hidden_here": len(group) - len(ids)}

    def review_page(self, project):
        """All photos flagged as bad (by the checks or by the user), to keep any that are fine."""
        lib = project.library
        kept, rejected = self.user_lists(project)
        ids = [i for i in range(len(lib)) if lib.problem(i) or i in rejected]
        photos = [self.describe(project, i, rejected) for i in ids]
        for p in photos:
            p["kept"] = p["id"] in kept
        return "steps/group_similar_review.html", {"photos": photos, "broken": lib.broken}

    # ---------- The forms on the pages ----------

    def form_action(self, project, name, form):
        lib, state = project.library, project.step_state(self.id)
        if name == "regroup":
            seconds = form.get("seconds", "any")
            try:
                settings = {"similarity": float(form["similarity"]),
                            "seconds": None if seconds == "any" else float(seconds)}
            except ValueError:
                raise ValueError("The grouping settings must be numbers.") from None
            self.action(project, "regroup", settings)
            return ""
        if name == "undo_edits":
            self.action(project, "regroup", state["settings"])
            return "Your changes by hand were undone"
        if name == "hide_problems":  # the switch sends hide=0, and hide=1 when it is on
            hide = "1" in form.getlist("hide")
            self.action(project, "hide_problems", {"hide": hide})
            return "Blurry and bad photos are hidden" if hide else "All photos are shown"
        if name in ("toggle_reject", "toggle_keep"):
            i = int(form["photo"])
            key = "rejected" if name == "toggle_reject" else "keep"
            on = lib.files[i] not in state.get(key, [])
            self.action(project, "reject" if name == "toggle_reject" else "keep", {"photo": i, "on": on})
            if name == "toggle_keep":
                return "The photo is kept and shown" if on else "The photo is hidden again"
            if not on:
                return "The photo is shown again"
            return ("Photo hidden · undo it in “review”" if state.get("hide_problems", True)
                    else "Photo marked as bad · hidden while the switch is on")
        if name == "merge":
            index = {g[0]: k for k, g in enumerate(self.groups(project))}
            chosen = [index[int(key)] for key in form.getlist("group") if int(key) in index]
            if len(chosen) < 2:
                raise ValueError("Tick two or more groups to merge them.")
            self.action(project, "merge", {"groups": chosen})
            return f"Merged {len(chosen)} groups into one"
        if name in ("split", "ungroup"):
            ticked = [int(i) for i in form.getlist("ticked")]
            group = next((g for g in self.groups(project) if ticked and ticked[0] in g), [])
            if not ticked or len(ticked) >= len(group):
                raise ValueError("Tick some of the photos, but not all of them.")
            self.action(project, name, {"photos": ticked})
            n = f"{len(ticked)} photos" if len(ticked) > 1 else "1 photo"
            return (f"Moved {n} to a new group" if name == "split"
                    else f"{n} {'are' if len(ticked) > 1 else 'is'} now single")
        return super().form_action(project, name, form)


def format_day(day):
    return f"{day:%a} {day.day} {day:%b %Y}"  # e.g. "Thu 17 Apr 2025"


def similarity_label(value):
    return f"{round(value * 100)}% · " + ("loose" if value < 0.86 else "balanced" if value <= 0.93 else "strict")
