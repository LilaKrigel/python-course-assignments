"""Step 1: stack photos that look almost the same (bursts, retakes) into one group."""
import numpy as np

from .base import Step

DEFAULT_SETTINGS = {"similarity": 0.90, "seconds": 120}  # seconds=None means "any time"


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
                groups[best].append(i)
                last_time[best] = taken[i]
                continue
        anchors[n], last_time[n] = emb, taken[i]
        groups.append([i])
    return groups


class GroupSimilarStep(Step):
    id = "group"
    title = "Group similar photos"
    tagline = "Bursts and retakes are stacked, so you choose between groups, not 2000 photos."
    description = ("Photos that look almost the same, like bursts and retakes, are stacked into one "
                   "group, so the next steps only have to choose between groups. Adjust the sliders "
                   "until the groups look right, then fix single photos by hand if needed.")
    ui = "group_similar"

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
            return set()
        keep, rejected = set(state.get("keep", [])), set(state.get("rejected", []))
        return {i for i, f in enumerate(lib.files) if lib.problem(i) and f not in keep or f in rejected}

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
        return self.get(project)
