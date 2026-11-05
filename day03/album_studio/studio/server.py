"""The local web server: serves the page and the small API the page talks to."""
import io
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file

from .analysis import load_image
from .project import Project, recent_folders, start_analysis
from .steps import STEPS, STEPS_BY_ID

STATIC = Path(__file__).resolve().parent.parent / "static"
app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
current = {"project": None, "job": None}  # one album project is open at a time


def project():
    if current["project"] is None:
        abort(409, "No folder is open")
    return current["project"]


def library():
    lib = project().library
    if lib is None:
        abort(409, "The photos are still being analysed")
    return lib


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/recent")
def recent():
    return jsonify(recent_folders())


@app.post("/api/pick-folder")
def pick_folder():
    """Show the Windows folder picker (the app runs on this computer, so it appears here)."""
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Choose the folder with your photos")
    root.destroy()
    return jsonify({"folder": folder or None})


@app.post("/api/open")
def open_folder():
    folder = Path(request.json["folder"].strip().strip('"'))
    if not folder.is_dir():
        return jsonify({"error": f"Folder not found: {folder}"}), 400
    current["project"] = Project(folder)
    current["job"] = start_analysis(current["project"])
    return project_info()


@app.get("/api/project")
def project_info():
    p = current["project"]
    if p is None:
        return jsonify(None)
    lib = p.library
    with_photos = lib is not None and request.args.get("photos") != "0"
    return jsonify({"folder": str(p.folder), "name": p.folder.name, "ready": lib is not None,
                    "photo_count": len(lib) if lib else 0,
                    "photos": [lib.photo_info(i) for i in range(len(lib))] if with_photos else [],
                    "steps": [step.info(p) for step in STEPS]})


@app.get("/api/steps")
def steps():
    """The list of steps, also shown before a folder is open."""
    return jsonify([{"id": s.id, "title": s.title, "tagline": s.tagline} for s in STEPS])


@app.get("/api/job")
def job():
    return jsonify(current["job"].info() if current["job"] else None)


@app.get("/api/thumb/<int:i>")
def thumb(i):
    return send_file(library().thumb_path(i))


@app.get("/api/photo/<int:i>")
def photo(i):
    """A large version of photo i for viewing (originals can be 20+ MB)."""
    img, _, _ = load_image(library().path(i), size=min(int(request.args.get("size", 1800)), 4000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


@app.get("/api/steps/<step_id>")
def step_get(step_id):
    library()
    return jsonify(STEPS_BY_ID[step_id].get(project()))


@app.post("/api/steps/<step_id>/<action>")
def step_action(step_id, action):
    library()
    try:
        return jsonify(STEPS_BY_ID[step_id].action(project(), action, request.json or {}))
    except KeyError as err:
        abort(404, str(err))
