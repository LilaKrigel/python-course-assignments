"""Make a photo dataset for test_dataset.py: folders named after the answer the app must give.

    python tests/make_dataset.py fake [FOLDER]
        A whole fake dataset, without any photo of yours: drawn landscapes as the good photos, and
        fake photos made from them. Without FOLDER: tests/dataset. The tests do this by themselves
        when the dataset does not exist yet.
    python tests/make_dataset.py new FOLDER
        An empty dataset: all the folders, and a short guide (HOW_TO.txt).
    python tests/make_dataset.py add FOLDER/quality/good photo.jpg [photo.jpg ...]
        Copy photos into a folder of the dataset, shrunk to 2400 pixels, keeping the date they were
        taken (bursts are grouped by time). Copying them by hand works too.
    python tests/make_dataset.py fakes [FOLDER]
        Make fake photos from the good photos in FOLDER/quality/good (yours, or drawn ones): blurred,
        shaken, too dark, burnt out, soft, out of focus, and a burst. Without FOLDER: tests/dataset.

Then test the app with it:
    python -m pytest tests --dataset=FOLDER

Making fakes loads the app's image model and subject detector (a minute the first time).
For each kind, the change starts mild and gets stronger until the app really sees the problem
in that photo (a dark photo with a bright window needs more darkening, for example); if no
strength works, the fake is skipped and the reason printed. The fakes are named fake_*.jpg, and
making them again replaces only those files.
"""
import argparse
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from studio import analysis  # noqa: E402

DEFAULT_DATASET = Path(__file__).resolve().parent / "dataset"  # not in the repository: made on each computer
LONG_SIDE = 2400  # big enough for the softness check (half size), small enough to keep
QUALITY_FOLDERS = ["good", "soft", "blurry", "unfocused", "too_dark", "blank", "overexposed"]
HOW_TO = """This folder is a photo dataset for testing Album Studio.

The folder a photo is in is the answer the app must give:
  quality/good          a good photo: shown, not marked soft
  quality/soft          shown, but marked "soft" (looks soft when seen large)
  quality/blurry        hidden as blurry
  quality/unfocused     hidden as out of focus (the animal or person is soft, the background sharp)
  quality/too_dark      hidden as too dark
  quality/blank         hidden as blank (almost all black or white)
  quality/overexposed   hidden as overexposed
  subjects/<subject>    recognised as this subject: a species from studio/species_africa.txt
                        (e.g. "lion", "African elephant"), or people, views, other, other animals
  groups/<any name>     the photos of one burst: they must form one group, alone

1. Put photos into the folders (copy them, or: python tests/make_dataset.py add FOLDER/... photos).
   A photo belongs in one folder only. Only image files are read (JPEG, PNG...), not RAW files.
2. Make fake photos from your good photos (optional):  python tests/make_dataset.py fakes FOLDER
3. Test:  python -m pytest tests --dataset=FOLDER
"""


# ---------- new, add ----------

def new(folder):
    folder = Path(folder)
    for name in QUALITY_FOLDERS:
        (folder / "quality" / name).mkdir(parents=True, exist_ok=True)
    (folder / "subjects").mkdir(exist_ok=True)
    (folder / "groups").mkdir(exist_ok=True)
    (folder / "HOW_TO.txt").write_text(HOW_TO, encoding="utf-8")
    print(f"New dataset in {folder}. Next: put photos into its folders (see HOW_TO.txt).")


def add(target, photos):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for photo in photos:
        with Image.open(photo) as img:
            exif = img.info.get("exif", b"")  # the date it was taken, for grouping bursts
            small = ImageOps.exif_transpose(img).convert("RGB")
        small.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
        small.save(target / (Path(photo).stem + ".jpg"), quality=85, exif=exif)
        print("added", target / (Path(photo).stem + ".jpg"))


# ---------- A whole fake dataset, from drawn photos ----------

