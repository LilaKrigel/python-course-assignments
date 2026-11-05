"""Pick the best photos from a folder and copy them into an album subfolder.

How it works:
  1. Measure the quality of every photo (sharpness, resolution, exposure).
  2. Group near-duplicates (burst shots, re-sent copies) and keep only the best one.
  3. Describe every photo with CLIP (a local image/text AI model): is it animals,
     people, landscapes or your own free text, and which animal species it shows.
  4. Choose N photos for the requested focus: one photo of every species first,
     then the best remaining photos, skipping photos that look too much alike.
  5. Copy them, in the order they were taken, into a subfolder with a CSV report.

Examples:
  python album_picker.py "D:/Photos/Africa 2026" -n 60 --focus animals people
  python album_picker.py "D:/Photos/Africa 2026" -n 30 --focus landscapes:2 people:1
  python album_picker.py "D:/Photos/Africa 2026" -n 20 --focus "sunset" "elephants"
"""
import argparse
import csv
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"}
CACHE_NAME = ".album_cache.npz"
OUTPUT_PREFIX = "album_"
ANALYSIS_SIZE = 1024  # photos are resized to this long side before measuring them
BATCH_SIZE = 32

# The large model is much better at telling similar animals apart (lion cub vs. warthog);
# "ViT-B-32" / "laion2b_s34b_b79k" is ~15x faster but mislabels many species.
MODEL_NAME = "ViT-L-14"
MODEL_WEIGHTS = "datacomp_xl_s13b_b90k"

# Built-in focus categories. Any other word given to --focus is used as free text.
FOCUS_PROMPTS = {
    "animals": ["a photo of a wild animal", "a photo of a bird", "a photo of animals in the grass"],
    "people": ["a photo of people", "a selfie", "a portrait of a person", "a group photo of friends on a trip",
               "a photo of a person sitting in a car", "a photo of people looking through binoculars"],
    "landscapes": ["a landscape photo", "a photo of scenery", "a photo of a sunset",
                   "a view of the savanna", "a photo of mountains"],
}
FOCUS_ALIASES = {"animal": "animals", "wildlife": "animals", "us": "people", "person": "people",
                 "view": "landscapes", "views": "landscapes", "landscape": "landscapes", "scenery": "landscapes"}
# Catch-all class so photos of food, cars, screenshots etc. are not forced into a focus.
OTHER_PROMPTS = ["a photo of food", "a photo of a car", "a photo of safari jeeps", "a photo of a building",
                 "a photo of a hotel room", "a photo of a pet cat or dog at home", "a screenshot",
                 "a photo of a document"]
# Fallback classes: an animal that matches these better than any listed species gets no species name,
# so it is not forced into the wrong one.
UNKNOWN_SPECIES_PROMPTS = ["a photo of a bird", "a photo of an animal", "a photo of grass"]
SPECIES_MIN_CONFIDENCE = 0.5

try:  # iPhone photos are often HEIC; Pillow reads them only with this plugin
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="folder with the photos (subfolders are included)")
    parser.add_argument("-n", "--number", type=int, required=True, help="how many photos to put in the album")
    parser.add_argument("--focus", nargs="+", default=["animals", "people", "landscapes"],
                        help="what to select: animals, people, landscapes or any free text, "
                             "optionally with a weight, e.g. animals:2 people:1 (default: all three equally)")
    parser.add_argument("--species", type=Path, default=Path(__file__).with_name("species_africa.txt"),
                        help="text file with the animal species to recognise, one per line")
    parser.add_argument("--no-species", action="store_true",
                        help="don't try to include one photo of every species")
    parser.add_argument("--duplicate-threshold", type=float, default=0.90,
                        help="how similar (0-1) two photos must be to count as duplicates (default 0.90; "
                             "lower it if duplicates slip through, raise it if different photos get merged)")
    parser.add_argument("--duplicate-seconds", type=float, default=120,
                        help="duplicates must be taken at most this many seconds apart (default 120)")
    parser.add_argument("--min-quality", type=float, default=0.25,
                        help="never pick photos with a quality score (0-1) below this (default 0.25)")
    parser.add_argument("--diversity", type=float, default=0.5,
                        help="how strongly to avoid similar-looking photos in the album (default 0.5)")
    parser.add_argument("--out", type=Path, help="output folder (default: a new album_... subfolder)")
    parser.add_argument("--dry-run", action="store_true", help="only print and report, don't copy photos")
    return parser.parse_args()


