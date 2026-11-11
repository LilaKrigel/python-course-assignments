# Day 04 Assignment: Album Studio as Flask Web Pages

## The assignment

> Take the previous assignment, or a previous project you implemented. Copy it to the day04
> folder just so we will have the old one intact. Write a web application (e.g. using Flask) that
> will use the "business logic" from the previous implementation and provide a web interface to it.

## What I did

I copied Album Studio, the photo album app from Day 03 ([../day03/README.md](../day03/README.md)),
into [album_studio/](album_studio/). The Day 03 copy is unchanged.

Album Studio already ran in the browser, but almost all of its interface was JavaScript: Flask only
sent one empty HTML page and answered JSON requests, and 643 lines of JavaScript built every screen,
decided which groups to show, counted them and handled every button. For this assignment I rebuilt
the interface as a **Flask web application**: Flask now makes every page from templates, and
every button is an HTML form handled by Flask. The features stayed the same.

### The business logic (unchanged)

| File | What it does |
|---|---|
| `studio/analysis.py` | reads every photo once: date, sharpness, exposure, focus, CLIP embedding, thumbnail |
| `studio/project.py` | one album project: the photos, the saved choices, the background analysis |
| `studio/steps/group_similar.py` | step 1: groups similar photos; merge, split, make single; hide bad photos |

The steps keep their two business-logic methods: `get()` (the step's results) and
`action(name, payload)` (a change, such as merging groups).

### The web application (new)

- **`studio/server.py`: Flask routes.** Each screen has its own address (`/`, `/progress`,
  `/step/group`, `/step/group/stack/412`, `/step/group/review`), and each button posts to
  `/step/<step>/do/<action>`. After a button press the browser is sent back to the page
  (post/redirect/get). The page then shows the new state and a short message from Flask's `flash()`.
- **`templates/`: Jinja templates** for the welcome page, the progress page, the sidebar with the
  steps, and the step 1 pages. A new step only needs a template that extends `workspace.html`.
- **Logic moved from JavaScript to Python.** Which groups are shown (without hidden photos),
  the trip days, the counts, the captions and the "loose / balanced / strict" label are now
  computed in `group_similar.py` (`main_page()`, `stack_page()`, `review_page()`). The forms are
  read by `form_action()`, which calls the unchanged `action()`.
- **What stays in JavaScript** ([static/app.js](album_studio/static/app.js), 119 lines instead of 643):
  only what a server can't do: the full-screen photo viewer (← → and H), sending a form as soon
  as a slider or switch changes, the thumbnail size slider, and keeping the scroll position after a
  button reloads the page. Without JavaScript the app still works through buttons.
- **Done without JavaScript:**
  - The progress page reloads itself every second with an HTML `<meta refresh>` tag.
  - Selecting groups for merging works with CSS alone. The checkboxes are real form fields,
    the merge bar appears with `:has(:checked)`, and the "3 selected" count uses CSS counters.
- **Small improvements on the way:** an old link to a group that has changed shows a message
  instead of an error; on touch screens the tick circles are always visible (before, they only
  appeared on mouse hover); messages fade out by themselves.

**Run it:**
```
cd album_studio
pip install -r requirements.txt
python run.py
```

### How it was tested

Testing used my real folder of 2,046 photos. Step 1 saves its choices in `project.json` inside the
photo folder, so the test server saved to a copy instead, and my own choices were not changed
(checked afterwards).

- **Every button, through the web app, the way a browser sends it** (28 checks, all passing):
  - the three tabs and both grouping settings (252 → 190 groups with looser settings)
  - the "hide bad photos" switch (1,959 ↔ 2,046 photos)
  - merging two groups; merging one group is refused
  - moving photos to a new group; ticking every photo is refused
  - hiding a photo by hand, and showing it again from *Review*
  - keeping a flagged photo, and undoing it
  - undoing all changes by hand, and the *Next* button
  - an old group link, a non-number in the form, an unknown step
  - thumbnails (with browser caching) and large photos
- **The welcome and progress pages:** a folder that doesn't exist, a failed analysis, and pages
  opened before the photos are ready.
- **Screenshots in Edge:** step 1, an opened group with a ticked photo, selecting three groups (the
  merge bar shows "3 selected"), the photo viewer, *Review*, a planned step, the welcome page,
  dark mode and a phone-sized window. To click inside the page (tick groups, open the viewer),
  the test server had an extra test-only page that loads the app in a frame and clicks in it.
  Two problems found this way were fixed: the merge bar showed "0 selected" when nothing was
  ticked, and the buttons above an opened group were indented.
- Speed: the step 1 page with 252 groups is made in 0.03 s (177 KB of HTML), and the thumbnails are cached
  by the browser, so reloading a page after each button press is quick.

## What I learned

- "Using Flask" can mean very different things. In Day 03, Flask only answered JSON and the browser
  did the work. Now Flask makes the pages. Moving the page logic into Python made it easier to
  read and to test: the test sends forms and reads the HTML, and needs no browser.
- Post/redirect/get keeps form apps simple: every button is a form, and every answer is the page
  again. Things a JavaScript app gets for free had to be added back: keeping the scroll position,
  and the photo viewer staying open after hiding a photo.
- Modern CSS (`:has()`, counters) can do interface work that used to need JavaScript.
- Before testing on real data, check where the app saves. Here a copy of `project.json` kept my own
  work safe.

## AI Prompts Used

**Prompt 1:** the assignment text above, with:
> In this environment we have a project in day03. This is the homework we got for Assignment (day 4).

Claude first built a web app for the command-line `album_picker` (Album Studio already had a web
interface).

**Prompt 2:**
> Delete the album picker, I want to continue with the album_studio. Do the same task (write a web
> application (e.g. using Flask) that will use the "business logic" from the previous implementation
> and provide a web interface to it) with this code.

Claude pointed out that Album Studio was already a Flask app and asked what to do. My answer:
*Rebuild with Flask pages*: keep the same features, but make the interface Flask/Jinja pages so
more of it is Python and less is JavaScript.
