# Album Studio

Turn a folder of trip photos into an album, one step at a time, in a friendly app that
runs on your own computer. Your original photos are never changed.

| Step | Status |
|---|---|
| 1. Group similar photos: bursts and retakes are stacked into one group | **ready** |
| 2. Pick the best photo of each group | planned |
| 3. Recognise what's in the photos (animals and species, people, views) | planned |
| 4. Choose the album photos (how many, what to focus on) | planned |
| 5. Arrange and export | planned |

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
70 minutes for 2000 photos; it continues where it stopped if the app is closed). After that
the folder opens in under a second.

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
  soft while the background may be sharp), almost entirely black or white, too
  dark (even the brightest parts are dark), or overexposed (more than 20% flat, pale sky and the rest nearly colourless). *Review* lists them, with *Keep* for any that are fine after all,
  plus files that could not be opened. The thresholds are in `studio/analysis.py`.
- To hide a bad photo the checks missed, click *Hide* under it in an opened group, or press
  H in the full-screen view. It is hidden with the others while the switch is on, and *Review*
  lists it as "Hidden by you" with *Show again*.
- Click any photo to see it large; use ← → to browse and Esc to close.
- Changes are saved automatically.

## Where things are saved

Inside the photo folder, in a hidden `.album_studio` folder:
`analysis.npz` (the analysis of every photo), `thumbs/` (small previews) and
`project.json` (your choices in each step). Delete this folder to start a project from scratch.

## How it is built

The pages are made by Flask from templates, and every button is a plain HTML form: it is sent
to the server, the step changes its results, and the browser goes back to the page, which shows
the new state and a short message ("post/redirect/get").

```
run.py                     starts the local web server and opens the browser
studio/                    the business logic, plus the Flask routes
  analysis.py              reads photos once: date, sharpness, CLIP embedding, thumbnail (cached)
  project.py               one album project: its photos, saved choices, background jobs
  server.py                Flask routes: turn page requests and forms into calls to the steps
  steps/
    base.py                Step base class: the contract every step follows
    group_similar.py       step 1: grouping and fixing groups, and what its pages show
    __init__.py            STEPS: the list of steps, in sidebar order
templates/                 the pages (Jinja)
  layout.html              top bar, messages, photo viewer
  welcome.html             choose a folder
  progress.html            progress bar while the photos are analysed (reloads every second)
  workspace.html           sidebar with the steps; each step page extends it
  steps/group_similar.html          step 1: settings, all groups, merging
  steps/group_similar_stack.html    step 1: one group opened
  steps/group_similar_review.html   step 1: blurry and bad photos
  steps/planned.html                "coming soon" page for steps that are not built yet
static/
  app.css                  design (light and dark mode, narrow windows)
  app.js                   small extras the server can't do: the photo viewer, sending a form as
                           soon as a slider moves, keeping the scroll position
```

The pages are:

| Address | Page |
|---|---|
| `/` | welcome (or the open project) |
| `/progress` | progress while the photos are analysed |
| `/step/<id>` | a step's main page, e.g. `/step/group?show=stacks` |
| `/step/<id>/<page>` | another page of a step, e.g. `/step/group/stack/412`, `/step/group/review` |
| `POST /step/<id>/do/<action>` | a button press, e.g. `/step/group/do/merge` |
| `/thumb/<n>`, `/photo/<n>` | a photo's thumbnail and large version |

### Adding a step

1. Write a `Step` subclass in `studio/steps/my_step.py` with `id`, `title`, `tagline`,
   `description` and `template = "steps/my_step.html"`.
   - `get(project)` and `action(project, name, payload)` are the business logic: the step's results
     and the changes the user can make. The photo analysis is in `project.library` (dates,
     quality, CLIP embeddings). Results of earlier steps are in `project.step_state("group")` etc.
   - `page(project, view, args)` returns the template and the data a page shows.
   - `form_action(project, name, form)` reads a form, calls `action()` and returns a message.
2. In `studio/steps/__init__.py`, replace the step's `PlannedStep(...)` in `STEPS` with your
   class (or add it where it should appear).
3. Write `templates/steps/my_step.html`, starting with `{% extends "workspace.html" %}` and
   putting the page in `{% block step %}`. Buttons are forms that post to
   `url_for('step_action', step_id=step.id, action='...')`. Links with class `view` open
   the photo viewer.

