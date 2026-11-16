# Day 05 Assignment: Tests for the Business Logic

## The assignment

> Write some tests for the "business logic" of your previous applications. You can put them in
> your day04.

## What I did

I wrote tests for the business logic of Album Studio, the photo album app from
[Day 04](../day04/README.md). It holds the business logic of both earlier apps: the Day 03
grouping and the recognition rules of the Day 03 album picker. The tests are in
[day04/album_studio/tests/](../day04/album_studio/tests/) and use **pytest**. There are two kinds:

- **98 fast tests** of the rules, with made-up values (3 seconds).
- **A photo dataset**: real image files in folders whose name is the right answer, checked with
  the app's real analysis and image model. Anyone can make one from their own photos.

**Run them:**
```
cd day04/album_studio
pip install -r requirements-dev.txt
python -m pytest tests                          # the 98 fast tests (datasets are skipped)
python -m pytest tests --dataset                # also the photo dataset of the repository
python -m pytest tests --dataset=D:/my_dataset  # also a dataset of your own photos
```
The fast tests take about 3 seconds; a dataset about a minute the first time (the image models
are loaded) and seconds after that (the analysis is cached).

### What is tested

| File | What it checks | Tests |
|---|---|---|
| `test_analysis.py` | which photos are bad (each rule: blurry, out of focus, too dark, blank, overexposed) and the borderline photos that must *not* be hidden (a sunset silhouette, deep shade); the "soft" hint, also for a soft subject on a sharp background; measuring sharpness and brightness on generated images; finding the photos of a folder (the app's own folders are skipped); the date of a photo without camera data | 37 |
| `test_grouping.py` | the grouping rule (alike photos, time gaps, compared with the group's first photo); merging, splitting and making photos single; keeping and hiding photos by hand; wrong input in the forms | 14 |
| `test_subjects.py` | recognising animals and their species, people and views; *Other animals* when the species is unknown or uncertain; all photos of a group decide together; the species list file | 9 |
| `test_pick_photos.py` | one card per group; picks saved by file name; picks and corrections survive regrouping; hiding with Undo; subjects inside large groups (2 zebras among 12 wildebeest); filters; *Previous / Next group*; correcting subjects; the target; wrong input | 25 |
| `test_export.py` | the album in trip order or by subject, numbered across days; photos hidden later are left out; saving copies of the originals; saving again replaces only the earlier copies | 8 |
| `test_project.py` | the choices are saved and read back; a backup is kept; a damaged file falls back to the backup | 5 |

### How the tests work without photos

The real app needs 2,000 photos and a large image model. The tests need neither:

- **A made-up library.** [conftest.py](../day04/album_studio/tests/conftest.py) builds the app's
  `Library` from analysis values written in the test, e.g.
  `{"emb": photo("animals", "lion"), "sharpness": 5}` is a blurry lion photo. Anything not
  given is the value of a good photo.
- **A fake image model.** The real model turns photos and text into vectors and compares
  them. The fake one gives every subject its own direction ("lion", "zebra", "people"…). A
  photo of a lion points to "animals" and "lion", so the expected result of every test is
  easy to see. It replaces the model only during the tests.
- **Generated images** for the sharpness measures: grey squares with sharp edges, sharp or
  blurred by a known amount.
- **Temporary folders** (pytest's `tmp_path`) for saving and exporting, so nothing is written
  next to the app or into a real photo folder.

### The photo dataset

A photo dataset holds photos whose right answer is known. **The folder a photo is in is the
answer the app must give** (see [tests/README.md](../day04/album_studio/tests/README.md)):

```
quality/good, soft, blurry, unfocused, too_dark, blank, overexposed
subjects/lion, zebra, people, views, other, other animals, ... (any species of the list)
groups/<any name>/      the photos of one burst: they must form one group, alone
```

`test_dataset.py` analyses every photo exactly as the app analyses a photo folder (sharpness,
exposure, the image model, the focus check, softness) and checks it against its folder.

**No photos in the repository.** Datasets are made on each computer by
[make_dataset.py](../day04/album_studio/tests/make_dataset.py), and when the tests run with
`--dataset` and the folder does not exist, they make a **fake dataset** first (about a minute):

- It **draws** two good photos, a landscape and a close-up of pebbles on sand (plus a landscape
  for `subjects/views/`).
- From every good photo it makes **fake photos** whose answer is known because they were made
  that way: blurred, too dark, burnt out, soft, a burst, plus a black and a white photo.
- Tried in a folder that did not exist: the dataset was made, and all 111 tests passed.

**Your own photos** can be added to any folder (or a new dataset started with
`make_dataset.py new` and `add`), and `make_dataset.py fakes` makes fakes from your good photos
too, including out-of-focus ones (only the animal or person blurred, found with the app's subject
detector). Real photos are what a drawing cannot be: animals, people, and photos out of focus.

**Fakes that work for any photo.** Each change starts mild and gets stronger until the app really
sees the problem in that photo (one photo needs more darkening than another); if no strength
works, the fake is skipped and the reason is printed. This came from making the first fakes by
hand, where each try showed how the app works:
- "A little blurred" missed the soft limit; with more blur, a calm landscape counted as *blurry*
  (little fine detail), and a blurred zebra as *out of focus* (the focus check looks at the
  animal). So a soft fake is only made from photos without an animal or person.
- Drawn photos never look shaken to the image model, and the two first drawings (a meadow and a
  sunset) were 0.91 alike, above the grouping limit, so their bursts became one group. A close-up
  of pebbles (0.72 alike) fixed that.

Because each fake is checked with the app when it is made, the fakes pass at first; their value
is protecting against later changes to the rules. **Real photos test the app's judgement.**

### Improving the app with the dataset

I added 16 of my own photos to the folders. 12 got the folder's answer; the other 4 showed where
the app is weak, and two of them led to changes in the app:

| My photo | My folder | The app said | Now |
|---|---|---|---|
| a dog in a dark room with a bright window | too dark | fine | **too dark** |
| the same dog, darker | too dark | blurry | **too dark** |
| a soft white cat on a sharp sofa | blurry | fine | **hidden** (out of focus) |
| a distant lion | blurry *and* unfocused | out of focus | **passes in both** (see below) |

- **Too dark**: a photo counted as too dark only when even its brightest parts were dark, so a
  bright window kept dark room photos shown. New rule: also too dark when most of the photo is
  very dark (half of it darker than 20) *and* nothing is really bright (brightest below 100). The
  second part matters: a limit on the middle brightness alone would also have hidden a sunset
  silhouette (brightest 228) and a lion cub in deep shade next to sunlight (119), both good photos.
  On my 2,046 trip photos the new rule hides no photo that was not hidden before.
- **The soft cat**: the focus check did find the cat, but its blur (0.557) was under the limit
  (0.60), which is that high because sharp zebras reach 0.595. Comparing the subject with the
  sharpest parts of the photo works better (the cat: 0.557 against 0.233), but close-ups showed
  that smooth subjects look the same: the cat, a black dog and a lion cub really were soft, a
  selfie was sharp. So I first only marked such photos *soft* (a hint to zoom in, from a
  difference of 0.27). I did not think the cat should fail, though: it is a bad photo. So a
  bigger difference, 0.30 or more, now hides the photo as out of focus: the cat (0.32) and, of
  my 2,046 trip photos, only one more, a soft black dog (0.35); the sharp selfie (0.25) stays
  well below.
- **Blurry or out of focus**: the distant lion was in `blurry/` and the app hid it as *out of
  focus*. For the user both mean "not sharp, hidden", so the test now accepts either answer for
  either folder.
- New fast tests for both rules, including the photos that must stay shown.

### Testing the tests

A test that always passes is worthless. To check the tests, a script broke one rule of the
app at a time, ran the tests, and put the code back. **All 12 breaks were caught:**

| Rule broken on purpose | Caught by |
|---|---|
| compare a photo with the previous photo instead of the group's first one | `test_photos_are_compared_with_the_groups_first_photo` |
| one photo of another subject is enough to list it | `test_one_photo_of_another_subject_is_not_enough` |
| name a species when only 30% sure | `test_an_uncertain_species_is_other_animals` |
| let photos without animals vote on the species | `test_frames_without_animals_do_not_vote_on_the_species` |
| save without a backup | `test_each_save_keeps_the_previous_version_and_no_temporary_file` |
| don't use the backup when the file is damaged | `test_a_damaged_file_falls_back_to_the_backup` |
| delete everything in the export folder | `test_saving_again_replaces_only_the_earlier_export` |
| hidden photos still count as picked | `test_hiding_a_group_takes_it_and_its_picks_out_and_undo_brings_them_back` |
| "too dark" limit too low | 4 tests |
| read the app's hidden folders as photos | `test_find_images_skips_the_apps_own_folders_and_other_files` |
| merge "one group" | `test_merging_needs_two_groups` |
| don't shorten typed subjects | `test_a_typed_animal_is_tidied_up` |

### Found while writing the tests

- **Blurred random noise is not like a blurred photo.** The first test images were random
  pixels; blurred, they became almost flat, and the softness measure (correctly) skipped them as
  "sky". Squares with sharp edges behave like real photos: the score rises steadily with blur
  (0.11 sharp, 0.45 slightly blurred, 0.85 clearly blurred).
- **A test can pass without testing its rule.** "Frames without animals don't vote on the
  species" passed even with the rule removed, because one view frame barely changed the vote.
  The test now uses 2 wildebeest frames and 5 unclear ones: without the rule the vote is 0.405,
  below the 50% needed, so the test fails if the rule goes.
- No bugs were found in the app itself: the earlier testing through the web pages had already
  covered the main paths. These tests check the rules directly and much faster (3 seconds
  instead of minutes with the real photos).

## What I learned

- Business logic that is separate from the web pages can be tested without a browser, a server
  or real data.
- A fake with known answers (here: the image model) makes tests fast and their expectations
  obvious.
- Each test should check one rule and say which one in its name; a failing test then explains
  itself.
- Testing the tests (breaking the code on purpose) shows which tests really protect a rule.
- Test data in folders named after the answer is easy to understand and to extend: adding a
  test is copying a photo, no code.
- Fast tests with made-up values and slower tests with real images complement each other: the
  first check every rule in seconds, the second check that real photos really behave that way.

## AI Prompts Used

**Prompt 1:**
> Our next assignment is (let's start a new README file for this assignment): Write some tests
> for the "business logic" of your previous applications. You can put them in your day04.

**Prompt 2:**
> I prefer that we create a fake dataset whose answers are known in advance for training, and
> we'll keep those in folders that I will be able to add also my photos.

Claude read "for training" as "for testing": the app does not learn from the photos; the dataset
checks its answers.

**Prompt 3:**
> Can we make better fake photos?

Claude offered three ways (from my photos, from public photos, better drawings). My answer: from
a few of my photos.

**Prompt 4:**
> If someone wants to run the tests on his own computer, I want him to be able to create his own
> datasets for testing.

**Prompt 5** (while that was being built):
> Improve the app for those two misses you mentioned.

**Prompt 6:**
> I prefer not to commit the base photos, but running code that will create me a fake dataset (or
> automatically if the dataset does not exist).

**Prompt 7** (with the two failing tests: the distant lion and the cat in `quality/blurry/`):
> I don't think they should fail.
