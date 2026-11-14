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
- **What stays in JavaScript** ([static/app.js](album_studio/static/app.js), 119 lines instead of 643;
  181 after step 2 added updating the page in place):
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

## Then: step 2, Pick photos

With the web app in place, I added the next step of the album. It was planned first, starting from
what I need on this screen, and only then built.

**What I need when choosing album photos, and the feature for each:**

| I need to… | Feature |
|---|---|
| look only at photos worth considering | one card per step-1 group (its best or picked photo); bad photos stay hidden |
| see what a photo shows | a subject tag on each card: a species, *Other animals*, *People*, *Views* or *Other* |
| see only one subject ("all lions", "photos of us") | subject chips: *Animals*, *People*, *Views*, *Other* and every species, with counts |
| see the photos in a useful order | *Trip order* (by day), *By subject*, *Best first* |
| pick quickly without losing my place | ♡ on every card; the page updates in place, no reload and no jump; **P** in the photo viewer |
| choose another or an extra photo of a burst | *N photos ›* opens the group, best photo first; any number of picks per group |
| know how far I am | album bar: "42 picked of 60" with a progress bar; *Show: Picked* shows the album so far |
| not forget an animal | chips show ♥ picked counts; subjects with nothing picked are dashed and listed as *Not in the album yet* |
| fix a wrong label | in an opened group: choose the right subject, or type an animal that isn't in the list |
| choose several photos of a burst by what happens in them | click a group to open it (as in step 1); its photos are in the order taken, not best first |
| get boring photos out of the way | *Hide* under every card, without opening it; *Undo* in the message; *Show: Hidden* to bring one back |
| not lose work | every click is saved; picks and corrections are kept per photo, so they survive regrouping in step 1 |

The planned steps 2–4 (pick the best photo, recognise subjects, choose the album) became this one
step, and *Arrange and export* is now step 3. I chose to pick by hand; an automatic suggestion
can come later.

**Recognising subjects** ([studio/subjects.py](album_studio/studio/subjects.py)) reuses the
business logic of the day03 album picker: the same AI model (CLIP), the descriptions of animals,
people and views, the 58-species list, and the rule that all photos of a group decide the species
together and only when the model is at least 50% sure. Every photo's CLIP embedding was already
saved in step 1, so only the text descriptions need the model. They are embedded once (about a
minute, with a progress page) and cached, and recognising all groups then takes 0.04 seconds.

Checking the result on my photos:
- A contact sheet of every subject showed that most labels are right: lions, zebras, hippos,
  elephants, birds, people, and indoor photos as *Other*. 29 species were found, as in day03.
- 30 groups were *Other animals*. A per-photo vote would name 16 of them, but about half of those
  names were wrong (safari cars as lions, vultures as secretary birds, people as wildebeest),
  so I kept the careful rule: *Other animals* is easy to fix by hand, a wrong species is not.
- Photos of people in front of the savanna were counted as animal photos. Seven more
  descriptions ("people looking through binoculars in the savanna", "a woman standing in the
  savanna", …) doubled the *People* groups from 5 to 10. The three binocular and portrait groups
  are now right; two safari-car groups also moved to People, and they were wrong before too.

**Testing** (again on the real photos, saving to a copy of `project.json`):
- 36 checks over HTTP, all passing:
  - the progress page the first time (11 s), then 0.04 s per page
  - all 81 combinations of subject, show and order
  - picking and removing a photo, and several picks in one group
  - the target and its message
  - correcting a subject from the menu and by typing, and going back to the recognised one
  - picks kept after regrouping in step 1; a picked photo hidden in step 1 leaves the album
  - wrong input and old links; *Next* to step 3
- After the changes from prompt 4 (below), 52 checks: the ones above, plus clicking a group opens it,
  the group's photos are in time order, hiding a group (its picks leave the album and come back
  with Undo), the Hidden tab and *Show again*, hiding one photo in an opened group, and wrong input.
- The step 1 checks pass too. One of them had to change: it assumed 85% is a looser setting
  than my saved 83%.
- Screenshots: the main page, one species, by subject in dark mode, an opened group, a phone.
  Clicked in the page: picking after scrolling down (the page stays in place and the counts
  update), and **P** in the photo viewer.
- They led to these changes: the long *Not in the album yet* list now folds after 15 names;
  phones show two photos per row; the viewer's *Picked* button is orange instead of the red
  used for hiding; on phones the "6 photos" count moved to the top corner so it doesn't cover the
  subject.
- Hiding was also clicked in the page: the card leaves without the page jumping, and the message
  "2 photos hidden · Undo" appears.
