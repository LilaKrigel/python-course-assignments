"""The base class of an album step.

To add a new step:
  1. Write a subclass of Step in a new file in this folder (group_similar.py is an example).
  2. Add it to STEPS in steps/__init__.py, at the position it should appear in the sidebar.
  3. Write templates/steps/<name>.html, the step's page (see steps/group_similar.html).
     page() gives it its data; its forms post to /step/<id>/do/<action>, which calls form_action().
"""


class Step:
    id = ""           # short name, used in URLs and in project.json
    title = ""
    tagline = ""      # one short line for the overview on the welcome screen
    description = ""  # one or two sentences shown at the top of the step
    template = "steps/planned.html"  # the step's page, in templates/
    planned = False   # designed but not built yet

    def summary(self, project):
        """A short status shown under the title in the sidebar, e.g. '601 groups'."""
        return ""

    def is_done(self, project):
        return project.step_state(self.id).get("done", False)

    # ---------- The business logic: what the step knows and can do ----------

    def get(self, project):
        """The step's current results, as JSON-friendly data."""
        return {}

    def action(self, project, name, payload):
        """Change the step's results (payload is a dict of plain values) and return the new get() data."""
        if name == "complete":
            project.step_state(self.id)["done"] = True
            project.save()
            return self.get(project)
        raise KeyError(f"Step '{self.id}' has no action '{name}'")

    # ---------- The web pages ----------

    def page(self, project, view, args):
        """The template and its data for one page of the step. `view` is the rest of the URL after
        /step/<id>/ (None for the step's main page); `args` are the URL's ?query values.
        Raise LookupError if there is no such page (e.g. a group that no longer exists)."""
        if view:
            raise LookupError(f"Page not found: {view}")
        return self.template, {}

    def form_action(self, project, name, form):
        """Handle a form sent from the step's pages: read the form, call action(), and return a
        short message for the user ('' for none). Raise ValueError for a form that can't be used;
        its text is shown to the user."""
        self.action(project, name, {})
        return ""

    def info(self, project):
        return {"id": self.id, "title": self.title, "description": self.description, "planned": self.planned,
                "summary": self.summary(project), "done": self.is_done(project)}


class PlannedStep(Step):
    """A step that is designed but not built yet: shows its description and 'coming soon'."""
    planned = True

    def __init__(self, id, title, tagline, description):
        self.id, self.title, self.tagline, self.description = id, title, tagline, description
