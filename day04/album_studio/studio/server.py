"""The web app: Flask routes that turn page requests and form posts into calls to the
business logic (project.py, analysis.py and the steps), and render the pages from templates/.

Every button on a page is an HTML form. It posts here, the step changes its results, and the
browser is sent back to the page (post/redirect/get), which shows the new state and a short message.
"""
import io
import os
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from .analysis import load_image
from .project import Project, recent_folders, start_analysis
from .steps import STEPS, STEPS_BY_ID

ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=str(ROOT / "static"), template_folder=str(ROOT / "templates"))
app.secret_key = os.urandom(16)  # needed for flash() messages
current = {"project": None, "job": None}  # one album project is open at a time


def not_ready():
    """Where to go instead when the photos are not ready yet, or None when they are."""
    if current["project"] is None:
        return redirect(url_for("index"))
    if current["project"].library is None:
        return redirect(url_for("progress"))
    return None


def get_step(step_id):
    if step_id not in STEPS_BY_ID:
        abort(404, "No such step")
    return STEPS_BY_ID[step_id]


def safe_back(url, default):
    """Only go back to a page of this app (a path such as /step/group?show=stacks)."""
    return url if url and url.startswith("/") and not url.startswith("//") else default


# ---------- Opening a folder ----------

@app.get("/")
def index():
    if current["project"] is not None:
        return not_ready() or redirect(url_for("step_page", step_id=STEPS[0].id))
    return render_template("welcome.html", recent=recent_folders(), steps=STEPS)


@app.post("/open")
def open_folder():
    folder = Path(request.form.get("folder", "").strip().strip('"'))
    if not str(folder) or str(folder) == "." or not folder.is_dir():
        flash(f"Folder not found: {folder}", "error")
        return redirect(url_for("index"))
    current["project"] = Project(folder)
    current["job"] = start_analysis(current["project"])
    return redirect(url_for("progress"))


@app.post("/pick-folder")
def pick_folder():
    """Show the Windows folder picker (the app runs on this computer, so it appears here)."""
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Choose the folder with your photos")
    root.destroy()
    if not folder:
        return redirect(url_for("index"))
    current["project"] = Project(folder)
    current["job"] = start_analysis(current["project"])
    return redirect(url_for("progress"))


@app.post("/close")
def close_folder():
    current["project"] = current["job"] = None
    return redirect(url_for("index"))


@app.get("/progress")
def progress():
    """Shown while the photos are analysed; the page reloads itself every second."""
    project, job = current["project"], current["job"]
    if project is None or job is None:
        return redirect(url_for("index"))
    next_page = getattr(job, "next_page", None)  # set for a step's job; None while opening a folder
    if job.finished:
        if job.error:
            flash(f"{job.title} failed: {job.error}", "error")
            if next_page is None:  # the folder could not be analysed
                current["project"] = None
                return redirect(url_for("index"))
            return redirect(url_for("step_page", step_id=STEPS[0].id))
        return redirect(next_page or url_for("index"))
    return render_template("progress.html", job=job.info(), project=project)


@app.template_filter("duration")
def duration(seconds):
    return f"{max(5, round(seconds / 5) * 5)} seconds" if seconds < 90 else f"{round(seconds / 60)} minutes"


@app.after_request
def no_stale_pages(response):
    """Pages show the current state, so the browser must not keep old copies (e.g. for its Back
    button). Thumbnails and photos set their own caching."""
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------- The steps ----------

def render_step(step, template, data):
    project = current["project"]
    index = STEPS.index(step)
    return render_template(template, project=project, steps=[s.info(project) for s in STEPS], step=step,
                           number=index + 1, next_step=STEPS[index + 1] if index + 1 < len(STEPS) else None,
                           photo_count=len(project.library), here=request.full_path.rstrip("?"), **data)


@app.get("/step/<step_id>")
@app.get("/step/<step_id>/<path:view>")
def step_page(step_id, view=None):
    if (other := not_ready()) is not None:
        return other
    step = get_step(step_id)
    job = step.prepare(current["project"])
    if job is not None:  # e.g. step 2 embeds its text descriptions the first time
        job.next_page = request.full_path.rstrip("?")
        current["job"] = job
        return redirect(url_for("progress"))
    try:
        template, data = step.page(current["project"], view, request.args)
    except LookupError as err:
        flash(str(err.args[0]) if err.args else "Page not found", "error")
        return redirect(url_for("step_page", step_id=step.id))
    return render_step(step, template, data)


@app.post("/step/<step_id>/do/<action>")
def step_action(step_id, action):
    """A button press on a step's page. request.values has the form fields and the URL's ?query."""
    if (other := not_ready()) is not None:
        return other
    step, project = get_step(step_id), current["project"]
    back = safe_back(request.args.get("back") or request.form.get("back"), url_for("step_page", step_id=step.id))
    if action == "complete":
        step.action(project, "complete", {})
        following = STEPS[STEPS.index(step) + 1:]
        return redirect(url_for("step_page", step_id=following[0].id) if following else back)
    try:
        message = step.form_action(project, action, request.values)
    except (ValueError, KeyError) as err:
        flash(str(err.args[0]) if err.args else "That didn't work.", "error")
        return redirect(back)
    if isinstance(message, tuple):  # (message, the form fields that undo it): the message gets an Undo button
        message, undo = message
        undo = dict(undo)
        flash({"text": message, "fields": undo,
               "action": url_for("step_action", step_id=step.id, action=undo.pop("action"))}, "undo")
    elif message:
        flash(message, "ok")
    return redirect(back)


# ---------- Photos ----------

@app.get("/thumb/<int:i>")
def thumb(i):
    if not_ready() or not 0 <= i < len(current["project"].library):
        abort(404)
    # thumbnails never change (their file name comes from the photo's size and date), so the
    # browser may keep them: pages that reload after every button press stay fast
    return send_file(current["project"].library.thumb_path(i), max_age=30 * 24 * 3600)


@app.get("/photo/<int:i>")
def photo(i):
    """A large version of photo i for viewing (originals can be 20+ MB)."""
    if not_ready() or not 0 <= i < len(current["project"].library):
        abort(404)
    size = min(request.args.get("size", 1800, type=int), 4000)
    img, _, _ = load_image(current["project"].library.path(i), size=size)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg", max_age=3600)