- A bug I found while using it (prompt 5): after hiding every photo inside a group, the group still
  seemed to be there. It was hidden, but I was still on the group's page, and the browser's Back
  button showed the old list from its cache. Now hiding the last photo goes back to all groups
  ("…the whole group is hidden now · Undo"), pages are sent with `Cache-Control: no-store`, and
  a partly hidden group's card counts only the photos still shown ("1 photo · 1 hidden").
  7 more checks (59 in all), and a click test in the browser.
- After prompt 6, Hide and ♡ sit together on every photo, and the photo viewer has both buttons
  (P and H; after H it goes on to the next photo, so going through photos large is quick). Checked
  by clicking in the browser: in the list, in an opened group (hiding the last photo goes back to
  all groups) and step 1's viewer, which uses the same code. On phones the "6 photos" count moved
  under the photo, because the buttons need the top of it.
- Making that work showed another small bug: when a button led to another page (e.g. *Make ticked
  photos single* in step 1), its message was lost. `app.js` now shows the page it received,
  message included.

## Then: a product review, and what came out of it

I asked Claude to review Album Studio as a product. The review used my photos and settings,
the code, and what had come up while I used it. Its main findings:

1. **Nothing came out of the app.** Photos could be picked, but there was no step 3, so no
   album.
2. **A few groups held most of the photos.** With my settings (83%, any time), 26 of 145 groups
   held 65% of the photos (the largest 118), each shown in step 2 as one photo with one subject.
3. **Going through the photos took many clicks**: open a group, go back, open the next one.
4. **Sharpness could not be judged**: no zoom, and slightly soft photos pass the blur check
   (it measures at 1024 pixels, where a blur a few pixels wide disappears).
5. **Two kinds of "hidden"** (bad photos in step 1, uninteresting ones in step 2) looked the same.
6. **project.json was overwritten in place**: a crash while saving could lose all choices.

I asked to implement all of the suggestions:

| Suggestion | What was built |
|---|---|
| Step 3, first version | the album in trip order or by subject, numbered; *Save the album* copies the originals into `album_export` with `album.html` (a page to print or save as PDF); *Open the folder* |
| Safe saving | write a temporary file, then replace `project.json`; the previous version is kept as `project.json.bak` and used if the file is damaged |
| Going through photos | *Previous / Next group* in an opened group (same filter and order as the list); *Review one by one ▶*: the viewer goes on from group to group (← →, ↑ ↓, P, H) |
| Zoom | click the photo (or Z) for full size, drag to look around |
| Large groups | step 1 warns about groups over 30 photos and offers 88% within 2 minutes; in step 2 large groups are also recognised photo by photo, so e.g. the 7 lion photos in a 62-photo wildebeest group are found under *Lion* |
| "Soft" badge | a sharpness check at half size for every photo; photos above the limit get a *Soft* badge (a hint, not hidden) |
| Two kinds of hidden | I kept my word "Hide" in step 2; the list now says how many bad photos step 1 left out, with a link, and the Hidden tab explains the difference |

**Choosing the "soft" limit.** The new measure blurs each part of the photo on purpose and
checks how much detail is lost (a sharp photo loses a lot, a soft one hardly anything), at half
size: at 1024 pixels a slight blur disappears, and at full size camera noise looks like detail.
It was measured on all 2,046 photos (13 minutes, 0.35 s per photo), and close-ups of photos at
each score showed where "soft" starts: up to 0.40 they were sharp, above 0.44 most were clearly
soft, including the blurred warthogs that had passed the blur check (0.463 and 0.448). 26 photos
are above 0.44. Close-ups of zebras can score high while sharp (their wide stripes have little
fine detail), so the result is a badge to look closer, not a reason to hide a photo.

**Large groups.** With my settings, recognising the photos of large groups one by one found
other subjects in 12 groups: 11 zebra and 7 lion photos in a 62-photo wildebeest group,
16 hartebeest in an *Other animals* group, 3 photos of people in a lion group. They are now
found under those subjects. It did not help the warthogs I had asked about: _MG_1170 is a group
of its own, and one by one the warthog photos were recognised as wildebeest, rhinoceros,
hippopotamus and hyena (once as warthog). At that distance the image model can't tell, so the
subject has to be corrected by hand.

**Testing** (my real photos; choices saved to a copy of `project.json`; the export written to a
test folder, never into my photo folder; the softness values taken from the calibration run, so
my analysis cache was not changed):
- Step 2: 71 checks, all passing. New: lions found inside a wildebeest group, opening it shows
  just the 7 lion photos (and all 62 on request), *Previous / Next group* follow the list's
  filter and order, *Review one by one* starts at the first group, *Soft* badges, and the note on
  bad photos.
