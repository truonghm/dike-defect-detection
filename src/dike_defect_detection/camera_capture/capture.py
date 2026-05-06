"""Capture KBVISION camera snapshots and save them with D/N tags."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import (
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    Request,
    build_opener,
)

from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from dike_defect_detection.camera_capture.constants import (
    CAMERA_PASSWORD_ENV_VAR,
    CAMERA_SITE_CONFIG_PATH,
    CAMERA_USERNAME_ENV_VAR,
    CAPTURE_WORKERS,
    LOG_FILENAME,
    OUTPUT_DIR,
    RETRY_ATTEMPTS,
    RETRY_WAIT_MAX_SECONDS,
    RETRY_WAIT_MIN_SECONDS,
    RETRY_WAIT_MULTIPLIER_SECONDS,
    SNAPSHOT_PATH,
    TIMEOUT_SECONDS,
    USE_OLD_PROVINCE_ABBR,
    USER_AGENT,
)
from dike_defect_detection.camera_capture.mappings import (
    NEW_PROVINCE_ABBR,
    OLD_PROVINCE_ABBR,
    CameraSite,
    load_camera_sites,
)
from dike_defect_detection.image_assessment.blur import assess_blur_from_image_bytes
from dike_defect_detection.image_assessment.constants import (
    BLUR_THRESHOLD,
    DARK_PIXEL_THRESHOLD,
    DAY_END_HOUR,
    DAY_START_HOUR,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    NIGHT_DARK_RATIO_THRESHOLD,
    NIGHT_MEDIAN_THRESHOLD,
)
from dike_defect_detection.image_assessment.day_night import (
    DayNightTag,
    assess_day_night_from_image_bytes,
    get_time_tag,
)
from dike_defect_detection.image_assessment.resolution import assess_resolution
from dike_defect_detection.scene_understanding.processing import (
    run_scene_understanding_for_paths,
    write_scene_understanding_error,
)

SCENE_UNDERSTANDING_DIR_NAME = "scene_understanding"
SCENE_UNDERSTANDING_RUN_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

CSV_FIELDS: tuple[str, ...] = (
    "filename",
    "camera_key",
    "base_url",
    "channel",
    "captured_at",
    "old_province_abbr",
    "province_name",
    "province_abbr",
    "site_code",
    "time_tag",
    "image_tag",
    "review_flag",
    "review_reason",
    "median_luminance",
    "mean_luminance",
    "dark_ratio",
    "image_width",
    "image_height",
    "blur_score",
    "blur_threshold",
    "blur_valid",
)


@dataclass(frozen=True, slots=True)
class CaptureCredentials:
    """Credentials used for KBVISION Digest authentication.

    Parameters
    ----------
    username: str
        Camera username.
    password: str
        Camera password.
    """

    username: str
    password: str


class SnapshotRetryableError(RuntimeError):
    """Retryable snapshot failure during fetch."""


@dataclass(frozen=True, slots=True)
class RawSnapshotCapture:
    """Raw snapshot bytes and capture metadata before image assessment.

    Parameters
    ----------
    camera_key: str
        Key in the camera site config.
    camera_site: CameraSite
        Camera endpoint metadata.
    channel: int
        Snapshot channel.
    captured_at: datetime
        Local timestamp captured before the snapshot request.
    image_bytes: bytes
        Raw snapshot image bytes.
    """

    camera_key: str
    camera_site: CameraSite
    channel: int
    captured_at: datetime
    image_bytes: bytes


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    """CSV record for one saved camera snapshot.

    Parameters
    ----------
    filename: str
        Saved image filename.
    camera_key: str
        Key in the camera site config.
    base_url: str
        Camera web URL.
    channel: int
        Snapshot channel.
    captured_at: str
        Local timestamp in ISO 8601 format.
    old_province_abbr: bool
        Whether the old province abbreviation table was used.
    province_name: str
        Normalized province name used to look up the abbreviation.
    province_abbr: str
        Province abbreviation used in the filename.
    site_code: str
        Site abbreviation used in the filename.
    time_tag: DayNightTag
        Timestamp-derived D/N tag.
    image_tag: DayNightTag
        Image-content-derived D/N tag.
    review_flag: bool
        Whether this snapshot should be manually reviewed.
    review_reason: str
        Semicolon-delimited reasons for manual review, if any.
    median_luminance: float
        Median grayscale luminance in the central scene crop.
    mean_luminance: float
        Mean grayscale luminance in the central scene crop.
    dark_ratio: float
        Fraction of central-crop pixels below the dark-pixel threshold.
    image_width: int
        Original image width in pixels.
    image_height: int
        Original image height in pixels.
    blur_score: str
        Blur-effect score for day images. Empty for night images.
    blur_threshold: str
        Blur-effect threshold used for day images. Empty for night images.
    blur_valid: str
        Whether the image is sharper than the blur threshold. Empty for night images.
    """

    filename: str
    camera_key: str
    base_url: str
    channel: int
    captured_at: str
    old_province_abbr: bool
    province_name: str
    province_abbr: str
    site_code: str
    time_tag: DayNightTag
    image_tag: DayNightTag
    review_flag: bool
    review_reason: str
    median_luminance: float
    mean_luminance: float
    dark_ratio: float
    image_width: int
    image_height: int
    blur_score: str
    blur_threshold: str
    blur_valid: str


def build_snapshot_url(camera_site: CameraSite, channel: int) -> str:
    """Build the KBVISION HTTP snapshot URL for a camera channel.

    Parameters
    ----------
    camera_site: CameraSite
        Camera endpoint metadata.
    channel: int
        KBVISION channel number.

    Returns
    -------
    str
        Snapshot URL for ``/cgi-bin/snapshot.cgi``.
    """

    base_url = camera_site.base_url.rstrip("/") + "/"
    return urljoin(base_url, f"{SNAPSHOT_PATH}?channel={channel}")


def resolve_credentials(username: str | None, password: str | None) -> CaptureCredentials:
    """Resolve camera credentials from CLI overrides or environment variables.

    Parameters
    ----------
    username: str | None
        CLI username override. If omitted, ``CAMERA_USERNAME`` is used.
    password: str | None
        CLI password override. If omitted, ``CAMERA_PASSWORD`` is used.

    Returns
    -------
    CaptureCredentials
        Resolved credentials.

    Raises
    ------
    ValueError
        If either username or password is missing.
    """

    resolved_username = username or os.environ.get(CAMERA_USERNAME_ENV_VAR)
    resolved_password = password or os.environ.get(CAMERA_PASSWORD_ENV_VAR)
    if not resolved_username or not resolved_password:
        raise ValueError(
            "Camera credentials are required. Set "
            f"{CAMERA_USERNAME_ENV_VAR} and {CAMERA_PASSWORD_ENV_VAR} "
            "or pass -u/--username and -p/--password."
        )
    return CaptureCredentials(username=resolved_username, password=resolved_password)


def fetch_snapshot(
    snapshot_url: str,
    credentials: CaptureCredentials,
    *,
    timeout_seconds: float,
) -> bytes:
    """Fetch a snapshot image using HTTP Digest authentication.

    Parameters
    ----------
    snapshot_url: str
        Snapshot endpoint URL.
    credentials: CaptureCredentials
        Digest-auth username and password.
    timeout_seconds: float
        Network timeout in seconds.

    Returns
    -------
    bytes
        Raw image response body.

    Raises
    ------
    SnapshotRetryableError
        If the endpoint cannot be reached or returns an empty response.
    """

    password_manager = HTTPPasswordMgrWithDefaultRealm()
    password_manager.add_password(
        None,
        snapshot_url,
        credentials.username,
        credentials.password,
    )
    opener = build_opener(HTTPDigestAuthHandler(password_manager))
    request = Request(
        snapshot_url,
        headers={
            "Accept": "image/jpeg,*/*",
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            image_bytes = response.read()
    except HTTPError as error:
        raise SnapshotRetryableError(
            f"HTTP error while fetching snapshot from {snapshot_url}: {error.code} {error.reason}"
        ) from error
    except URLError as error:
        raise SnapshotRetryableError(
            f"URL error while fetching snapshot from {snapshot_url}: {error.reason}"
        ) from error
    except TimeoutError as error:
        raise SnapshotRetryableError(f"Timeout while fetching snapshot from {snapshot_url}") from error
    except OSError as error:
        raise SnapshotRetryableError(f"OS error while fetching snapshot from {snapshot_url}: {error}") from error

    if not image_bytes:
        raise SnapshotRetryableError(f"Empty snapshot response from {snapshot_url}")
    return image_bytes


def fetch_snapshot_with_retries(
    snapshot_url: str,
    credentials: CaptureCredentials,
    *,
    timeout_seconds: float,
) -> bytes:
    """Fetch raw snapshot bytes with exponential backoff.

    Parameters
    ----------
    snapshot_url: str
        Snapshot endpoint URL.
    credentials: CaptureCredentials
        Digest-auth username and password.
    timeout_seconds: float
        Network timeout in seconds for each attempt.

    Returns
    -------
    bytes
        Raw snapshot image bytes.

    Raises
    ------
    SnapshotRetryableError
        If all attempts fail due to fetch errors or empty responses.
    """

    retryer = Retrying(
        retry=retry_if_exception_type(SnapshotRetryableError),
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=RETRY_WAIT_MULTIPLIER_SECONDS,
            min=RETRY_WAIT_MIN_SECONDS,
            max=RETRY_WAIT_MAX_SECONDS,
        ),
        reraise=True,
    )
    for attempt in retryer:
        with attempt:
            return fetch_snapshot(
                snapshot_url,
                credentials,
                timeout_seconds=timeout_seconds,
            )

    raise SnapshotRetryableError(f"Snapshot retry loop exited unexpectedly: {snapshot_url}")


def get_province_name(camera_site: CameraSite, *, old_province_abbr: bool) -> str:
    """Return the province name selected for filename abbreviation.

    Parameters
    ----------
    camera_site: CameraSite
        Camera endpoint metadata.
    old_province_abbr: bool
        Whether to use the old province mapping.

    Returns
    -------
    str
        Normalized province name.
    """

    if old_province_abbr:
        return camera_site.old_province_name
    return camera_site.new_province_name


def get_province_abbr(province_name: str, *, old_province_abbr: bool) -> str:
    """Return the province abbreviation for a normalized province name.

    Parameters
    ----------
    province_name: str
        Normalized province name.
    old_province_abbr: bool
        Whether to use the old province mapping.

    Returns
    -------
    str
        Province abbreviation.
    """

    if old_province_abbr:
        return OLD_PROVINCE_ABBR[province_name]
    return NEW_PROVINCE_ABBR[province_name]


def build_filename(
    camera_site: CameraSite,
    captured_at: datetime,
    *,
    old_province_abbr: bool,
) -> str:
    """Build a camera snapshot filename.

    Parameters
    ----------
    camera_site: CameraSite
        Camera endpoint metadata.
    captured_at: datetime
        Local capture timestamp.
    old_province_abbr: bool
        Whether to use the old province mapping.

    Returns
    -------
    str
        Filename using ``<province>-<site>-<YYYYMMDD>_<HHMMSS>.jpg``.
    """

    province_name = get_province_name(
        camera_site,
        old_province_abbr=old_province_abbr,
    )
    province_abbr = get_province_abbr(province_name, old_province_abbr=old_province_abbr)
    timestamp_text = captured_at.strftime("%Y%m%d_%H%M%S")
    return f"{province_abbr}-{camera_site.site_code}-{timestamp_text}.jpg"


def append_capture_record(log_path: Path, record: CaptureRecord) -> None:
    """Append one capture record to a CSV log.

    Parameters
    ----------
    log_path: Path
        CSV log path.
    record: CaptureRecord
        Record to append.
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing_fields = read_existing_csv_fields(log_path)
    fieldnames = existing_fields or CSV_FIELDS
    should_write_header = existing_fields is None
    with log_path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        if should_write_header:
            writer.writeheader()
        writer.writerow(asdict(record))


