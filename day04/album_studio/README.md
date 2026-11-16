# Album Studio

Turn a folder of trip photos into an album, one step at a time, in a friendly app that
runs on your own computer. Your original photos are never changed.

| Step | Status |
|---|---|
| 1. Group similar photos: bursts and retakes are stacked into one group | **ready** |
| 2. Pick photos: find photos by what's in them (animals and species, people, views) and pick them | **ready** |
| 3. Arrange and export: the album in order, saved as a folder of copies with a page to print | **ready** |

## Start

```
pip install -r requirements.txt
python run.py
```

The app opens in your browser. Keep the terminal window open while you work. Run it from
Windows (PowerShell or the VS Code terminal), not WSL, because the packages are installed in
Windows Python.

The first time a folder is opened, every photo is analysed once: about 3–15 minutes for
2000 photos, plus about 2 seconds per photo to check the focus on animals and people (about
70 minutes for 2000 photos), and about 0.35 seconds per photo to check the sharpness in detail
(about 12 minutes). Both continue where they stopped if the app is closed. After that the folder
opens in under a second.

## Step 1: Group similar photos

- **How similar must photos be?** Move right for stricter groups (only near-identical photos),
  left for bigger groups.
- **Taken within**: photos of one burst are taken seconds apart. *Any time* also stacks the
  same view photographed hours later.
- Click a stack to see all its photos. Tick the photos that don't belong, then
  *Move ticked photos to a new group* or *Make ticked photos single*.
- Tick two or more groups (circle in the corner) and click *Merge into one group*.
- *Hide blurry and bad photos* (on by default) hides photos that are blurry (sharpness below
  15, or motion blur that the image model recognises), out of focus (the animal or person is
  soft while the background may be sharp, or much softer than the sharpest parts of the photo), almost entirely black or white, too
  dark (even the brightest parts are dark, or most of the photo is very dark and nothing in it
  is really bright, like a dark room with a bright window), or overexposed (more than 20% flat, pale sky and the rest nearly colourless). *Review* lists them, with *Keep* for any that are fine after all,
  plus files that could not be opened. The thresholds are in `studio/analysis.py`.
- To hide a bad photo the checks missed, click *Hide* under it in an opened group, or press
  H in the full-screen view. It is hidden with the others while the switch is on, and *Review*
  lists it as "Hidden by you" with *Show again*.
- **Very large groups**: if some groups have more than 30 photos, a note says so and offers a
  stricter setting (88% within 2 minutes). Big groups mix different moments and animals, and
  step 2 would show each of them as one photo with one subject.
- Click any photo to see it large; use ← → to browse and Esc to close.
- Changes are saved automatically.

## Step 2: Pick photos

- Every group from step 1 is one card: its best photo (or the one you picked), and under it what
  it shows (an animal species, *Other animals* when the species is not certain, *People*, *Views*
  or *Other*) and how many photos it has. Point at a card (or tab to it) for its two buttons:
  hide and ♡. On a touch screen they are always shown. Picked photos keep their ♥ and an outline.
- **Subjects**: click *Animals*, *People*, *Views* or *Other* to see only those; *Animals* also
  shows the species (*Lion 23*). The numbers are groups; ♥ shows how many photos of that subject
  are picked. A dashed border means nothing is picked yet, and the line *N subjects not in the
  album yet* opens the list of them, so none is forgotten.
- **Order**: *Trip order* (by day), *By subject* (a section per subject) or *Best first*.
- **♡** picks a photo, **♥** removes it. The page updates in place. *Show: Picked* shows the album so far.
- **Hide** (the crossed-out eye next to ♡) takes a group you don't want off the screen; the message has **Undo**.
  Hidden groups are left out of the album and the counts; *Show: Hidden* lists them with *Show again*.
- Type a **target** ("of 60") to see a progress bar; it says so when you reach it.
- **Large groups** (10 photos or more) are also recognised photo by photo: if at least 2 of their
  photos show another subject (some zebras among wildebeest, people next to a lion), the group is
  found under that subject too. The card then shows one of those photos and "7 of 62 photos",
  and opening it shows just those photos (with a link to all of them).
