# Day 03 Assignment: Photo Album Builder

## The problem

I have about 2,000 photos from a trip to Tanzania. Many of them are
near-duplicates: bursts of the same lion, where one frame is sharper than the others. I want a program that builds an album from them: it should keep only the best photo of each set of near-duplicates and let me choose how many photos I want and what to focus on. For this trip that means every animal species we saw plus photos of us; another time it might be views.

## What I did

I built it with Claude Code (an AI coding assistant) in two rounds.

### Round 1: a command-line program ([album_picker/](album_picker/))

`album_picker.py` takes a folder, a number of photos and a focus, and copies the chosen photos
into a new subfolder with a CSV report explaining every choice:

```
python album_picker.py "C:\...\101CANON" -n 60 --focus animals people
```

How it works:
- **Quality:** sharpness (variance of the Laplacian, measured on the sharpest parts of the
  photo so that an animal against a blurred background still counts as sharp), resolution, and
  blown-out highlights or shadows.
- **Near-duplicates:** each photo gets a CLIP embedding (CLIP is an image/text AI model that
  runs locally). Photos that look very alike and were taken within 2 minutes of each other form
  one group, and only the best photo of the group is kept.
- **Content:** CLIP compares each photo with text such as "a photo of a wild animal" or "a
  selfie", and with a list of African species ("a photo of a giraffe", ...).
- **Selection:** the best photo of every species first, then the best remaining photos, with a
  penalty for photos that look like ones already chosen.

The first version looked fine on a small test set but failed on the real 2,046 photos. I fixed
it step by step after looking at the results:

| Problem found on the real photos | Fix |
|---|---|
| 897 different photos were merged into one "duplicate" group (A looks like B, B like C, ...) | Duplicates must be taken within 2 minutes, and each photo is compared with the first photo of its group |
| About half the species labels were wrong (lions labelled as impala, warthog, wild dog...) | A larger CLIP model (ViT-L-14); the species is decided by the whole burst; animals we actually saw (guineafowl, starling, owl) added to the list; "some bird / some animal" fallbacks |
| About 20 of 60 photos were lions (we took 599 lion photos) | Each additional photo of the same species gets a penalty |
| The same scene appeared twice when shot hours apart | Photos too similar to an already chosen one are skipped |
| Hidden `._` macOS files were reported as unreadable photos | Skipped |

The result was a 60-photo album covering 29 species, with at most 5 photos of any one species.

I first ran it from WSL, where it failed with `No module named 'numpy'`: WSL has its own Python
without the packages. The fix was to run the Windows Python (`python.exe`) or use a PowerShell
terminal.

### Round 2: Album Studio, an app with a graphical interface ([album_studio/](album_studio/))

I then started over to build the project step by step, with a comfortable user interface and room to add more album-editing steps later.

**Design.** Album Studio runs on my own computer and opens in the browser (Python and Flask on
the back end, plain HTML/CSS/JavaScript on the front end). The album is made in 5 steps shown in
a sidebar:

1. **Group similar photos** (built)
2. Pick the best photo of each group (planned)
3. Recognise what's in the photos: animals and species, people, views (planned)
4. Choose the album photos (planned)
5. Arrange and export (planned)

Each step is one Python class plus one JavaScript file, registered in one list
(`studio/steps/__init__.py`), so new steps can be added without changing the rest. The photo
analysis (quality, CLIP embedding, thumbnail) is done once per folder and cached, so after the
first time a folder opens in under a second.

**Step 1: Group similar photos.**
- Two settings regroup the photos as soon as you change them: "How similar must photos be?" and
  "Taken within" (30 s to any time).
- The groups are shown by trip day as stacked cards with a photo count. With the default settings,
  2,046 photos become 474 groups.
- Opening a group shows all its photos, with the sharpest one marked. Photos that don't belong
  can be moved to a new group or made single, and several groups can be merged.
- Any photo can be viewed full screen (← → to browse, Esc to close).
- Changes are saved automatically. Light and dark mode both work, and the layout fits a narrow
  window.

**Step 1, added afterwards:**
- Inside each group the photos are sorted best first (sharpness, then resolution).
- A *Hide blurry and bad photos* switch (on by default) hides bad photos everywhere in the step.
  *Review* lists them with a reason, and *Keep* brings back any photo that is fine after all.
  Files that cannot be opened are listed there too. In my folder it hides 88 photos:
  - **Blurry:** sharpness below 15. Motion blur (a shaking car, running zebras) was missed by
    this measure, because the streaks look like sharp edges. Measuring at a higher resolution
    did not help either. What worked: asking CLIP whether a photo looks more like "a blurry
    photo / motion blur" or "a sharp, in-focus photo". A smeared serval was just under both
    limits (and too blurry for the object detector to recognise), so a photo that is a little
    off on both measures at once now counts as blurry too. A looser version of this rule also
    hid a good panning shot of a running zebra.
  - **Overexposed:** a burnt-out leopard series against a pale sky. The first rule only counted
    pure white pixels and missed one photo with a pale grey sky. Counting all pale pixels also
    flagged lions on sunny sand. The final rule counts only *flat* pale areas (sky has no
    texture, sand and water do) and requires the rest of the photo to be nearly colourless.
  - **Too dark:** even the brightest 5% of the photo is darker than 50 (of 255). The 5 darkest
    photos were at most 39; dim but usable dusk photos started at 55.
  - **Out of focus:** the camera focused on the grass instead of the lion. Every whole-photo
    measure sees the sharp grass and passes it. An object detector (Mask R-CNN from
    torchvision) now outlines the largest animal or person, and only its pixels are measured.
    The measure blurs them on purpose and checks how much detail is lost (Crete et al. 2007).
    The limit depends on how big the animal is in the frame. It catches 46 clearly soft
    photos, but not mildly soft ones like the lioness that started it: those score like
    sharp photos. Sharp zebras with big flat stripes also score high. A soft lioness between
    two cars was first missed by a small margin; the photos just under the limit for small
    animals were mostly soft too, so that limit was lowered from 0.55 to 0.52. This check takes about
    2 seconds per photo (70 minutes for my folder), so it is saved every 100 photos.
  - Each limit was chosen by looking at the photos just above and below it.
  - **Hidden by hand:** a hazy leopard behind grass looked like an average photo to every
    measure (sharpness, blur, contrast). Instead of yet another rule that would also hide good
    photos, any photo can now be hidden by hand: *Hide* in an opened group or H in the
    full-screen view, undone with *Show again* in *Review*.