- Step 3, the step 1 note and saving: 25 checks, all passing.
  - The copies are identical to the originals, `album.html` shows them in order, and saving again
    replaces only the earlier copies (a file of mine in the folder stays).
  - *Try 88% within 2 min* takes the groups over 30 photos from 17 (the largest 118) to 8 (the
    largest 66).
  - A damaged `project.json` falls back to the backup.
- Step 1: all checks pass.
- The real analysis run on a small test folder: the softness pass measures new photos once,
  continues from the cache, and gives the same values as the calibration.
- In Edge: *Review one by one* opened the first group with the viewer; ↓ went to the next group,
  → past its last photo went on to the group after, Z zoomed in to full size. Screenshots of
  the step 1 note, the lions inside the wildebeest group, step 3 and the album page.

## Then: a calmer design

Looking at the result, I found the screen too busy. I asked Claude to review it as a UI/UX
designer and design an elegant solution. The review:

1. **Every card had four dark labels on the photo** (Hide, ♡, subject, count): 100 of them on
   one screen. They covered the photos, had the same weight, and cut off the subject
   ("Other anir", "Wildebees").
2. **The first photo started halfway down the screen**, below a three-line description, four rows
   of species chips, a hint and a toolbar.
3. **Hide looked as important as ♡**, on every photo, all the time.
4. **Some information appeared twice**: the count as a label and as the stacked-photo effect.

The design, "the photo first, quiet labels, controls when you need them":
- **Cards**: nothing on the photo. One caption line under it: the subject with its coloured dot,
  and the number of photos with a small stack icon (or "soft").
- **Actions**: two small round icon buttons (a crossed-out eye to hide, ♡ to pick) appear on
  hover or keyboard focus, and always on touch screens. A picked photo always shows its filled ♥
  and an outline, so the album is visible at a glance.
- **The top of the page**: a one-line description; the species only after choosing *Animals*;
  "27 subjects not in the album yet" as one line that opens; no hint before the first pick.
  The first photo now starts about 180 pixels higher.
- **An opened group**: the same cards; the subject form folded into *Wrong subject? Change it*.
- **Step 3**: the same cards, with the album number in the caption.

Tests: the step 2 checks were updated to the new page (72, all passing, including that the first
view has no species row and no hint, and that *Animals* shows the species); step 3 (25) and
step 1 pass too. Screenshots: the main page, keyboard focus on a card, *Animals*, an opened
group, step 3, dark mode, a phone.

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
- Planning a screen from what the user needs (one row per need, one feature per row) made it clear
  what to build and what to leave out.
- The business logic from day03 (the recognition rules) could be reused as it was. Its
  weak spot only showed on new data, the loosely grouped photos of people, and was fixed by
  checking contact sheets.
- A cautious label ("Other animals") is often better than a confident wrong one.
- A review of the whole product found what testing single features did not: the app had no
  output yet, and one setting in step 1 (very loose groups) made step 2 much harder.
- A screen can have every feature and still be hard to use. Removing things from view (labels
  on photos, chips not needed yet) made it easier, without removing any feature.
- Thresholds need real data: the "soft" limit came from looking at close-ups of photos at
  each score, and it is shown as a hint because some sharp photos (zebra stripes) score high.
- Using the screen showed what the plan missed: choosing photos of a burst is about what happens
  in them, not their quality, and removing things needs to be as quick as picking them (with Undo,
  so it is safe to be quick).

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

**Prompt 3:**
> Let's write step 2: pick photos. In this step we will pick the good photos for the album. In this
> screen I want to have the option to filter and order the photos by subjects (by recognising what's
> in the photo). Plan and only then implement. Make sure you define the needs of the user first and
> the features that the user needs in this screen. Make sure that it is comfortable for the user and
> has all the features that the user needs, and also has correct UI/UX.

Claude asked four questions before planning. My answers: merge the planned steps 2–4 into
*Pick photos*; pick by hand (no automatic suggestion); one card per group; allow correcting
subjects by hand.

**Prompt 4** (after trying step 2):
> Sometimes there are a few photos that I would like to select from the grouped collection. I think
> that the second screen should be similar to the first one (clicking on the image will open the
> group), but here we will select the images by interest, not quality. Also, I want the option to
> hide the image from the screen itself, without clicking on it.

**Prompt 5:**
> Found a bug: inside a group I hide all the images, but I still see it as a group.

**Prompt 6** (with screenshots of a card and of the photo viewer):
> I think that in both cases it will be easier to have both pick and hide.

**Prompt 7:**
> Do a product review and check how we can improve the product.

**Prompt 8:**
> Implement all.

**Prompt 9** (with a screenshot of the cards):
> It seems to me that the UI/UX is not good, it's too much. Review it from the point of view of a
> UX/UI specialist and design an elegant solution.
