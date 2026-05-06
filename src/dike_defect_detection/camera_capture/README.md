# Camera Capture

Capture KBVISION camera snapshots and save them with the project filename convention:

```text
<PROVINCE>-<SITE>-<YYYYMMDD>_<HHMMSS>_<D|N>.jpg
```

Example:

```text
TB-KTT-20260505_091530_D.jpg
```

## Credentials

Preferred: set environment variables once per shell session.

```bash
export CAMERA_USERNAME="your_username"
export CAMERA_PASSWORD="your_password"
```

Alternative: pass credentials directly with CLI flags. CLI flags override environment variables.

```bash
-u "your_username" -p "your_password"
```

## List Cameras

```bash
uv run python -m dike_defect_detection.camera_capture --list-cameras
```

## Site Config

Default site config:

```text
config/camera_sites.json
```

Each site entry uses this shape:

```json
{
  "camera_key": "ketanthanh",
  "base_url": "http://ketanthanh.kbvision.tv:8081/",
  "site_code": "KTT",
  "old_province_name": "Thai Binh",
  "new_province_name": "Hung Yen",
  "default_channel": 1
}
```

Use a custom site config:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --site-config config/my_camera_sites.json \
  --camera all
```

## Capture One Camera

Using environment credentials:

```bash
uv run python -m dike_defect_detection.camera_capture --camera ketanthanh
```

Using CLI credentials:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --camera ketanthanh \
  -u "your_username" \
  -p "your_password"
```

## Capture All Cameras

```bash
uv run python -m dike_defect_detection.camera_capture --camera all
```

## Output Directory

Default output directory:

```text
data/camera_img
```

Set a custom output directory:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --camera all \
  --output-dir data/camera_img_new
```

## CSV Log

Default log path:

```text
<output-dir>/camera_capture_log.csv
```

Set a custom log path:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --camera all \
  --log-path data/camera_capture_log.csv
```

## Retry Behavior

Snapshot fetches are retried automatically for transient failures:

```text
empty response
invalid image response
HTTP/URL fetch error
```

Retry settings are constants in `camera_capture/constants.py`, not CLI flags.

## Province Abbreviation Mode

Default: old province abbreviations.

Use current province abbreviations:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --camera all \
  --no-old-province-abbr
```

## Day/Night Review Flags

The filename uses the image-based `D` or `N` tag.

The CSV log compares this against local timestamp-based expectation. If they disagree, the row has:

```text
review_flag=true
review_reason=time_image_disagree
```

The CSV log also validates image resolution against `IMAGE_WIDTH` and `IMAGE_HEIGHT` in `image_assessment/constants.py`. If the resolution is unexpected, the row has:

```text
review_flag=true
review_reason=resolution_mismatch
```

If multiple checks fail, `review_reason` is semicolon-delimited.

Default timestamp rule:

```text
05:00-18:59 -> D
19:00-04:59 -> N
```

Override the timestamp rule:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --camera all \
  --day-start-hour 5 \
  --day-end-hour 19
```

## Camera Keys

```text
ketanthanh
congvanthang
kethonguyen
congtrieuduonghungyen
kesaraidongthap
all
```

## Common Commands

Capture all cameras with environment credentials:

```bash
uv run python -m dike_defect_detection.camera_capture --camera all
```

Capture all cameras with a custom site config:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --site-config config/my_camera_sites.json \
  --camera all
```

Capture all cameras with explicit credentials:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --camera all \
  -u "your_username" \
  -p "your_password"
```

Capture one camera into a temporary directory:

```bash
uv run python -m dike_defect_detection.camera_capture \
  --camera ketanthanh \
  --output-dir /tmp/camera_capture_test
```

Run as a script path instead of a module:

```bash
uv run src/dike_defect_detection/camera_capture/capture.py --camera all
```