def read_existing_csv_fields(log_path: Path) -> tuple[str, ...] | None:
    """Read an existing CSV header, if the log already has one.

    Parameters
    ----------
    log_path: Path
        CSV log path.

    Returns
    -------
    tuple[str, ...] | None
        Existing field names, or ``None`` when the file is absent or empty.
    """

    if not log_path.exists() or log_path.stat().st_size == 0:
        return None
    with log_path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader, None)
    if not header:
        return None
    return tuple(header)


def build_scene_understanding_output_dir(capture_output_dir: Path, run_started_at: datetime) -> Path:
    """Build the fixed scene-understanding output directory for one capture run.

    Parameters
    ----------
    capture_output_dir: Path
        Directory where camera snapshots are saved.
    run_started_at: datetime
        Timestamp assigned to the camera-capture run.

    Returns
    -------
    Path
        ``<capture-output-parent>/scene_understanding/<YYYYMMDD_HHMMSS>``.
    """

    timestamp_text = run_started_at.strftime(SCENE_UNDERSTANDING_RUN_TIMESTAMP_FORMAT)
    return capture_output_dir.parent / SCENE_UNDERSTANDING_DIR_NAME / timestamp_text


def collect_day_capture_paths(records: Sequence[CaptureRecord], output_dir: Path) -> list[Path]:
    """Collect saved day-image paths from the current capture run.

    Parameters
    ----------
    records: Sequence[CaptureRecord]
        Capture records saved during the current CLI invocation.
    output_dir: Path
        Directory where camera snapshots are saved.

    Returns
    -------
    list[Path]
        Paths for records whose image-content tag is ``D``.
    """

    return [output_dir / record.filename for record in records if record.image_tag == "D"]


