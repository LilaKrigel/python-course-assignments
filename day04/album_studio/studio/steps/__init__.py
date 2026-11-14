"""The steps of making an album, in the order they appear in the sidebar."""
from .export import ExportStep
from .group_similar import GroupSimilarStep
from .pick_photos import PickPhotosStep

grouping = GroupSimilarStep()
picking = PickPhotosStep(grouping)
STEPS = [grouping, picking, ExportStep(picking)]
STEPS_BY_ID = {step.id: step for step in STEPS}
