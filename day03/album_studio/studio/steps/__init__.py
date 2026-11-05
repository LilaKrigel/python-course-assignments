"""The steps of making an album, in the order they appear in the sidebar."""
from .base import PlannedStep
from .group_similar import GroupSimilarStep

STEPS = [
    GroupSimilarStep(),
    PlannedStep("best", "Pick the best photo",
                "The sharpest photo of each group is chosen; swap it with one click.",
                "From every group, the sharpest, best-exposed photo is chosen automatically. "
                "You can swap it for another photo of the group with one click."),
    PlannedStep("content", "Recognise what's in the photos",
                "Animals and their species, people and views are labelled.",
                "Each photo is labelled as animals (with the species), people or views. "
                "Wrong labels can be corrected, and you can add your own labels."),
    PlannedStep("select", "Choose the album photos",
                "Say how many photos and what to focus on; get a proposal.",
                "Say how many photos the album should have and what to focus on, e.g. every "
                "species plus photos of us. The best matching photos are proposed; add or remove any."),
    PlannedStep("export", "Arrange and export",
                "Order, caption and save the album as a folder of copies.",
                "Put the photos in order (by date or by hand), add captions, and save the album "
                "as a folder of copies, ready to print or share."),
]
STEPS_BY_ID = {step.id: step for step in STEPS}
