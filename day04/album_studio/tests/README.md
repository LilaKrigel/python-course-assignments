# Tests

```
pip install -r requirements-dev.txt
python -m pytest tests                          the fast tests of the business logic (3 seconds)
python -m pytest tests --dataset                also a photo dataset (tests/dataset)
python -m pytest tests --dataset=D:/my_dataset  also a photo dataset somewhere else
```

**The fast tests** (`test_*.py` except `test_dataset.py`) check every rule of the app with
made-up analysis values and a fake image model, so they need no photos.

**A photo dataset** is checked by `test_dataset.py`: real image files go through the app's real
analysis and image model. The first run takes one or two minutes (the models are loaded and every
photo is analysed); the results are cached in the dataset's `.album_studio/` folder, so later runs
take seconds and only new photos are analysed.

## When a test fails: the log

The app's business logic writes a log of what it does: what each function received, what it
measured, and which rule decided. When a test fails, pytest prints that log under the failure
("Captured log call"), each line with the file, line and function it came from, so you can see
where it went wrong without a debugger. The tests also log the photos they made up.
For example, with the rule "another subject needs at least 2 photos" broken on purpose:

```
FAILED tests/test_pick_photos.py::test_one_photo_of_another_subject_is_not_enough
E   AssertionError: assert {'zebra': [10]} == {}
------------------------------ Captured log call ------------------------------
DEBUG conftest.py:130 make_library() | test photo p10.jpg: shows ['animals', 'zebra'], taken +86500s
...
DEBUG subjects.py:133 recognise() | group of photos [10]: animals (...); species vote of frames [10]: zebra 1.00 (needs 0.5) -> zebra
DEBUG pick_photos.py:82 cards() | group 6 (12 photos, a large group): photo by photo {'wildebeest': 10, 'zebra': 1, 'other animals': 1}; other subjects shown by at least 1 photos (...): ['zebra']
DEBUG pick_photos.py:92 cards() | card 6: wildebeest, photos [...] shown, [] hidden here, [] picked, cover 17, also {'zebra': 1}
```

To watch the log of a test that passes (here one test, by name):
```
python -m pytest tests -k test_one_photo_of_another -o log_cli=true --log-cli-level=DEBUG
```
The log lines are `log.debug(...)` in `studio/*.py`; they are off when the app runs normally.
`pytest.ini` sets their format, and `conftest.py` turns them on for the tests (the app's own
lines only, not those of libraries like Pillow).

## A photo dataset

**The folder a photo is in is the answer the app must give:**

| Folder | The app must say |
|---|---|
| `quality/good/` | a good photo: shown, not marked soft. **Fake photos are made from these.** |
| `quality/soft/` | shown, but marked *soft* (looks soft when seen large, or the animal is much softer than the rest) |
| `quality/blurry/` | hidden as blurry (or as out of focus: both mean "not sharp") |
| `quality/unfocused/` | hidden as out of focus: the animal or person is soft, the background sharp (or as blurry) |
| `quality/too_dark/` | hidden as too dark |
| `quality/blank/` | hidden as blank (almost all black or white) |
| `quality/overexposed/` | hidden as overexposed |
| `subjects/<subject>/` | recognised as this subject: a species from `studio/species_africa.txt` (`lion`, `zebra`, `African elephant`…), or `people`, `views`, `other`, `other animals` |
| `groups/<any name>/` | one burst: its photos form one group, without photos of other folders (grouped with the app's default settings) |

A failing test names the photo and shows what the app measured (sharpness, brightness, the
subject's blur...).

### No dataset yet: a fake one is made

Datasets are not part of the repository (photos are big and personal). When the tests run with
`--dataset` and the folder does not exist, they first make a **fake dataset** there, without any
photo of yours (about a minute). To make one yourself:

```
python tests/make_dataset.py fake                  in tests/dataset
python tests/make_dataset.py fake D:/my_dataset    somewhere else
```

It draws two good photos, a landscape and a close-up of pebbles on sand (and a landscape for
`subjects/views/`), and makes **fake photos** from them whose answer is known because they were
made that way: blurred, too dark, burnt out, soft, a burst of each, and a black and a white photo.

### Adding your own photos

Copy photos into the folders of the answers you expect, then run the tests again. Or start an
empty dataset and copy them in shrunk (2400 pixels, keeping the date they were taken, which
bursts need):

```
python tests/make_dataset.py new D:/my_dataset
python tests/make_dataset.py add D:/my_dataset/quality/good a.jpg b.jpg
python tests/make_dataset.py add D:/my_dataset/subjects/zebra zebra.jpg
python tests/make_dataset.py fakes D:/my_dataset      fake photos from your good photos
python -m pytest tests --dataset=D:/my_dataset
```

- Real photos are what a drawing cannot be: animals and people (`subjects/`), and photos out of
  focus (`fakes` blurs only the animal or person of your good photos, found with the app's
  subject detector).
- Only image files are read (JPEG, PNG…): camera RAW files (`.CR2`) are skipped.
- A photo belongs in one folder only: the app gives one answer.

### How the fakes are made

From every photo in `quality/good/`, `fakes` makes a blurred, a shaken (the camera moved), a too
dark and a burnt-out version, a burst of 2 photos, and either a soft version (photos without an
animal or person; blurring an animal makes it "out of focus") or an out-of-focus one. Each change
starts mild and gets stronger until the app really sees the problem in that photo (one photo
needs more darkening than another); if no strength works, the fake is skipped and the reason is
printed. For example, a drawing never looks shaken to the image model, and a calm landscape counts
as blurry before it counts as soft. Making fakes again replaces only the `fake_*` files.

Because each fake is checked with the app when it is made, the fakes pass at first: they protect
against later changes to the app's rules. **Real photos test the app's judgement.**
