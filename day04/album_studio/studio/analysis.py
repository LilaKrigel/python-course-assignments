"""Reading a photo folder once: dates, quality, CLIP embeddings and thumbnails.

Every step of the album works on these results. They are cached in
<photo folder>/.album_studio/, so a folder is only analysed the first time it is opened.
"""
import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"}
STUDIO_DIR = ".album_studio"
OLD_CACHE = ".album_cache.npz"  # written by the earlier album_picker.py; reused if present
ANALYSIS_SIZE = 1024  # photos are resized to this long side before measuring them
THUMB_SIZE = 480
BATCH_SIZE = 16
# Checked on 2000 real trip photos: below 15 every photo was clearly blurry; above it, even
# low-detail landscapes (sky, plains) were fine.
BLURRY_BELOW = 15
# Motion blur (shaken camera, running animals) leaves streaks that look like sharp edges, so
# the image model judges it instead: how much more a photo looks "blurry" than "sharp".
# Checked on the same photos: above 0.05 every photo was blurry.
LOOKS_BLURRY_ABOVE = 0.05
# Both measures a little off together: a smeared serval the detector did not even recognise.
# Above 70 sharpness this also caught a good panning shot of a running zebra.
SOFT_BELOW = 70
LOOKS_SOFT_ABOVE = 0.03
BLURRY_PROMPTS = ["a blurry photo", "a photo with motion blur", "an out of focus photo",
                  "a shaky, smeared photo taken from a moving car"]
SHARP_PROMPTS = ["a sharp photo", "a sharp, in focus photo", "a crisp, clear photo"]
BLANK_ABOVE = 0.9  # more than 90% pure black/white pixels: lens cap, badly over/under-exposed
# Overexposed: a large flat, pale area (burnt-out sky) AND the rest nearly without colour.
# A pale sky alone is fine: birds against a grey sky had rest colour 9.3-12.3, the burnt
# leopard photos 5.5-8.0. Pale but textured areas (sand, water) do not count as sky.
OVEREXPOSED_PALE = 0.2
OVEREXPOSED_COLOUR = 9
# Too dark: even the brightest parts (95th percentile brightness, 0-255) are dark. The 5 darkest
# trip photos were at most 39; dim but usable ones (dusk, shade) started at 55.
TOO_DARK_BELOW = 50
# Out of focus: the camera focused on the background (sharp grass) instead of the animal. The
# largest animal or person is outlined (Mask R-CNN) and only its pixels are measured with the
# re-blur metric of Crete et al. (2007): 0 = sharp .. 1 = blurry.
# The limit depends on the subject's share of the photo: (smallest share, blur limit). Chosen on
# the trip photos: above it nearly all subjects were clearly soft. Large sharp zebras (big flat
# stripes) reached 0.595, small distant animals look softer anyway. Mildly soft subjects score
# like sharp ones and are not caught.
FOCUS_LIMITS = [(0.05, 0.60), (0.01, 0.52), (0.0, 0.64)]
SOFT_TILE = 128  # tile size (pixels at half size) for the softness measure
# Looks soft when seen large: shown as a hint in step 2, never hidden. Checked on close-ups of the
# 2046 trip photos: up to 0.40 they were sharp, above 0.44 most were clearly soft (the blurred
# warthogs _MG_1170/1171: 0.463/0.448). 26 photos are above it. Close-ups of zebras can score high
# while sharp (wide smooth stripes have little fine detail), so it is a hint only.
SOFT_ABOVE = 0.44
FIELDS = ["embedding", "sharpness", "clipped", "pixels", "taken", "pale_flat", "rest_colour", "brightest",
          "blur"]
# Slow to measure (focus about 2 s per photo, softness 0.35 s), so saved while still incomplete;
# NOT_CHECKED marks the rest
SLOW_FIELDS = ["subject_area", "subject_blur", "softness"]
NOT_CHECKED = -1.0

# The large model is much better at telling similar animals apart than ViT-B-32
MODEL_NAME = "ViT-L-14"
MODEL_WEIGHTS = "datacomp_xl_s13b_b90k"

try:  # iPhone photos are often HEIC; Pillow reads them only with this plugin
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    IMAGE_EXTS -= {".heic", ".heif"}