def landscape(seed, sunset=False, size=(LONG_SIDE, LONG_SIDE * 2 // 3)):
    """A drawn landscape: sky, distant hills, a textured field with grass and bushes. Sharp edges
    and fine detail below the sky, like a photo; the image model sees it as a view."""
    from PIL import ImageDraw
    rng = np.random.default_rng(seed)
    w, h = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    top, bottom = ((250, 140, 60), (255, 210, 120)) if sunset else ((70, 130, 210), (190, 215, 240))
    for y in range(int(h * 0.45)):  # sky: a smooth gradient
        t = y / (h * 0.45)
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    hills = [(x, int(h * 0.42 + h * 0.03 * np.sin(x / (w / 11) + seed))) for x in range(0, w + 40, 40)]
    draw.polygon(hills + [(w, h), (0, h)], fill=(70, 60, 80) if sunset else (90, 120, 80))
    patches = rng.integers(0, 256, (h // 8, w // 8, 3)).astype(int)  # grass: 8-pixel patches
    base = np.array([120, 90, 40] if sunset else [110, 150, 60])
    grass = Image.fromarray(np.clip(base + (patches - 128) * 0.45, 0, 255).astype(np.uint8)).resize(size, Image.NEAREST)
    field = Image.new("L", size, 0)
    ImageDraw.Draw(field).rectangle([0, int(h * 0.55), w, h], fill=255)
    img.paste(grass, (0, 0), field)
    for _ in range(25):  # bushes and stones: dark shapes with sharp outlines
        x, y, r = int(rng.integers(0, w)), int(rng.integers(int(h * 0.58), h)), int(rng.integers(w // 100, w // 27))
        draw.ellipse([x - r, y - r // 2, x + r, y + r // 2], fill=tuple(int(c) for c in rng.integers(20, 70, 3)))
    return img


def pebbles(seed, size=(LONG_SIDE, LONG_SIDE * 2 // 3)):
    """A drawn close-up of pebbles on sand: a different kind of scene than a landscape (to the
    image model they are only 0.72 alike), so their bursts are separate groups."""
    from PIL import ImageDraw
    rng = np.random.default_rng(seed)
    w, h = size
    sand = np.clip(np.array([194, 170, 130]) + rng.normal(0, 18, (h // 4, w // 4, 1)), 0, 255).astype(np.uint8)
    img = Image.blend(Image.fromarray(sand).resize(size, Image.NEAREST), Image.new("RGB", size, (194, 170, 130)), 0.4)
    draw = ImageDraw.Draw(img)
    for _ in range(140):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        rx, ry = int(rng.integers(w // 80, w // 20)), int(rng.integers(w // 120, w // 27))
        tone = int(rng.integers(70, 200))
        colour = (tone + int(rng.integers(-15, 25)), tone + int(rng.integers(-15, 15)), tone - int(rng.integers(0, 30)))
        draw.ellipse([x - rx, y - ry, x + rx, y + ry], fill=colour, outline=(40, 35, 30), width=3)
        draw.ellipse([x - rx // 2, y - ry // 1.6, x, y - ry // 3], fill=tuple(min(255, c + 35) for c in colour))  # light on top
    return img


DRAWN = {  # the drawn photos of a fake dataset (named drawn_*, not fake_*: fakes are made from them)
    "quality/good/drawn_meadow.jpg": lambda: landscape(1),
    "quality/good/drawn_pebbles.jpg": lambda: pebbles(3),
    "subjects/views/drawn_hills.jpg": lambda: landscape(6),
}


def fake(folder):
    """A whole fake dataset in a new folder: drawn good photos, and the fakes made from them.
    A drawing cannot show a real animal or person, so subjects other than views, and out of focus,
    stay empty: real photos can be added there."""
    folder = Path(folder)
    new(folder)
    for name, draw in DRAWN.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        draw().save(folder / name, quality=88)
        print("drew", name)
    fakes(folder)


def ensure(folder):
    """The dataset in folder, made as a fake dataset first if it does not exist yet."""
    folder = Path(folder)
    if not folder.exists():
        print(f"\nNo photo dataset in {folder} yet: making a fake one (about a minute)...")
        fake(folder)
    return folder


# ---------- What the app says about one photo ----------

def analyse_one(path):
    """A one-photo Library, measured exactly as analysis.analyse() measures every photo."""
    img, pixels, taken = analysis.load_image(path)
    sharpness, clipped = analysis.quality_metrics(img)
    thumb = img.copy()
    thumb.thumbnail((analysis.THUMB_SIZE, analysis.THUMB_SIZE))
    buf = io.BytesIO()
    thumb.save(buf, "JPEG", quality=82)  # exposure is measured on the saved thumbnail
    pale, colour, brightest, middle = analysis.exposure_metrics(Image.open(buf))
    clip = analysis.Clip.get()
    embedding = clip.embed_images([img])
    area, subject_blur = analysis.focus_metrics(img, analysis.Subjects.get().main_subject(img))
    values = {"embedding": embedding, "sharpness": sharpness, "clipped": clipped, "pixels": pixels,
              "taken": taken, "pale_flat": pale, "rest_colour": colour, "brightest": brightest,
              "middle_brightness": middle,
              "blur": clip.blur_scores(embedding)[0], "subject_area": area, "subject_blur": subject_blur,
              "softness": analysis.softness_metric(path)}
    return analysis.Library(Path(path).parent, [f"{Path(path).name}|0|0"],
                            {k: np.array(v if k == "embedding" else [v]) for k, v in values.items()})


def verdict(path):
    """The app's answer for one photo, as the dataset's folders name it."""
    lib = analyse_one(path)
    return "soft" if lib.problem(0) == "" and lib.is_soft(0) else lib.problem(0) or "good"


# ---------- The changes ----------

def blurred(img, radius):
    return img.filter(ImageFilter.GaussianBlur(radius))


def shaken(img, length):
    """The camera moved sideways during the photo: each pixel smeared over `length` pixels."""
    a = np.asarray(img, dtype=np.float32)
    pad = np.pad(a, ((0, 0), (length // 2, length - length // 2), (0, 0)), mode="edge")
    c = np.concatenate([np.zeros_like(pad[:, :1]), np.cumsum(pad, axis=1)], axis=1)
    return Image.fromarray(((c[:, length:] - c[:, :-length]) / length)[:, :a.shape[1]].astype(np.uint8))


def darkened(img, factor):
    return Image.eval(img, lambda v: int(v * factor))


def burnt_out(img, gain):
    """Much too bright: the bright parts turn into flat pale areas (clipped at a pale grey, as a
    camera's JPEG does) and the colours are almost gone."""
    faded = Image.blend(img.convert("L").convert("RGB"), img, 0.06)
    return Image.eval(faded, lambda v: min(238, int(v * gain)))


def subject_mask(img):
    """Where the animal or person is (the app's subject detector), at the photo's size, or None."""
    small = img.copy()
    small.thumbnail((analysis.ANALYSIS_SIZE, analysis.ANALYSIS_SIZE))
    mask = analysis.Subjects.get().main_subject(small)
    if mask is None or mask.mean() < 0.01:
        return None
    return Image.fromarray(mask.astype(np.uint8) * 255).resize(img.size).filter(ImageFilter.MaxFilter(9))


def out_of_focus(img, radius):
    """The camera focused on the background: only the animal or person is blurred."""
    mask = subject_mask(img)
    return Image.composite(blurred(img, radius), img, mask.filter(ImageFilter.GaussianBlur(radius / 1.5)))


def crop_shift(img, dx, dy):
    """The same scene, the camera moved a little: a photo of a burst."""
    w, h = img.size
    return img.crop((30 + dx, 30 + dy, w - 30 + dx, h - 30 + dy)).resize(img.size)


# kind -> (folder, the answer it must get, the change, strengths from mild to strong, needs a subject?)
KINDS = {
    "blurred": ("blurry", "blurry", blurred, [12, 20, 35], None),
    "shaken": ("blurry", "blurry", shaken, [40, 70, 110], None),
    "dark": ("too_dark", "dark", darkened, [0.15, 0.1, 0.06, 0.03], None),
    "burnt": ("overexposed", "overexposed", burnt_out, [1.9, 2.4, 3.0, 3.8], None),
    "soft": ("soft", "soft", blurred, [1.5, 2, 2.5, 3, 3.5, 4], False),  # an animal would be "out of focus"
    "unfocused": ("unfocused", "unfocused", out_of_focus, [6, 9, 14, 20], True),
}


def fakes(folder):
    folder = Path(folder)
    sources = [p for p in analysis.find_images(folder / "quality" / "good") if not p.name.startswith("fake_")]
    if not sources:
        sys.exit(f"No photos in {folder / 'quality' / 'good'}: put a few good photos there first.")
    for old in folder.glob("**/fake_*.jpg"):  # only the fakes made before; nothing else is touched
        old.unlink()
    for d in sorted(folder.glob("groups/fake_burst_*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    print("Loading the image model and the subject detector...")
    for source in sources:
        name = source.stem.removeprefix("base_")
        img = Image.open(source).convert("RGB")
        has_subject = subject_mask(img) is not None
        print(f"\n{source.relative_to(folder)}: {'an animal or person found' if has_subject else 'no animal or person'}")
        for kind, (target, answer, change, strengths, needs_subject) in KINDS.items():
            if needs_subject is not None and needs_subject != has_subject:
                continue
            path = folder / "quality" / target / f"fake_{kind}_{name}.jpg"
            for strength in strengths:
                change(img, strength).save(path, quality=85)
                got = verdict(path)
                if got == answer:
                    print(f"  made {path.relative_to(folder)} (strength {strength})")
                    break
            else:
                path.unlink()
                print(f"  skipped {kind}: the app said {got!r}, not {answer!r}, even at the strongest")
        burst = folder / "groups" / f"fake_burst_{name}"
        burst.mkdir(parents=True, exist_ok=True)
        for n, (dx, dy) in enumerate([(0, 0), (20, 8)], 1):
            crop_shift(img, dx, dy).save(burst / f"fake_{n}.jpg", quality=85)
        print(f"  made {burst.relative_to(folder)}/ (2 photos)")
    for kind, colour in (("black", 0), ("white", 255)):
        path = folder / "quality" / "blank" / f"fake_{kind}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1600, 1067), (colour,) * 3).save(path, quality=85)
    print("\nmade quality/blank/fake_black.jpg and fake_white.jpg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fake", help="a whole fake dataset, from drawn photos").add_argument(
        "folder", nargs="?", default=DEFAULT_DATASET)
    commands.add_parser("new", help="an empty dataset").add_argument("folder")
    p = commands.add_parser("add", help="copy photos into a folder of the dataset, shrunk")
    p.add_argument("target")
    p.add_argument("photos", nargs="+")
    commands.add_parser("fakes", help="fake photos from quality/good").add_argument("folder", nargs="?", default=DEFAULT_DATASET)
    args = parser.parse_args()
    {"fake": lambda: fake(args.folder), "new": lambda: new(args.folder), "add": lambda: add(args.target, args.photos),
     "fakes": lambda: fakes(args.folder)}[args.command]()