def parse_focus(items):
    """Turn ['animals:2', 'people'] into (['animals', 'people'], [2.0, 1.0])."""
    names, weights = [], []
    for item in items:
        name, weight = item, 1.0
        if ":" in item:
            head, tail = item.rsplit(":", 1)
            try:
                name, weight = head, float(tail)
            except ValueError:
                pass
        name = FOCUS_ALIASES.get(name.strip().lower(), name.strip())
        names.append(name)
        weights.append(weight)
    return names, weights


def find_images(folder):
    paths, skipped_heic = [], 0
    for path in sorted(folder.rglob("*")):
        rel_dirs = path.relative_to(folder).parts[:-1]
        if (not path.is_file() or path.name.startswith("._")  # "._" files are macOS metadata, not photos
                or any(d.startswith(OUTPUT_PREFIX) for d in rel_dirs)):
            continue
        ext = path.suffix.lower()
        if ext in (".heic", ".heif") and not HEIC_SUPPORTED:
            skipped_heic += 1
        elif ext in IMAGE_EXTS:
            paths.append(path)
    if skipped_heic:
        print(f"WARNING: skipped {skipped_heic} HEIC photos. Run 'pip install pillow-heif' to include them.")
    return paths


def date_taken(img, path):
    exif = img.getexif()
    value = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
    try:
        return datetime.strptime(value.strip("\x00 "), "%Y:%m:%d %H:%M:%S").timestamp()
    except (AttributeError, TypeError, ValueError):
        return path.stat().st_mtime


def load_image(path):
    """Return a small upright RGB copy of the photo, its original pixel count and date taken."""
    with Image.open(path) as img:
        pixels = img.width * img.height
        taken = date_taken(img, path)
        img.draft("RGB", (ANALYSIS_SIZE, ANALYSIS_SIZE))  # fast JPEG decoding at reduced size
        small = ImageOps.exif_transpose(img).convert("RGB")
    small.thumbnail((ANALYSIS_SIZE, ANALYSIS_SIZE))
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
    sharpness = float(np.percentile(tiles, 90))
    clipped = float(np.mean((gray < 5) | (gray > 250)))
    return sharpness, clipped


class Clip:
    def __init__(self):
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # harmless model-cache notice on Windows
        import open_clip
        import torch
        self.torch = torch
        print(f"Loading CLIP model {MODEL_NAME} (downloaded once on first use)...")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=MODEL_WEIGHTS)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(MODEL_NAME)

    def embed_images(self, images):
        with self.torch.no_grad():
            emb = self.model.encode_image(self.torch.stack([self.preprocess(im) for im in images]))
        return normalize(emb.numpy())

    def embed_class(self, prompts):
        """One embedding for a class described by several prompts."""
        with self.torch.no_grad():
            emb = normalize(self.model.encode_text(self.tokenizer(prompts)).numpy())
        return normalize(emb.mean(axis=0, keepdims=True))[0]