class Library:
    """All photos of a folder with their analysis results, in the order they were taken."""

    def __init__(self, folder, keys, data, broken=()):
        order = np.argsort(data["taken"], kind="stable")
        self.folder = folder
        self.broken = list(broken)  # files that could not be opened (damaged or not photos)
        self.keys = [keys[i] for i in order]
        self.files = [k.split("|")[0] for k in self.keys]  # path relative to the folder
        for field in FIELDS + SLOW_FIELDS:
            setattr(self, field, data[field][order])
        # Quality 0..1: sharpness matters most, resolution second, blown-out areas cost points
        self.quality = (0.7 * rank01(np.log1p(self.sharpness)) + 0.3 * rank01(self.pixels)
                        - np.maximum(0, self.clipped - 0.1))

    def __len__(self):
        return len(self.keys)

    def path(self, i):
        return self.folder / self.files[i]

    def thumb_path(self, i):
        return thumb_path(self.folder, self.keys[i])

    def is_soft(self, i):
        """The photo looks soft when seen large (a hint; soft photos are not hidden)."""
        return bool(self.softness[i] > SOFT_ABOVE)  # NaN and NOT_CHECKED (-1) never are

    def problem(self, i):
        """Why photo i is not worth showing: "blank", "dark", "blurry", "unfocused", "overexposed",
        or "" if it is fine."""
        if self.clipped[i] > BLANK_ABOVE:
            return "blank"
        if self.brightest[i] < TOO_DARK_BELOW:  # before blurry: dark photos also measure as unsharp
            return "dark"
        if (self.sharpness[i] < BLURRY_BELOW or self.blur[i] > LOOKS_BLURRY_ABOVE
                or self.sharpness[i] < SOFT_BELOW and self.blur[i] > LOOKS_SOFT_ABOVE):
            return "blurry"
        limit = next(limit for share, limit in FOCUS_LIMITS if self.subject_area[i] >= share)
        if self.subject_blur[i] > limit:  # NaN (no animal or person found) is never above
            return "unfocused"
        if self.pale_flat[i] > OVEREXPOSED_PALE and self.rest_colour[i] < OVEREXPOSED_COLOUR:
            return "overexposed"
        return ""

    def photo_info(self, i):
        return {"id": i, "file": self.files[i],
                "taken": datetime.fromtimestamp(self.taken[i]).strftime("%Y-%m-%d %H:%M:%S"),
                "megapixels": round(float(self.pixels[i]) / 1e6, 1),
                "quality": round(float(self.quality[i]), 3),
                "problem": self.problem(i)}


def rank01(values):
    """Rank values to the range 0 (worst) .. 1 (best)."""
    return np.argsort(np.argsort(values)) / max(len(values) - 1, 1)


def find_images(folder):
    paths = []
    for path in sorted(folder.rglob("*")):
        rel_dirs = path.relative_to(folder).parts[:-1]
        if (path.is_file() and path.suffix.lower() in IMAGE_EXTS
                and not path.name.startswith("._")  # macOS metadata, not photos
                and not any(d.startswith((".", "album_")) for d in rel_dirs)):
            paths.append(path)
    return paths


def cache_key(folder, path):
    stat = path.stat()
    return f"{path.relative_to(folder).as_posix()}|{stat.st_size}|{int(stat.st_mtime)}"


def thumb_path(folder, key):
    return folder / STUDIO_DIR / "thumbs" / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".jpg")


def date_taken(img, path):
    exif = img.getexif()
    value = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
    try:
        return datetime.strptime(value.strip("\x00 "), "%Y:%m:%d %H:%M:%S").timestamp()
    except (AttributeError, TypeError, ValueError):
        return path.stat().st_mtime


def load_image(path, size=ANALYSIS_SIZE):
    """Return a small upright RGB copy of the photo, its original pixel count and date taken."""
    with Image.open(path) as img:
        pixels = img.width * img.height
        taken = date_taken(img, path)
        img.draft("RGB", (size, size))  # fast JPEG decoding at reduced size
        small = ImageOps.exif_transpose(img).convert("RGB")
    small.thumbnail((size, size))
    return small, pixels, taken