**Testing.**
- I opened the real 2,046-photo folder through the app and tested every action (merge, split,
  make single, different settings) through its API.
- An automated browser test (Playwright with Edge) clicked through all the screens and took
  screenshots, including dark mode and a phone-sized window.
- Two problems found this way were fixed: uneven card sizes, and reopening a folder took
  28 seconds instead of 0.4.

**Run it:**
```
cd album_studio
pip install -r requirements.txt
python run.py
```

## What I learned

- Results that look right on a small test set can fail on real data. Looking at the actual
  output (a contact sheet of the chosen photos) is what exposed the wrong species and the
  merged duplicates.
- Small AI models make confident mistakes. Here a larger model and combining evidence (a whole
  burst votes on the species) made the labels much more reliable.
- Planning the full workflow first (all 5 steps) and building one step at a time keeps the
  code easy to extend.
- A single number rarely captures "bad photo". Sharpness misses motion blur, and brightness
  confuses sky with sand. Testing each rule against the whole folder showed what it really
  catches.

## AI Prompts Used

My prompts, with spelling corrected.

**Prompt 1 (the idea):**
> I have a folder with images; in this case, it's from a trip to Africa. I want to create an album of it. The problem is that I have many images that are duplicated multiple times: images that look almost the same, but one of them has better focus or resolution. Also, in this specific case, I want my album to have all the animal species we saw, but also our images. In a different case, I might want to have our images or images of views. I want to design a program that will allow me to enter the number of images to select and maybe what to focus on (for example, animals), and the program will select the best images for me and create a subfolder with copies of the images.

**Prompt 2 (running it on my photos):**
> C:\Users\liliyak\Pictures\Africa 2025\new\101CANON

**Prompt 3 (an error when running it myself from WSL; I pasted the terminal output):**
```
liliyak@lt06268849:/mnt/c/Users/liliyak/Desktop/PythonUsingAI/photo-album-picker$ python album_picker.py "C:\Users\liliyak\Pictures\Africa 2025\new\101CANON" -n 30 --focus animals:3 views:1 --min-quality 0.35
Traceback (most recent call last):
  File "/mnt/c/Users/liliyak/Desktop/PythonUsingAI/photo-album-picker/album_picker.py", line 27, in <module>
    import numpy as np
ModuleNotFoundError: No module named 'numpy'
```

**Prompt 4 (starting over with a graphical interface):**
> Let's start over with the project and build it step by step. The first step: I will give you a folder of images; in this folder, find similar photos and put them under one category. Create a GUI with a comfortable UI/UX. First design the UI/UX platform for creating the full album, then the steps. Make sure that we will be able to add more steps to the album editing later.

**Prompt 5 (this submission):**
> Commit and put this into day03. Add a README.md describing what we did and the prompts I wrote.
>
> Don't include my typos.

**Prompt 6 (two ostrich photos in different groups; I attached a screenshot):**
> My current setting in the code is 92% similarity, but it separates the images attached. What setting should I try to merge them?

**Prompt 7 (sorting inside a group):**
> OK, now inside each group I want to see the best images first, based on quality and resolution (sort inside each group).

**Prompt 8 (bad photos; I attached a blurry photo):**
> The image attached is really blurred. Add a checkbox (use good UI/UX) to hide blurred and corrupted images.

**Prompt 9 (a washed-out leopard photo, attached):**
> Also, this is not a good image, the colours are burnt. How can we detect this and also mark it as a bad image?

**Prompt 10 (a motion-blurred zebra photo, attached):**
> This image passed the blur filter.

**Prompt 11 (another leopard photo, attached):**
> I also want to hide overexposed photos.

**Prompt 12:**
> Commit.

**Prompt 13 (a very dark photo, attached):**
> Sometimes the images are really dark.

**Prompt 14:**
> Remind me, based on what do you decide the similarity of images?

**Prompt 15 (a lioness out of focus in front of sharp grass, attached):**
> I still see some blurred images.

**Prompt 16:**
> Commit the dark images. Detect missed focus automatically.

**Prompt 17 (a soft lioness walking between two safari cars, attached):**
> I have this image. It wasn't marked as blurry, why?

**Prompt 18 (a smeared serval on a dirt track, attached):**
> This image passed the filters.

**Prompt 19 (a hazy leopard half hidden in tall grass, attached):**
> That image also should not pass.
