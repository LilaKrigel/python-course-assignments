"""An album project: one photo folder, its analysis and the choices made in each step.

The choices are saved in <photo folder>/.album_studio/project.json after every change,
so closing the app never loses work. Saving is safe: the new version is written to a temporary
file first and then replaces the old one, which is kept as project.json.bak.
"""
import json
import os
import shutil
import threading
import time
from pathlib import Path

from .analysis import STUDIO_DIR, analyse

RECENT_FILE = Path(__file__).resolve().parent.parent / "recent_folders.json"
SAVE_LOCK = threading.Lock()


class Project:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.state_file = self.folder / STUDIO_DIR / "project.json"
        self.state = self.load_state()
        self.library = None  # set when the analysis job finishes
        remember_recent(self.folder)

    def step_state(self, step_id):
        """The saved data of one step (a dict the step may change, then call save())."""
        return self.state["steps"].setdefault(step_id, {})

    def load_state(self):
        """The saved choices; if the file is damaged, the previous version (project.json.bak)."""
        for path in (self.state_file, self.backup_file):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return {"steps": {}}

    @property
    def backup_file(self):
        return self.state_file.with_name(self.state_file.name + ".bak")

    def save(self):
        """Write the choices without ever leaving a half-written file: a crash during saving
        keeps either the old or the new version."""
        with SAVE_LOCK:  # the web server handles requests in parallel threads
            self.state_file.parent.mkdir(exist_ok=True)
            temp = self.state_file.with_name(self.state_file.name + ".tmp")
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=1)
                f.flush()
                os.fsync(f.fileno())  # really on the disk before it replaces the old file
            if self.state_file.exists():
                shutil.copy2(self.state_file, self.backup_file)
            os.replace(temp, self.state_file)  # atomic: the file is the old or the new version


class Job:
    """A long task (e.g. analysing photos) running in the background with a progress bar."""

    def __init__(self, title, work, detail=""):
        self.title, self.detail, self.done, self.total, self.message = title, detail, 0, 0, "Starting..."
        self.eta, self.error, self.finished = None, None, False
        self.thread = threading.Thread(target=self._run, args=(work,), daemon=True)
        self.thread.start()

    def progress(self, done, total, message, started=None):
        self.done, self.total, self.message = done, total, message
        if started and done:
            self.eta = (time.time() - started) / done * (total - done)

    def _run(self, work):
        try:
            work(self.progress)
        except Exception as err:
            self.error = f"{type(err).__name__}: {err}"
        self.finished = True

    def info(self):
        return {"title": self.title, "detail": self.detail, "done": self.done, "total": self.total, "message": self.message,
                "eta": self.eta, "error": self.error, "finished": self.finished}


def start_analysis(project):
    def work(progress):
        project.library = analyse(project.folder, progress)
    return Job("Getting to know your photos", work,
               "Every photo is read once to measure its sharpness and understand what it shows. "
               "Next time, this folder opens instantly.")


def recent_folders():
    if RECENT_FILE.exists():
        return [f for f in json.loads(RECENT_FILE.read_text(encoding="utf-8")) if Path(f).is_dir()]
    return []


def remember_recent(folder):
    folders = [str(folder)] + [f for f in recent_folders() if f != str(folder)]
    RECENT_FILE.write_text(json.dumps(folders[:8], indent=1), encoding="utf-8")
