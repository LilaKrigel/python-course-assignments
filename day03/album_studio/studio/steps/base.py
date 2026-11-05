"""The base class of an album step.

To add a new step:
  1. Write a subclass of Step in a new file in this folder (group_similar.py is an example).
  2. Add it to STEPS in steps/__init__.py, at the position it should appear in the sidebar.
  3. Write static/steps/<ui>.js with a render() function that draws the step (see
     static/steps/group_similar.js). It talks to the step through get() and action().
"""


class Step:
    id = ""           # short name, used in URLs and in project.json
    title = ""
    tagline = ""      # one short line for the overview on the welcome screen
    description = ""  # one or two sentences shown at the top of the step
    ui = "planned"    # static/steps/<ui>.js draws this step

    def summary(self, project):
        """A short status shown under the title in the sidebar, e.g. '601 groups'."""
        return ""

    def is_done(self, project):
        return project.step_state(self.id).get("done", False)

    def get(self, project):
        """Everything the step's page needs, as JSON-friendly data."""
        return {}

    def action(self, project, name, payload):
        """Handle a button press from the step's page and return the updated get() data."""
        if name == "complete":
            project.step_state(self.id)["done"] = True
            project.save()
            return self.get(project)
        raise KeyError(f"Step '{self.id}' has no action '{name}'")

    def info(self, project):
        return {"id": self.id, "title": self.title, "description": self.description, "ui": self.ui,
                "summary": self.summary(project), "done": self.is_done(project)}


class PlannedStep(Step):
    """A step that is designed but not built yet: shows its description and 'coming soon'."""

    def __init__(self, id, title, tagline, description):
        self.id, self.title, self.tagline, self.description = id, title, tagline, description
