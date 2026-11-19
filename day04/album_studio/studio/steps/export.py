"""Step 3: arrange the picked photos and save the album.

The album is the photos picked in step 2 (without photos hidden since), in trip order or by
subject. Saving copies the original photos, numbered in album order, into a folder next to the
photos ("album_export": folders starting with "album_" are not read as photos), with album.html,
a page that shows them all and prints well (or saves as PDF from the browser's print dialog).
Only files written by an earlier export are replaced; the originals are never changed.

The first half is the business logic; the second half prepares the web pages and reads their forms.
"""
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from .. import subjects
from ..project import Job
from .base import Step
from .group_similar import format_day

log = logging.getLogger(__name__)  # debug lines: shown by the tests when a test fails

FOLDER_NAME = "album_export"
PAGE_NAME = "album.html"
ORDER_OPTIONS = [("time", "Trip order"), ("subject", "By subject")]


class ExportStep(Step):
    id = "export"
    title = "Arrange and export"
    tagline = "Put the picked photos in order and save them as a folder of copies, with a page to print."
    description = "Your album, in order. Save it as a folder of copies, with a page to print or save as PDF."
    template = "steps/export.html"

    def __init__(self, picking):
        self.picking = picking  # step 2: the picked photos and their subjects
        self.job = None

    # ---------- Business logic ----------

    def folder(self, project):
        return project.folder / FOLDER_NAME

    def album(self, project):
        """The album in its order: sections (a day, or a subject), each with its photos
        ({id, number, subject}). Photos hidden in step 1 or 2 since they were picked are left out."""
        lib, state = project.library, project.step_state(self.id)
        photos = [(i, c["labels"][i]) for c in self.picking.cards(project) if not c["dismissed"] for i in c["picked"]]
        photos.sort(key=lambda p: lib.taken[p[0]])
        sections = []
        if state.get("order", "time") == "subject":
            # subjects in the order they were first met on the trip; photos by time within each
            first = {}
            for i, s in photos:
                first.setdefault(s, len(first))
            photos.sort(key=lambda p: first[p[1]])
            for i, s in photos:
                if not sections or sections[-1]["key"] != s:
                    sections.append({"key": s, "title": subjects.label(s), "photos": []})
                sections[-1]["photos"].append({"id": i, "subject": s})
        else:
            trip_days = sorted({datetime.fromtimestamp(t).date() for t in lib.taken})
            for i, s in photos:
                day = datetime.fromtimestamp(lib.taken[i]).date()
                if not sections or sections[-1]["key"] != day:
                    sections.append({"key": day, "title": f"Day {trip_days.index(day) + 1} · {format_day(day)}",
                                     "photos": []})
                sections[-1]["photos"].append({"id": i, "subject": s})
        number = 0
        for section in sections:
            for photo in section["photos"]:
                number += 1
                photo["number"] = number
        if log.isEnabledFor(logging.DEBUG):
            log.debug("album (%s order): %s", state.get("order", "time"),
                      [(s["title"], [(p["number"], p["id"]) for p in s["photos"]]) for s in sections])
        return sections

    def file_name(self, project, photo):
        """The copy's name: its number in the album, then the original name (e.g. "007 _MG_1172.JPG")."""
        return f"{photo['number']:03d} {Path(project.library.files[photo['id']]).name}"

    def summary(self, project):
        if not project.library:
            return ""
        exported = project.step_state(self.id).get("exported")
        return f"saved {exported['count']} photos" if exported else ""

    def get(self, project):
        state = project.step_state(self.id)
        return {"order": state.get("order", "time"), "exported": state.get("exported"),
                "album": [{"title": s["title"], "photos": [int(p["id"]) for p in s["photos"]]}
                          for s in self.album(project)]}

    def action(self, project, name, payload):
        state = project.step_state(self.id)
        if name == "set_order":  # payload: order ("time" or "subject")
            state["order"] = payload["order"]
        elif name == "export":  # payload: page (the HTML of album.html); runs in the background
            self.export(project, payload["page"])
            return self.get(project)
        else:
            return super().action(project, name, payload)
        project.save()
        return self.get(project)

    def export(self, project, page_html):
        """Copy the album's photos into the album folder (replacing an earlier export) as a
        background job, and write the album page."""
        if self.job and not self.job.finished:
            raise ValueError("The album is being saved already.")
        lib, state = project.library, project.step_state(self.id)
        photos = [p for s in self.album(project) for p in s["photos"]]
        if not photos:
            raise ValueError("Pick some photos first (step 2).")
        target = self.folder(project)
        earlier = state.get("files", [])

        def work(progress):
            target.mkdir(exist_ok=True)
            log.debug("export to %s: removing the earlier export %s", target, earlier)
            for name in earlier:  # only what an earlier export wrote; anything else stays
                (target / name).unlink(missing_ok=True)
            written, started = [], time.time()
            for n, photo in enumerate(photos, 1):
                name = self.file_name(project, photo)
                shutil.copy2(lib.path(photo["id"]), target / name)  # the original, untouched
                log.debug("copied %s -> %s", lib.files[photo["id"]], name)
                written.append(name)
                progress(n, len(photos), f"Copying photos ({n} of {len(photos)})", started)
            (target / PAGE_NAME).write_text(page_html, encoding="utf-8")
            state["files"] = written + [PAGE_NAME]
            state["exported"] = {"count": len(photos), "when": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                 "folder": str(target)}
            project.save()

        self.job = Job("Saving the album", work)

    # ---------- The web pages ----------

    def page(self, project, view, args):
        if view is None:
            return self.main_page(project)
        if view == "sheet":
            return self.sheet(project, for_export=False)
        raise LookupError(f"Page not found: {view}")

    def sheet(self, project, for_export):
        """The album page: every photo with its number and caption, by section. Exported, it
        shows the copies next to it; in the app, the photos from the server."""
        from flask import url_for
        lib = project.library
        sections = []
        for section in self.album(project):
            photos = []
            for p in section["photos"]:
                taken = datetime.fromtimestamp(lib.taken[p["id"]])
                photos.append({**p, "src": self.file_name(project, p) if for_export
                               else url_for("photo", i=p["id"], size=1200),
                               "caption": f"{subjects.label(p['subject'])} · {format_day(taken)} {taken:%H:%M}"})
            sections.append({"title": section["title"], "photos": photos})
        count = sum(len(s["photos"]) for s in sections)
        return "export_sheet.html", {"sections": sections, "count": count, "trip": project.folder.name,
                                     "for_export": for_export}

    def main_page(self, project):
        lib, state = project.library, project.step_state(self.id)
        sections = self.album(project)
        for section in sections:
            for p in section["photos"]:
                taken = datetime.fromtimestamp(lib.taken[p["id"]])
                soft = lib.is_soft(p["id"])
                p["caption"] = (f"{p['number']} · {subjects.label(p['subject'])} · {lib.files[p['id']]} · "
                                f"{format_day(taken)} {taken:%H:%M}" + (" · looks soft" if soft else ""))
                p["soft"] = soft
                p["label"] = subjects.label(p["subject"])
                p["category"] = subjects.category_of(p["subject"])
        job = self.job.info() if self.job else None
        return self.template, {
            "sections": sections, "count": sum(len(s["photos"]) for s in sections),
            "order": state.get("order", "time"), "order_options": ORDER_OPTIONS,
            "exported": state.get("exported"), "folder": str(self.folder(project)),
            "job": job, "saving": bool(job and not job["finished"]),
            "can_open_folder": hasattr(os, "startfile"),
        }

    # ---------- The forms on the pages ----------

    def form_action(self, project, name, form):
        if name == "set_order":
            order = form.get("order", "")
            if order not in dict(ORDER_OPTIONS):
                raise ValueError("Unknown order.")
            self.action(project, "set_order", {"order": order})
            return ""
        if name == "export":
            from flask import render_template
            template, data = self.sheet(project, for_export=True)
            self.action(project, "export", {"page": render_template(template, **data)})
            return ""
        if name == "open_folder":  # this app runs on the user's own computer
            folder = self.folder(project)
            if not folder.exists():
                raise ValueError("Save the album first.")
            if not hasattr(os, "startfile"):
                return f"The album is in {folder}"
            os.startfile(folder)  # opens it in Explorer
            return ""
        return super().form_action(project, name, form)
