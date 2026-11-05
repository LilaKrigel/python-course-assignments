# Photo Album Picker

Picks the best N photos from a folder (e.g. a whole trip) and copies them into a new subfolder.

- **Removes near-duplicates**: from a group of photos that look almost the same, only the
  sharpest / highest-resolution one is kept.
- **Selects by content**: `animals`, `people` (us), `landscapes` (views), or any free text
  such as `"sunset"` or `"elephants"`.
- **Covers every animal species**: when `animals` is a focus, every recognised species gets
  at least one photo before a species gets a second one.
- **Avoids repetitive albums**: photos that look like ones already chosen are penalised.

Everything runs locally on your computer (no upload, no API key). Content recognition uses
the [CLIP](https://github.com/mlfoundations/open_clip) model, which is downloaded once (~600 MB).

## Install

```
pip install -r requirements.txt
```

Optional, for iPhone `.HEIC` photos: `pip install pillow-heif`

## Use

```
python album_picker.py "D:/Photos/Africa 2026" -n 60 --focus animals people
```

| Option | Meaning |
|---|---|
| `-n 60` | number of photos in the album |
| `--focus animals people landscapes` | what to select (default: all three equally). Aliases: `us`, `views`, `wildlife` |
| `--focus animals:2 people:1` | weights: here 2/3 of the photos are animals, 1/3 people |
| `--focus "sunset" "elephants"` | free text works too |
| `--species my_species.txt` | species list (default: [species_africa.txt](species_africa.txt)); make your own for other trips |
| `--no-species` | don't force one photo per species |
| `--duplicate-threshold 0.9` | lower it if duplicates still slip through; raise it if different photos are treated as duplicates |
| `--duplicate-seconds 120` | photos of one burst must be taken at most this many seconds apart |
| `--min-quality 0.25` | never pick photos below this quality score (0–1); raise it to drop more blurry or distant shots |
| `--diversity 0.5` | higher means more varied photos, lower means simply the best-scoring ones |
| `--out FOLDER` | output folder (default: `album_<focus>_<n>` inside the photo folder) |
| `--dry-run` | don't copy, only print and write the report |

The photos are copied (originals are never touched) and named in the order they were taken,
e.g. `012_giraffe_IMG_4411.jpg`, so the album reads like the trip.

`album_report.csv` in the output folder lists **every** photo with its sharpness, resolution,
duplicate group, detected category and species, and whether it was selected. Open it in Excel
to understand or fine-tune the choices.

The first run analyses every photo with the large CLIP model (ViT-L-14). On a laptop CPU this
takes several minutes for 2000 photos. The small model (`ViT-B-32` in `album_picker.py`) is much
faster but mislabeled about half the species in testing. The results are cached in
`.album_cache.npz` inside the photo folder, so running again with a different `-n` or `--focus`
takes seconds.

## How it scores photos

- **Sharpness**: variance of the Laplacian (edge strength), measured on the sharpest parts of
  the photo, so a sharp animal in front of a blurred background still scores high.
- **Resolution**: original pixel count.
- **Exposure**: penalty when much of the photo is pure black or pure white.
- **Duplicates**: photos taken in a row whose CLIP image embeddings are similar (cosine similarity
  above the threshold) to the first photo of the burst are grouped. In the album, a photo is also
  skipped if it is that similar to one already chosen, even when taken much later.
- **Content and species**: CLIP zero-shot classification against text descriptions. The species
  is decided per burst (all frames vote) and only when the model is at least 50% confident.
- **Variety**: each additional photo of a species already in the album gets a penalty.