def quality_metrics(img):
    """Return (sharpness, fraction of pure black/white pixels)."""
    if max(img.size) < ANALYSIS_SIZE:  # upscale small photos so they are judged on the same scale
        scale = ANALYSIS_SIZE / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.BICUBIC)
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    laplacian = (gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
                 - 4 * gray[1:-1, 1:-1])
    # Sharpness of the sharpest tiles, so a sharp animal on a blurred background still scores high
    t = 32
    h, w = (laplacian.shape[0] // t) * t, (laplacian.shape[1] // t) * t
    tiles = laplacian[:h, :w].reshape(h // t, t, w // t, t).var(axis=(1, 3))
    return float(np.percentile(tiles, 90)), float(np.mean((gray < 5) | (gray > 250)))


def exposure_metrics(thumb):
    """Return (fraction of flat, pale pixels, colourfulness of the rest, brightness of the
    brightest parts), measured on the thumbnail (the thresholds above were chosen on thumbnails)."""
    rgb = np.asarray(thumb.convert("RGB"), dtype=np.float32)
    lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    spread = rgb.max(axis=2) - rgb.min(axis=2)  # 0 for grey/white, large for strong colours
    texture = np.full_like(lum, 255)  # mean difference to the 4 neighbours; borders count as textured
    c = lum[1:-1, 1:-1]
    texture[1:-1, 1:-1] = (np.abs(c - lum[:-2, 1:-1]) + np.abs(c - lum[2:, 1:-1])
                           + np.abs(c - lum[1:-1, :-2]) + np.abs(c - lum[1:-1, 2:])) / 4
    pale = (lum > 200) & (spread < 30) & (texture < 2)
    colour = float(spread[~pale].mean()) if (~pale).sum() > 100 else 0.0
    return float(np.mean(pale)), colour, float(np.percentile(lum, 95))


def box_mean9(a, axis):
    """Mean of 9 neighbouring pixels along axis (same size as a, edges repeated)."""
    pad = np.pad(a, [(4, 4) if ax == axis else (0, 0) for ax in range(2)], mode="edge")
    c = np.cumsum(pad, axis=axis, dtype=np.float64)
    c = np.concatenate([np.zeros_like(c.take([0], axis=axis)), c], axis=axis)
    n = c.shape[axis]
    return (c.take(range(9, n), axis=axis) - c.take(range(0, n - 9), axis=axis)) / 9


def reblur(gray, mask):
    """Blur of the masked pixels, 0 (sharp) .. 1 (blurry): blur them on purpose and see how much
    of the detail is lost. A sharp photo loses a lot, a blurry one hardly anything (Crete et al. 2007)."""
    result = []
    for axis in (0, 1):
        detail = np.abs(np.diff(gray, axis=axis))
        left = np.abs(np.diff(box_mean9(gray, axis), axis=axis))
        m = mask[1:, :] if axis == 0 else mask[:, 1:]
        total = detail[m].sum()
        lost = np.maximum(0, detail - left)[m].sum()
        result.append((total - lost) / total if total > 0 else 1.0)
    return max(result)


def softness_metric(path):
    """How soft the sharpest parts of the photo are, 0 (sharp) .. 1 (blurry), measured at half
    size. At the 1024-pixel size of the other checks a slightly soft photo still looks sharp (a
    blur a few pixels wide disappears), and at full size camera noise looks like detail.
    The photo is cut into tiles; flat tiles (sky, water) are skipped, and the sharpest 10% count."""
    with Image.open(path) as img:
        img.draft("L", (img.width // 2, img.height // 2))  # JPEG: decoded at half size directly
        gray = img.convert("L")
        if max(gray.size) > 2900:  # not a JPEG (no draft): halve it here
            gray = gray.reduce(2)
        gray = np.asarray(gray, dtype=np.float32)
    t = SOFT_TILE
    h, w = (gray.shape[0] // t) * t, (gray.shape[1] // t) * t
    if not h or not w:
        return np.nan
    gray = gray[:h, :w]

    def per_tile(a):
        return a.reshape(h // t, t, w // t, t).sum(axis=(1, 3))

    kept = []
    for axis in (0, 1):  # the re-blur measure (see reblur()), for every tile at once
        detail = np.abs(np.diff(gray, axis=axis))
        left = np.abs(np.diff(box_mean9(gray, axis), axis=axis))
        pad = [(0, 1), (0, 0)] if axis == 0 else [(0, 0), (0, 1)]
        total, lost = per_tile(np.pad(detail, pad)), per_tile(np.pad(np.maximum(0, detail - left), pad))
        kept.append((total - lost) / np.maximum(total, 1e-6))
    tile_blur = np.maximum(*kept)
    textured = gray.reshape(h // t, t, w // t, t).std(axis=(1, 3)) > 8
    return float(np.percentile(tile_blur[textured], 10)) if textured.any() else np.nan


def focus_metrics(img, mask):
    """Return (share of the photo covered by the subject, blur of the subject or NaN)."""
    if mask is None:
        return 0.0, np.nan
    inner = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(5))
    inner = np.asarray(inner) > 127  # without its outline, where the background shows through
    if inner.sum() < 400:
        return float(mask.mean()), np.nan
    return float(mask.mean()), reblur(np.asarray(img.convert("L"), dtype=np.float32), inner)


def save_thumb(img, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    thumb = img.copy()
    thumb.thumbnail((THUMB_SIZE, THUMB_SIZE))
    thumb.save(path, quality=82)


class Clip:
    """The CLIP image/text model, loaded on first use (it takes a few seconds)."""
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # harmless notice on Windows
        import open_clip
        import torch
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=MODEL_WEIGHTS)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(MODEL_NAME)

    def embed_images(self, images):
        with self.torch.no_grad():
            emb = self.model.encode_image(self.torch.stack([self.preprocess(im) for im in images]))
        return normalize(emb.numpy())

    def embed_text(self, prompts):
        """One embedding for a class described by one or more prompts."""
        with self.torch.no_grad():
            emb = normalize(self.model.encode_text(self.tokenizer(prompts)).numpy())
        return normalize(emb.mean(axis=0, keepdims=True))[0]

    def embed_prompts(self, prompts):
        """One embedding per prompt (rows), e.g. to cache them one by one."""
        with self.torch.no_grad():
            return normalize(self.model.encode_text(self.tokenizer(prompts)).numpy())

    def blur_scores(self, embeddings):
        """How much more each photo looks blurry than sharp (compared with LOOKS_BLURRY_ABOVE)."""
        return embeddings @ (self.embed_text(BLURRY_PROMPTS) - self.embed_text(SHARP_PROMPTS))


class Subjects:
    """Finds the outline of the main animal or person (Mask R-CNN), loaded on first use."""
    _instance = None
    # COCO classes: person, bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe
    LIVING = {1, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25}

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        import torch
        from torchvision.models.detection import MaskRCNN_ResNet50_FPN_V2_Weights, maskrcnn_resnet50_fpn_v2
        from torchvision.transforms.functional import to_tensor
        self.torch, self.to_tensor = torch, to_tensor
        self.model = maskrcnn_resnet50_fpn_v2(weights=MaskRCNN_ResNet50_FPN_V2_Weights.DEFAULT,
                                              box_score_thresh=0.6, min_size=512, max_size=768).eval()

    def main_subject(self, img):
        """Mask (True on the subject) of the largest animal or person in img, or None."""
        with self.torch.no_grad():
            det = self.model([self.to_tensor(img)])[0]
        masks = [m[0].numpy() > 0.5 for m, label in zip(det["masks"], det["labels"]) if int(label) in self.LIVING]
        return max(masks, key=np.sum) if masks else None


def normalize(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def load_cache(folder):
    cached = {}
    for cache_file in (folder / STUDIO_DIR / "analysis.npz", folder / OLD_CACHE):
        if cache_file.exists():
            data = np.load(cache_file)
            if str(data["model"]) == MODEL_NAME:
                # read each array once, not once per photo; older caches lack some fields
                arrays = {f: data[f] for f in FIELDS + SLOW_FIELDS if f in data.files}
                for i, key in enumerate(data["keys"]):
                    cached[str(key)] = {f: values[i] for f, values in arrays.items()
                                        if not (f in SLOW_FIELDS and values[i] == NOT_CHECKED)}
                return cached
    return cached


def save_cache(folder, cached):
    (folder / STUDIO_DIR).mkdir(exist_ok=True)
    keys = [k for k in cached if all(f in cached[k] for f in FIELDS)]
    np.savez(folder / STUDIO_DIR / "analysis.npz", model=MODEL_NAME, keys=np.array(keys),
             **{f: np.array([cached[k][f] for k in keys]) for f in FIELDS},
             **{f: np.array([cached[k].get(f, NOT_CHECKED) for k in keys]) for f in SLOW_FIELDS})


def analyse(folder, progress):
    """Analyse all photos in folder (using the cache) and return a Library.

    progress(done, total, message) is called regularly so the UI can show a progress bar."""
    progress(0, 0, "Looking for photos...")
    paths = find_images(folder)
    keys = [cache_key(folder, p) for p in paths]
    cached = load_cache(folder)
    todo = [i for i, k in enumerate(keys) if k not in cached or not thumb_path(folder, k).exists()]
    started = time.time()
    clip = None
    broken = []
    for start in range(0, len(todo), BATCH_SIZE):
        images, batch = [], []
        for i in todo[start:start + BATCH_SIZE]:
            try:
                img, pixels, taken = load_image(paths[i])
            except Exception:  # damaged file: leave it out, but tell the user
                broken.append(paths[i].relative_to(folder).as_posix())
                continue
            save_thumb(img, thumb_path(folder, keys[i]))
            if keys[i] not in cached:
                sharpness, clipped = quality_metrics(img)
                images.append(img)
                batch.append((i, sharpness, clipped, pixels, taken))
        if images:
            if clip is None:
                progress(start, len(todo), "Loading the image model...")
                clip = Clip.get()
            for (i, sharpness, clipped, pixels, taken), emb in zip(batch, clip.embed_images(images)):
                cached[keys[i]] = {"embedding": emb, "sharpness": sharpness, "clipped": clipped,
                                   "pixels": pixels, "taken": taken}
        done = min(start + BATCH_SIZE, len(todo))
        progress(done, len(todo), f"Reading photos ({done} of {len(todo)})", started)

    # Exposure is measured on the thumbnails (also for photos analysed by an older version)
    missing = [k for k in keys if k in cached and "brightest" not in cached[k]]
    started = time.time()
    for n, key in enumerate(missing):
        with Image.open(thumb_path(folder, key)) as thumb:
            cached[key]["pale_flat"], cached[key]["rest_colour"], cached[key]["brightest"] = exposure_metrics(thumb)
        if n % 50 == 0:
            progress(n, len(missing), f"Checking exposure ({n} of {len(missing)})", started)

    # The blur score comes from the embeddings (also for photos analysed by an older version)
    no_blur = [k for k in keys if k in cached and "blur" not in cached[k]]
    if no_blur:
        progress(0, 0, "Checking for blur...")
        clip = clip or Clip.get()
        scores = clip.blur_scores(np.array([cached[k]["embedding"] for k in no_blur]))
        for key, score in zip(no_blur, scores):
            cached[key]["blur"] = score

    if todo or missing or no_blur:
        save_cache(folder, cached)

    # Focus on the main animal or person, and softness at half size; slow, so they are saved
    # regularly and continue where they stopped if the app is closed
    no_focus = [i for i, k in enumerate(keys) if k in cached and "subject_blur" not in cached[k]]
    started = time.time()
    for n, i in enumerate(no_focus):
        if n == 0:
            progress(0, len(no_focus), "Loading the subject detector...")
        img, _, _ = load_image(paths[i])
        cached[keys[i]]["subject_area"], cached[keys[i]]["subject_blur"] = \
            focus_metrics(img, Subjects.get().main_subject(img))
        progress(n + 1, len(no_focus), f"Checking focus ({n + 1} of {len(no_focus)})", started)
        if (n + 1) % 100 == 0 or n + 1 == len(no_focus):
            save_cache(folder, cached)
    no_soft = [i for i, k in enumerate(keys) if k in cached and "softness" not in cached[k]]
    started = time.time()
    for n, i in enumerate(no_soft):
        try:
            cached[keys[i]]["softness"] = softness_metric(paths[i])
        except Exception:  # not readable at full size: not measured (never flagged)
            cached[keys[i]]["softness"] = np.nan
        progress(n + 1, len(no_soft), f"Checking sharpness in detail ({n + 1} of {len(no_soft)})", started)
        if (n + 1) % 200 == 0 or n + 1 == len(no_soft):
            save_cache(folder, cached)

    ok = [k for k in keys if k in cached]
    return Library(folder, ok, {f: np.array([cached[k][f] for k in ok]) for f in FIELDS + SLOW_FIELDS}, broken)