def run_scene_understanding_for_capture_records(
    records: Sequence[CaptureRecord],
    *,
    capture_output_dir: Path,
    run_started_at: datetime,
) -> bool:
    """Run scene understanding for current-run day captures.

    Parameters
    ----------
    records: Sequence[CaptureRecord]
        Capture records saved during the current CLI invocation.
    capture_output_dir: Path
        Directory where camera snapshots are saved.
    run_started_at: datetime
        Timestamp assigned to the camera-capture run.

    Returns
    -------
    bool
        ``True`` when scene understanding completed and wrote its JSON files.
    """

    scene_output_dir = build_scene_understanding_output_dir(capture_output_dir, run_started_at)
    day_image_paths = collect_day_capture_paths(records, capture_output_dir)
    try:
        result = run_scene_understanding_for_paths(day_image_paths, scene_output_dir)
    except Exception as error:
        write_scene_understanding_error(scene_output_dir, day_image_paths, str(error))
        print(f"scene_understanding_failed output_dir={scene_output_dir} error={error}", file=sys.stderr)
        return False

    print(f"scene_understanding_output_dir={result.output_dir}")
    print(f"scene_understanding_images={len(day_image_paths)}")
    print(f"scene_assessment={result.scene_assessment_path}")
    return True


def capture_raw_snapshot(
    camera_key: str,
    credentials: CaptureCredentials,
    *,
    camera_sites: Mapping[str, CameraSite],
    channel: int | None,
    timeout_seconds: float,
) -> RawSnapshotCapture:
    """Download one raw camera snapshot.

    Parameters
    ----------
    camera_key: str
        Key in the camera site config.
    credentials: CaptureCredentials
        Digest-auth username and password.
    camera_sites: Mapping[str, CameraSite]
        Camera site metadata keyed by camera key.
    channel: int | None
        Channel override. If omitted, the camera default channel is used.
    timeout_seconds: float
        Network timeout in seconds.

    Returns
    -------
    RawSnapshotCapture
        Raw snapshot bytes and capture metadata.
    """

    camera_site = camera_sites[camera_key]
    selected_channel = camera_site.default_channel if channel is None else channel
    captured_at = datetime.now()
    snapshot_url = build_snapshot_url(camera_site, selected_channel)
    image_bytes = fetch_snapshot_with_retries(
        snapshot_url,
        credentials,
        timeout_seconds=timeout_seconds,
    )

    return RawSnapshotCapture(
        camera_key=camera_key,
        camera_site=camera_site,
        channel=selected_channel,
        captured_at=captured_at,
        image_bytes=image_bytes,
    )


