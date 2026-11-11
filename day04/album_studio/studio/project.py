"""An album project: one photo folder, its analysis and the choices made in each step.

The choices are saved in <photo folder>/.album_studio/project.json after every change,
so closing the app never loses work.
"""
import json
import threading
import time
from pathlib import Path

from .analysis import STUDIO_DIR, analyse

RECENT_FILE = Path(__file__).resolve().parent.parent / "recent_folders.json"


class Project:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.state_file = self.folder / STUDIO_DIR / "project.json"
        self.state = {"steps": {}}
        if self.state_file.exists():
            self.state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.library = None  # set when the analysis job finishes
        remember_recent(self.folder)

    def step_state(self, step_id):
        """The saved data of one step (a dict the step may change, then call save())."""
        return self.state["steps"].setdefault(step_id, {})

    def save(self):
        self.state_file.parent.mkdir(exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=1), encoding="utf-8")


class Job:
    """A long task (e.g. analysing photos) running in the background with a progress bar."""

    def __init__(self, title, work):
        self.title, self.done, self.total, self.message = title, 0, 0, "Starting..."
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
        return {"title": self.title, "done": self.done, "total": self.total, "message": self.message,
                "eta": self.eta, "error": self.error, "finished": self.finished}


def start_analysis(project):
    def work(progress):
        project.library = analyse(project.folder, progress)
    return Job("Analysing photos", work)


def recent_folders():
    if RECENT_FILE.exists():
        return [f for f in json.loads(RECENT_FILE.read_text(encoding="utf-8")) if Path(f).is_dir()]
    return []


def remember_recent(folder):
    folders = [str(folder)] + [f for f in recent_folders() if f != str(folder)]
    RECENT_FILE.write_text(json.dumps(folders[:8], indent=1), encoding="utf-8")