- **Soft** on a photo: it looks soft when seen large (measured at half size, where a slight blur
  shows), or its animal or person is much softer than the rest of the photo (a soft cat on a sharp
  sofa). It is only a hint, because smooth subjects (skin, dark fur) also measure soft: zoom in to
  judge (Z in the viewer).
- **Click a group** to open it (as in step 1): all its photos in the order they were taken, so you
  choose by what is interesting, not by quality. ♡ as many as you like, and *Hide* the ones you don't
  want to see (hidden photos stay there, faded, with *Show again*). Hiding the last one hides the
  whole group and goes on to the next group. If the subject is wrong, open *Wrong subject? Change
  it* and choose the right one, or type an animal that is not in the list. It applies to the whole group.
- Click a single photo (or a photo in an opened group) to see it large: ← → to browse, **P** to pick
  or remove it, **H** to hide it (the viewer goes on to the next photo). **Click the photo or press
  Z** to zoom in to full size; drag to look around, click again to zoom out.
- **Previous / Next group** (in an opened group) go through the groups in the list's order, with
  its filter. **Review one by one ▶** starts at the first group with the viewer open: ← → through
  the photos and on into the next group, ↑ ↓ to jump to the group before or after, P to pick,
  H to hide, Z to zoom.
- The list says how many *bad photos* step 1 left out, with a link to them: they are a different
  list from the photos you *Hide* here.
- The first time, the image model learns the subject names (about a minute; a progress page is
  shown). The animals it knows are in `studio/species_africa.txt`; replace the list for another trip.
- Photos hidden in step 1 are not shown and leave the album. Picks and corrected subjects are kept
  when you regroup in step 1.

## Step 3: Arrange and export

