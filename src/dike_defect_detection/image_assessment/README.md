# Image Assessment

Run reusable image checks on existing files or directories. Output is CSV to stdout.

## Run All Checks

```bash
uv run python -m dike_defect_detection.image_assessment data/camera_img
```

Save CSV with shell redirection:

```bash
uv run python -m dike_defect_detection.image_assessment data/camera_img \
  > /tmp/camera_img_assessment.csv
```

## Run Selected Checks

Resolution only:

```bash
uv run python -m dike_defect_detection.image_assessment data/camera_img \
  --checks resolution
```

Day/night only:

```bash
uv run python -m dike_defect_detection.image_assessment data/camera_img \
  --checks day_night
```

## Paths

Inputs can be image files or directories.

Directory scanning is non-recursive and includes:

```text
.jpg
.jpeg
.png
```

## Checks

```text
day_night
resolution
```

Default: run all checks.

`day_night` is image-only and does not parse timestamps from filenames.

`resolution` validates against `IMAGE_WIDTH` and `IMAGE_HEIGHT` in `image_assessment/constants.py`.