def assess_and_save_capture(
    raw_capture: RawSnapshotCapture,
    *,
    output_dir: Path,
    old_province_abbr: bool,
    day_start_hour: int,
    day_end_hour: int,
    night_median_threshold: float,
    night_dark_ratio_threshold: float,
    dark_pixel_threshold: int,
    blur_threshold: float,
    overwrite: bool,
) -> CaptureRecord:
    """Assess a raw snapshot, save it, and build a CSV record.

    Parameters
    ----------
    raw_capture: RawSnapshotCapture
        Downloaded snapshot bytes and capture metadata.
    output_dir: Path
        Directory where image files are saved.
    old_province_abbr: bool
        Whether to use old province abbreviations.
    day_start_hour: int
        Inclusive local hour when daytime begins.
    day_end_hour: int
        Exclusive local hour when daytime ends.
    night_median_threshold: float
        Median luminance below which the image is tagged as night.
    night_dark_ratio_threshold: float
        Dark-pixel ratio above which the image is tagged as night.
    dark_pixel_threshold: int
        Luminance threshold used to count dark pixels.
    blur_threshold: float
        Blur-effect score above which day images are flagged as blurred.
    overwrite: bool
        Whether to overwrite an existing filename.

    Returns
    -------
    CaptureRecord
        Saved snapshot metadata and D/N diagnostics.
    """

    camera_site = raw_capture.camera_site
    captured_at = raw_capture.captured_at
    day_night_assessment = assess_day_night_from_image_bytes(
        raw_capture.image_bytes,
        night_median_threshold=night_median_threshold,
        night_dark_ratio_threshold=night_dark_ratio_threshold,
        dark_pixel_threshold=dark_pixel_threshold,
    )
    time_tag = get_time_tag(
        captured_at,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
    )
    resolution_assessment = assess_resolution(
        day_night_assessment.image_width,
        day_night_assessment.image_height,
        expected_width=IMAGE_WIDTH,
        expected_height=IMAGE_HEIGHT,
    )
    review_reasons: list[str] = []
    if day_night_assessment.image_tag != time_tag:
        review_reasons.append("time_image_disagree")
    if not resolution_assessment.is_valid:
        review_reasons.append("resolution_mismatch")
    blur_score = ""
    blur_threshold_text = ""
    blur_valid = ""
    if day_night_assessment.image_tag == "D":
        blur_threshold_text = f"{blur_threshold}"
        try:
            blur_assessment = assess_blur_from_image_bytes(
                raw_capture.image_bytes,
                blur_threshold=blur_threshold,
            )
        except (OSError, RuntimeError):
            review_reasons.append("blur_check_failed")
        else:
            blur_score = f"{blur_assessment.blur_score:.6f}"
            blur_valid = str(blur_assessment.is_sharp)
            if not blur_assessment.is_sharp:
                review_reasons.append("blurred")
    review_flag = bool(review_reasons)
    review_reason = ";".join(review_reasons)
    filename = build_filename(
        camera_site,
        captured_at,
        old_province_abbr=old_province_abbr,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    if output_path.exists() and not overwrite:
        raise RuntimeError(f"Output file already exists: {output_path}")
    output_path.write_bytes(raw_capture.image_bytes)

    province_name = get_province_name(
        camera_site,
        old_province_abbr=old_province_abbr,
    )
    province_abbr = get_province_abbr(province_name, old_province_abbr=old_province_abbr)
    record = CaptureRecord(
        filename=filename,
        camera_key=raw_capture.camera_key,
        base_url=camera_site.base_url,
        channel=raw_capture.channel,
        captured_at=captured_at.isoformat(timespec="seconds"),
        old_province_abbr=old_province_abbr,
        province_name=province_name,
        province_abbr=province_abbr,
        site_code=camera_site.site_code,
        time_tag=time_tag,
        image_tag=day_night_assessment.image_tag,
        review_flag=review_flag,
        review_reason=review_reason,
        median_luminance=round(day_night_assessment.median_luminance, 4),
        mean_luminance=round(day_night_assessment.mean_luminance, 4),
        dark_ratio=round(day_night_assessment.dark_ratio, 6),
        image_width=day_night_assessment.image_width,
        image_height=day_night_assessment.image_height,
        blur_score=blur_score,
        blur_threshold=blur_threshold_text,
        blur_valid=blur_valid,
    )
    return record


def capture_camera_snapshot(
    camera_key: str,
    credentials: CaptureCredentials,
    *,
    camera_sites: Mapping[str, CameraSite],
    output_dir: Path,
    log_path: Path,
    channel: int | None,
    old_province_abbr: bool,
    timeout_seconds: float,
    day_start_hour: int,
    day_end_hour: int,
    night_median_threshold: float,
    night_dark_ratio_threshold: float,
    dark_pixel_threshold: int,
    blur_threshold: float,
    overwrite: bool,
) -> CaptureRecord:
    """Capture one camera snapshot, save it, and append a CSV record."""

    raw_capture = capture_raw_snapshot(
        camera_key,
        credentials,
        camera_sites=camera_sites,
        channel=channel,
        timeout_seconds=timeout_seconds,
    )
    record = assess_and_save_capture(
        raw_capture,
        output_dir=output_dir,
        old_province_abbr=old_province_abbr,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        night_median_threshold=night_median_threshold,
        night_dark_ratio_threshold=night_dark_ratio_threshold,
        dark_pixel_threshold=dark_pixel_threshold,
        blur_threshold=blur_threshold,
        overwrite=overwrite,
    )
    append_capture_record(log_path, record)
    return record


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the camera-capture CLI parser.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser.
    """

    parser = argparse.ArgumentParser(
        description="Capture KBVISION camera snapshots with automatic D/N tags.",
    )
    parser.add_argument(
        "--camera",
        help="Camera key to capture, or 'all'.",
    )
    parser.add_argument(
        "--site-config",
        type=Path,
        help=f"Camera site JSON config path. Default: {CAMERA_SITE_CONFIG_PATH}.",
    )
    parser.add_argument(
        "-u",
        "--username",
        help="Camera username. Overrides CAMERA_USERNAME.",
    )
    parser.add_argument(
        "-p",
        "--password",
        help="Camera password. Overrides CAMERA_PASSWORD.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=f"Directory where snapshots are saved. Default: {OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        help=f"CSV log path. Default: <output-dir>/{LOG_FILENAME}.",
    )
    parser.add_argument(
        "--channel",
        type=int,
        help="Camera channel override. Defaults to each camera mapping.",
    )
    parser.add_argument(
        "--old-province-abbr",
        action=argparse.BooleanOptionalAction,
        default=USE_OLD_PROVINCE_ABBR,
        help="Use old province abbreviations. Use --no-old-province-abbr for current abbreviations.",
    )
    parser.add_argument(
        "--day-start-hour",
        type=int,
        help=f"Inclusive local hour when daytime begins. Default: {DAY_START_HOUR}.",
    )
    parser.add_argument(
        "--day-end-hour",
        type=int,
        help=f"Exclusive local hour when daytime ends. Default: {DAY_END_HOUR}.",
    )
    parser.add_argument(
        "--night-median-threshold",
        type=float,
        help=(f"Median luminance below which an image is tagged as night. Default: {NIGHT_MEDIAN_THRESHOLD}."),
    )
    parser.add_argument(
        "--night-dark-ratio-threshold",
        type=float,
        help=(f"Dark-pixel ratio above which an image is tagged as night. Default: {NIGHT_DARK_RATIO_THRESHOLD}."),
    )
    parser.add_argument(
        "--dark-pixel-threshold",
        type=int,
        help=(f"Luminance threshold used to count dark pixels. Default: {DARK_PIXEL_THRESHOLD}."),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        help=f"Network timeout in seconds. Default: {TIMEOUT_SECONDS}.",
    )
    parser.add_argument(
        "--capture-workers",
        type=int,
        help=f"Maximum parallel snapshot downloads. Default: {CAPTURE_WORKERS}.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing image filename if it already exists.",
    )
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="Print configured cameras and exit without credentials.",
    )
    return parser


def validate_hour_arguments(day_start_hour: int, day_end_hour: int) -> None:
    """Validate timestamp-based D/N hour thresholds.

    Parameters
    ----------
    day_start_hour: int
        Inclusive local hour when daytime begins.
    day_end_hour: int
        Exclusive local hour when daytime ends.

    Raises
    ------
    ValueError
        If either hour is outside ``0`` to ``23`` or the interval is empty.
    """

    if not 0 <= day_start_hour <= 23:
        raise ValueError("--day-start-hour must be between 0 and 23")
    if not 0 <= day_end_hour <= 23:
        raise ValueError("--day-end-hour must be between 0 and 23")
    if day_start_hour >= day_end_hour:
        raise ValueError("--day-start-hour must be smaller than --day-end-hour")


def validate_channel_argument(channel: int | None) -> None:
    """Validate the optional camera channel override.

    Parameters
    ----------
    channel: int | None
        Channel override supplied by the CLI.

    Raises
    ------
    ValueError
        If the channel is smaller than ``1``.
    """

    if channel is not None and channel < 1:
        raise ValueError("--channel must be at least 1")


def validate_capture_workers(capture_workers: int) -> None:
    """Validate the parallel capture worker count.

    Parameters
    ----------
    capture_workers: int
        Maximum number of concurrent snapshot downloads.

    Raises
    ------
    ValueError
        If the worker count is smaller than ``1``.
    """

    if capture_workers < 1:
        raise ValueError("--capture-workers must be at least 1")


def print_camera_list(camera_sites: Mapping[str, CameraSite], *, old_province_abbr: bool) -> None:
    """Print configured camera keys and filename prefixes.

    Parameters
    ----------
    old_province_abbr: bool
        Whether to print prefixes using old province abbreviations.
    """

    for camera_key, camera_site in camera_sites.items():
        province_name = get_province_name(
            camera_site,
            old_province_abbr=old_province_abbr,
        )
        province_abbr = get_province_abbr(
            province_name,
            old_province_abbr=old_province_abbr,
        )
        prefix = f"{province_abbr}-{camera_site.site_code}"
        active_text = "active" if camera_site.is_active else "inactive"
        print(f"{camera_key}\t{prefix}\t{active_text}\t{camera_site.base_url}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the camera-capture CLI.

    Parameters
    ----------
    argv: Sequence[str] | None
        CLI arguments excluding the executable name. If omitted, arguments are
        read from ``sys.argv``.

    Returns
    -------
    int
        Process exit code.
    """

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    site_config_path = args.site_config or CAMERA_SITE_CONFIG_PATH
    output_dir = args.output_dir or OUTPUT_DIR
    log_path = args.log_path or output_dir / LOG_FILENAME
    day_start_hour = DAY_START_HOUR if args.day_start_hour is None else args.day_start_hour
    day_end_hour = DAY_END_HOUR if args.day_end_hour is None else args.day_end_hour
    night_median_threshold = (
        NIGHT_MEDIAN_THRESHOLD if args.night_median_threshold is None else args.night_median_threshold
    )
    night_dark_ratio_threshold = (
        NIGHT_DARK_RATIO_THRESHOLD if args.night_dark_ratio_threshold is None else args.night_dark_ratio_threshold
    )
    dark_pixel_threshold = DARK_PIXEL_THRESHOLD if args.dark_pixel_threshold is None else args.dark_pixel_threshold
    blur_threshold = BLUR_THRESHOLD
    timeout_seconds = TIMEOUT_SECONDS if args.timeout_seconds is None else args.timeout_seconds
    capture_workers = CAPTURE_WORKERS if args.capture_workers is None else args.capture_workers
    run_started_at = datetime.now()

    try:
        camera_sites = load_camera_sites(site_config_path)
        validate_hour_arguments(day_start_hour, day_end_hour)
        validate_channel_argument(args.channel)
        validate_capture_workers(capture_workers)
    except ValueError as error:
        parser.error(str(error))

    if args.list_cameras:
        print_camera_list(camera_sites, old_province_abbr=args.old_province_abbr)
        return 0

    if args.camera is None:
        parser.error("--camera is required unless --list-cameras is used")
    if args.camera != "all" and args.camera not in camera_sites:
        parser.error(f"Unknown camera key: {args.camera}. Use --list-cameras to inspect configured keys.")

    try:
        credentials = resolve_credentials(args.username, args.password)
    except ValueError as error:
        parser.error(str(error))

    if args.camera == "all":
        camera_keys = tuple(camera_key for camera_key, camera_site in camera_sites.items() if camera_site.is_active)
    else:
        camera_keys = (args.camera,)
    if not camera_keys:
        parser.error("No active camera sites are configured")

    raw_captures: list[RawSnapshotCapture] = []
    saved_records: list[CaptureRecord] = []
    failed_count = 0
    max_workers = min(capture_workers, len(camera_keys))
    capture_futures: dict[Future[RawSnapshotCapture], str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for camera_key in camera_keys:
            future = executor.submit(
                capture_raw_snapshot,
                camera_key,
                credentials,
                camera_sites=camera_sites,
                channel=args.channel,
                timeout_seconds=timeout_seconds,
            )
            capture_futures[future] = camera_key

        for future in as_completed(capture_futures):
            camera_key = capture_futures[future]
            try:
                raw_captures.append(future.result())
            except RuntimeError as error:
                failed_count += 1
                print(f"{camera_key}: {error}", file=sys.stderr)

    for raw_capture in raw_captures:
        try:
            record = assess_and_save_capture(
                raw_capture,
                output_dir=output_dir,
                old_province_abbr=args.old_province_abbr,
                day_start_hour=day_start_hour,
                day_end_hour=day_end_hour,
                night_median_threshold=night_median_threshold,
                night_dark_ratio_threshold=night_dark_ratio_threshold,
                dark_pixel_threshold=dark_pixel_threshold,
                blur_threshold=blur_threshold,
                overwrite=args.overwrite,
            )
        except RuntimeError as error:
            failed_count += 1
            print(f"{raw_capture.camera_key}: {error}", file=sys.stderr)
            continue
        append_capture_record(log_path, record)
        saved_records.append(record)
        review_text = " review_flag=true" if record.review_flag else ""
        print(f"saved {record.filename}{review_text}")

    scene_understanding_ok = run_scene_understanding_for_capture_records(
        saved_records,
        capture_output_dir=output_dir,
        run_started_at=run_started_at,
    )
    if not scene_understanding_ok:
        failed_count += 1

    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