def normalize(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def analyse_photos(folder, paths, clip):
    """Measure every photo, reusing results cached from earlier runs. Returns (paths, data)."""
    fields = ["embedding", "sharpness", "clipped", "pixels", "taken"]
    cache_file = folder / CACHE_NAME
    cached = {}
    if cache_file.exists():
        data = np.load(cache_file)
        if str(data["model"]) == MODEL_NAME:
            for i, key in enumerate(data["keys"]):
                cached[str(key)] = {f: data[f][i] for f in fields}

    def cache_key(path):
        stat = path.stat()
        return f"{path.relative_to(folder).as_posix()}|{stat.st_size}|{int(stat.st_mtime)}"

    keys = [cache_key(p) for p in paths]
    todo = [i for i, key in enumerate(keys) if key not in cached]
    print(f"Found {len(paths)} photos ({len(paths) - len(todo)} already analysed in an earlier run).")
    for start in range(0, len(todo), BATCH_SIZE):
        images, batch = [], []
        for i in todo[start:start + BATCH_SIZE]:
            try:
                img, pixels, taken = load_image(paths[i])
            except Exception as err:
                print(f"  skipping unreadable file {paths[i].name}: {err}")
                continue
            sharpness, clipped = quality_metrics(img)
            images.append(img)
            batch.append((i, sharpness, clipped, pixels, taken))
        if images:
            for (i, sharpness, clipped, pixels, taken), emb in zip(batch, clip.embed_images(images)):
                cached[keys[i]] = {"embedding": emb, "sharpness": sharpness, "clipped": clipped,
                                   "pixels": pixels, "taken": taken}
        print(f"  analysed {min(start + BATCH_SIZE, len(todo))}/{len(todo)}")

    if todo:
        all_keys = list(cached)
        np.savez(cache_file, model=MODEL_NAME, keys=np.array(all_keys),
                 **{f: np.array([cached[k][f] for k in all_keys]) for f in fields})

    ok = [i for i, key in enumerate(keys) if key in cached]
    data = {f: np.array([cached[keys[i]][f] for i in ok]) for f in fields}
    return [paths[i] for i in ok], data


def class_probabilities(embeddings, class_embeddings):
    logits = 100 * embeddings @ np.array(class_embeddings).T
    logits -= logits.max(axis=1, keepdims=True)
    probs = np.exp(logits)
    return probs / probs.sum(axis=1, keepdims=True)


def rank01(values):
    """Rank values to the range 0 (worst) .. 1 (best)."""
    return np.argsort(np.argsort(values)) / max(len(values) - 1, 1)


def group_duplicates(embeddings, taken, threshold, max_gap):
    """Group photos taken in a row (at most max_gap seconds apart) that look like the first
    photo of their group. Returns a group id per photo.

    Comparing with the group's first photo, not just the previous one, stops long chains of
    'each looks a bit like the next' from merging a whole game drive into one group."""
    groups = np.zeros(len(embeddings), dtype=int)
    group, anchor, last_time = -1, None, None
    for i in np.argsort(taken, kind="stable"):
        if anchor is None or taken[i] - last_time > max_gap or embeddings[i] @ embeddings[anchor] < threshold:
            group, anchor = group + 1, i
        groups[i] = group
        last_time = taken[i]
    return groups


def split_quota(n, weights):
    raw = n * np.array(weights) / sum(weights)
    quota = np.floor(raw).astype(int)
    for i in np.argsort(raw - quota)[::-1][:n - quota.sum()]:
        quota[i] += 1
    return quota


def pick_diverse(pool, k, score, embeddings, already_chosen, diversity, labels, too_similar):
    """Greedily pick high-scoring photos, penalising ones similar to photos already picked
    and ones whose label (species or category) is already in the album several times.
    Photos at least too_similar alike to a picked one (same scene, shot later) are skipped."""
    pool, picked = list(pool), []
    while pool and len(picked) < k:
        selected = already_chosen + picked
        penalty = (embeddings[pool] @ embeddings[selected].T).max(axis=1) if selected else np.zeros(len(pool))
        pool = [i for i, sim in zip(pool, penalty) if sim < too_similar]
        penalty = penalty[penalty < too_similar]
        if not pool:
            break
        repeats = Counter(labels[i] for i in selected)
        penalty = penalty + 0.1 * np.array([repeats[labels[i]] for i in pool])
        picked.append(pool.pop(int(np.argmax(score[pool] - diversity * penalty))))
    return picked


def slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()


def main():
    args = parse_args()
    folder = args.folder.resolve()
    if not folder.is_dir():
        sys.exit(f"Folder not found: {folder}")
    focuses, weights = parse_focus(args.focus)
    out = args.out or folder / f"{OUTPUT_PREFIX}{'_'.join(slug(f) for f in focuses)}_{args.number}"
    if out.exists() and any(out.iterdir()) and not args.dry_run:
        sys.exit(f"Output folder {out} already exists and is not empty. Delete it or choose --out.")

    paths = find_images(folder)
    if not paths:
        sys.exit(f"No photos found in {folder}")
    clip = Clip()
    paths, data = analyse_photos(folder, paths, clip)
    emb = data["embedding"]

    # Quality: sharpness matters most, resolution second, blown-out highlights/shadows cost points
    quality = (0.7 * rank01(np.log1p(data["sharpness"])) + 0.3 * rank01(data["pixels"])
               - np.maximum(0, data["clipped"] - 0.1))

    # Near-duplicates: keep only the best-quality photo of each group
    groups = group_duplicates(emb, data["taken"], args.duplicate_threshold, args.duplicate_seconds)
    best_in_group = {}
    for i, g in enumerate(groups):
        if g not in best_in_group or quality[i] > quality[best_in_group[g]]:
            best_in_group[g] = i
    reps = sorted(best_in_group.values())
    print(f"{len(paths)} photos -> {len(reps)} after removing near-duplicates.")
    reps = [i for i in reps if quality[i] >= args.min_quality]
    print(f"{len(reps)} of them are sharp enough (quality >= {args.min_quality}).")

    # Content: what each photo shows
    class_names = list(FOCUS_PROMPTS) + ["other"]
    class_probs = class_probabilities(emb, [clip.embed_class(FOCUS_PROMPTS[c]) for c in FOCUS_PROMPTS]
                                      + [clip.embed_class(OTHER_PROMPTS)])
    category = np.array(class_names)[class_probs.argmax(axis=1)]
    relevance, in_focus = {}, {}
    for focus in focuses:
        if focus in FOCUS_PROMPTS:
            relevance[focus] = class_probs[:, class_names.index(focus)]
            in_focus[focus] = category == focus
        else:  # free text: does the photo match it better than a generic photo?
            relevance[focus] = class_probabilities(
                emb, [clip.embed_class([f"a photo of {focus}"]), clip.embed_class(["a photo"])])[:, 0]
            in_focus[focus] = relevance[focus] >= 0.5

    species = np.full(len(paths), "", dtype=object)
    species_conf = np.zeros(len(paths))
    use_species = "animals" in focuses and not args.no_species
    if use_species:
        names = [line.strip() for line in args.species.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]
        probs = class_probabilities(emb, [clip.embed_class([f"a photo of a {s}."]) for s in names]
                                    + [clip.embed_class([p]) for p in UNKNOWN_SPECIES_PROMPTS])
        # Decide the species per burst: dozens of frames of one lion outvote a single odd guess
        for g in np.unique(groups):
            members = groups == g
            probs[members] = probs[members].mean(axis=0)
        best = probs.argmax(axis=1)
        species_conf = np.where(category == "animals", probs.max(axis=1), 0)
        known = (best < len(names)) & (category == "animals") & (species_conf >= SPECIES_MIN_CONFIDENCE)
        species = np.where(known, np.array(names + [""] * len(UNKNOWN_SPECIES_PROMPTS), dtype=object)[best], "")

    # Selection
    labels = np.where(species != "", species, category)  # used to avoid too many photos of one kind
    n = min(args.number, len(reps))
    quota = split_quota(n, weights)
    species_reps = {}
    for i in reps:
        if species[i]:
            species_reps.setdefault(species[i], []).append(i)
    if use_species:
        a = focuses.index("animals")
        if quota[a] < len(species_reps):
            others = [j for j in range(len(focuses)) if j != a]
            quota[a] = min(len(species_reps), n)
            if others:
                quota[others] = split_quota(n - quota[a], [weights[j] for j in others])
            if quota[a] >= len(species_reps):
                print(f"Found {len(species_reps)} species; using {quota[a]} animal photos so every species appears.")
            else:
                print(f"Found {len(species_reps)} species, but there is room for only {quota[a]}; "
                      f"increase -n to include them all.")

    chosen, chosen_for = [], {}
    for focus, k in zip(focuses, quota):
        score = 0.6 * quality + 0.4 * relevance[focus]
        pool = [i for i in reps if in_focus[focus][i] and i not in chosen_for]
        picked = []
        if focus == "animals" and use_species:
            firsts = []
            for members in species_reps.values():
                members = [i for i in members if i not in chosen_for]
                if members:
                    firsts.append(max(members, key=lambda i: score[i]))
            picked = sorted(firsts, key=lambda i: score[i], reverse=True)[:k]
            pool = [i for i in pool if i not in picked]
        picked += pick_diverse(pool, k - len(picked), score, emb, chosen + picked, args.diversity, labels,
                               args.duplicate_threshold)
        if len(picked) < k:
            print(f"Only {len(picked)} good '{focus}' photos found (wanted {k}).")
        chosen += picked
        chosen_for.update({i: focus for i in picked})

    if len(chosen) < n:  # fill the gap with the best remaining photos of any requested focus
        best_focus = np.array(focuses)[np.argmax([relevance[f] for f in focuses], axis=0)]
        score = 0.6 * quality + 0.4 * np.max([relevance[f] for f in focuses], axis=0)
        pool = [i for i in reps if any(in_focus[f][i] for f in focuses) and i not in chosen_for]
        picked = pick_diverse(pool, n - len(chosen), score, emb, chosen, args.diversity, labels,
                              args.duplicate_threshold)
        chosen += picked
        chosen_for.update({i: best_focus[i] for i in picked})

    # Copy in the order the photos were taken
    chosen.sort(key=lambda i: data["taken"][i])
    album_name = {}
    for rank, i in enumerate(chosen, 1):
        album_name[i] = f"{rank:03d}_{slug(species[i] or chosen_for[i])}_{paths[i].name}"
    if not args.dry_run:
        out.mkdir(parents=True, exist_ok=True)
        for i in chosen:
            shutil.copy2(paths[i], out / album_name[i])

    report = out / "album_report.csv" if not args.dry_run else folder / "album_report_dry_run.csv"
    with open(report, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "date_taken", "megapixels", "sharpness", "clipped", "quality",
                         "duplicate_group", "best_of_group", "category", "category_prob",
                         "species", "species_conf", "selected", "album_file"])
        for i, path in enumerate(paths):
            writer.writerow([path.relative_to(folder).as_posix(),
                             datetime.fromtimestamp(data["taken"][i]).strftime("%Y-%m-%d %H:%M:%S"),
                             round(data["pixels"][i] / 1e6, 1), round(data["sharpness"][i], 1),
                             round(data["clipped"][i], 3), round(quality[i], 3),
                             groups[i], best_in_group[groups[i]] == i, category[i],
                             round(class_probs[i].max(), 2), species[i], round(species_conf[i], 2),
                             i in album_name, album_name.get(i, "")])

    print(f"\nSelected {len(chosen)} photos:")
    for focus in focuses:
        print(f"  {focus}: {sum(chosen_for[i] == focus for i in chosen)}")
    if use_species:
        in_album = sorted({species[i] for i in chosen if species[i]})
        print(f"  species in album ({len(in_album)}): {', '.join(in_album)}")
    print(f"{'Would copy to' if args.dry_run else 'Copied to'}: {out}")
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