- The album: every photo you picked (and haven't hidden since), numbered, in **Trip order**
  (a section per day) or **By subject** (subjects in the order you met them on the trip).
  ♥ (or P in the viewer) takes a photo out of the album.
- **Save the album** copies the original photos, numbered in album order ("007 _MG_1172.JPG"),
  into `album_export` in the photo folder, with `album.html`: a page with all of them, their
  numbers and captions, to print or save as PDF. Saving again replaces only the files of the
  earlier export; anything else in the folder stays. The originals are never changed.
- **Open the folder** opens it in Explorer; **Album page** shows the same page from the app.

## Where things are saved

Inside the photo folder, in a hidden `.album_studio` folder:
`analysis.npz` (the analysis of every photo), `thumbs/` (small previews) and
`project.json` (your choices in each step). Each save first writes a temporary file and then
replaces `project.json`, keeping the previous version as `project.json.bak`, so a crash while
saving never leaves a damaged file (if it is damaged anyway, the backup is used).
Delete this folder to start a project from scratch. The exported album is in `album_export`.
Next to the app, `text_embeddings.npz` keeps what the model learned about the subject names
(the same for every folder).

## How it is built

The pages are made by Flask from templates, and every button is a plain HTML form: it is sent
to the server, the step changes its results, and the browser goes back to the page, which shows
the new state and a short message ("post/redirect/get"). With JavaScript on, `app.js` sends the
form in the background and swaps in the new page content, so a click (e.g. ♡) doesn't reload the page.

```
run.py                     starts the local web server and opens the browser
studio/                    the business logic, plus the Flask routes
  analysis.py              reads photos once: date, sharpness, CLIP embedding, thumbnail (cached)
  subjects.py              recognises what's in a group: species, people, views (from the embeddings)
  species_africa.txt       the animals subjects.py knows
  project.py               one album project: its photos, saved choices, background jobs
  server.py                Flask routes: turn page requests and forms into calls to the steps
  steps/
    base.py                Step base class: the contract every step follows
    group_similar.py       step 1: grouping and fixing groups, and what its pages show
    pick_photos.py         step 2: picks, subjects, filters and orders, and what its pages show
    export.py              step 3: the album's order and saving it as a folder
    __init__.py            STEPS: the list of steps, in sidebar order
templates/                 the pages (Jinja)
  layout.html              top bar, messages, photo viewer
  welcome.html             choose a folder
  progress.html            progress bar of a background job (reloads every second)
  workspace.html           sidebar with the steps; each step page extends it
  steps/group_similar.html          step 1: settings, all groups, merging
  steps/group_similar_stack.html    step 1: one group opened
  steps/group_similar_review.html   step 1: blurry and bad photos
  steps/pick_photos.html            step 2: album bar, subjects, all groups to pick from
  steps/pick_photos_group.html      step 2: one group opened, with its subject
  steps/export.html                 step 3: the album, its order, saving it
  export_sheet.html                 the album page (album.html), also for printing
  steps/planned.html                "coming soon" page for steps that are not built yet
static/
  app.css                  design (light and dark mode, narrow windows)
  app.js                   small extras the server can't do: updating the page in place, the photo
                           viewer (zoom, going from group to group), sending a form as soon as a slider moves
```

The pages are:

| Address | Page |
|---|---|
| `/` | welcome (or the open project) |
| `/progress` | progress while the photos are analysed (or a step prepares) |
| `/step/<id>` | a step's main page, e.g. `/step/group?show=stacks`, `/step/pick?subject=lion&order=quality` |
| `/step/<id>/<page>` | another page of a step, e.g. `/step/group/stack/412`, `/step/pick/group/412?subject=lion`, `/step/export/sheet` |
| `POST /step/<id>/do/<action>` | a button press, e.g. `/step/group/do/merge` |
| `/thumb/<n>`, `/photo/<n>` | a photo's thumbnail and large version (`?size=4000` for zooming in) |

### Tests

The business logic has its own tests (pytest), with made-up photo data and a fake image model,
so they need no photos and take about 3 seconds:

```
pip install -r requirements-dev.txt
python -m pytest tests
python -m pytest tests --dataset                # also the photo dataset: real images, real image model
python -m pytest tests --dataset=D:/my_dataset   # a dataset of your own photos
```

A photo dataset holds photos in folders named after the answer the app must give (e.g.
`quality/blurry/`, `subjects/lion/`). It is not in the repository: with `--dataset`, a fake one is
made first if the folder does not exist (drawn photos and fakes made from them), and you can add
your own photos. See [tests/README.md](tests/README.md).

See [../../day05/README.md](../../day05/README.md) for what they check.

### Adding a step

1. Write a `Step` subclass in `studio/steps/my_step.py` with `id`, `title`, `tagline`,
   `description` and `template = "steps/my_step.html"`.
   - `get(project)` and `action(project, name, payload)` are the business logic: the step's results
     and the changes the user can make. The photo analysis is in `project.library` (dates,
     quality, CLIP embeddings). Results of earlier steps are in `project.step_state("group")` etc.
   - `page(project, view, args)` returns the template and the data a page shows.
   - `form_action(project, name, form)` reads a form, calls `action()` and returns a message.
   - `prepare(project)` (optional) returns a background `Job` for slow work needed first, such as
     loading a model; the progress page is shown until it is done.
2. In `studio/steps/__init__.py`, replace the step's `PlannedStep(...)` in `STEPS` with your
   class (or add it where it should appear).
3. Write `templates/steps/my_step.html`, starting with `{% extends "workspace.html" %}` and
   putting the page in `{% block step %}`. Buttons are forms that post to
   `url_for('step_action', step_id=step.id, action='...')`. If `form_action()` returns
   `(message, fields)`, the message gets an Undo button that sends `fields`. Links with class `view` open
   the photo viewer. Each hidden form with class `viewer-action` gives the viewer a button and a
   key (`data-key`) for the shown photo; its `data-flag` names the link attribute that says whether
   it is on (e.g. `data-hidden="1"`).

