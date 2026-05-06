"""Command-line interface for standalone image assessment."""

# TODO: implement separate blur thresholds for day and night images.
# TODO: extract the capture-filename D/N parser into the `dataset` subpackage
# once it gains other consumers.

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from dike_defect_detection.image_assessment.blur import assess_blur_from_image_bytes
from dike_defect_detection.image_assessment.constants import (
    BLUR_THRESHOLD,
    DARK_PIXEL_THRESHOLD,
    IMAGE_EXTENSIONS,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    NIGHT_DARK_RATIO_THRESHOLD,
    NIGHT_MEDIAN_THRESHOLD,
)
from dike_defect_detection.image_assessment.day_night import assess_day_night_from_image_bytes
from dike_defect_detection.image_assessment.resolution import assess_resolution

AssessmentCheck = Literal["day_night", "resolution", "blur"]

AVAILABLE_CHECKS: tuple[AssessmentCheck, ...] = ("day_night", "resolution", "blur")
CSV_FIELDS: tuple[str, ...] = (
    "path",
    "filename",
    "checks_run",
    "review_flag",
    "review_reason",
    "error",
    "image_tag",
    "median_luminance",
    "mean_luminance",
    "dark_ratio",
    "image_width",
    "image_height",
    "expected_width",
    "expected_height",
    "resolution_valid",
    "blur_score",
    "blur_threshold",
    "blur_valid",
)


@dataclass(frozen=True, slots=True)
class ImageAssessmentRecord:
    """CSV record for standalone image assessment.

    Parameters
    ----------
    path: str
        Image path as provided after expansion.
    filename: str
        Image filename.
    checks_run: str
        Semicolon-delimited check names.
    review_flag: bool
        Whether this image needs manual review.
    review_reason: str
        Semicolon-delimited review reasons.
    error: str
        Error message, if assessment failed.
    image_tag: str
        Image-content-derived D/N tag.
    median_luminance: str
        Median grayscale luminance in the central scene crop.
    mean_luminance: str
        Mean grayscale luminance in the central scene crop.
    dark_ratio: str
        Fraction of central-crop pixels below the dark-pixel threshold.
    image_width: str
        Observed image width in pixels.
    image_height: str
        Observed image height in pixels.
    expected_width: str
        Expected image width in pixels.
    expected_height: str
        Expected image height in pixels.
    resolution_valid: str
        Whether observed and expected resolutions match exactly.
    blur_score: str
        ``skimage.measure.blur_effect`` score in ``[0, 1]``. Higher = blurrier.
    blur_threshold: str
        Score threshold above which the image is considered blurred.
    blur_valid: str
        Whether the image is sharper than the threshold. Empty for night images
        where blur evaluation is suppressed.
    """

    path: str
    filename: str
    checks_run: str
    review_flag: bool
    review_reason: str
    error: str
    image_tag: str
    median_luminance: str
    mean_luminance: str
    dark_ratio: str
    image_width: str
    image_height: str
    expected_width: str
    expected_height: str
    resolution_valid: str
    blur_score: str
    blur_threshold: str
    blur_valid: str


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the standalone image-assessment CLI parser.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser.
    """

    parser = argparse.ArgumentParser(
        description="Run reusable image assessment checks on files or directories.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Image files or non-recursive image directories to assess.",
    )
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=AVAILABLE_CHECKS,
        help="Checks to run. Default: all checks.",
    )
    parser.add_argument(
        "--blur-threshold",
        type=float,
        help=(f"Blur-effect score above which an image is flagged as blurred. Default: {BLUR_THRESHOLD}."),
    )
    return parser


def expand_input_paths(paths: Sequence[Path]) -> list[Path]:
    """Expand file and directory inputs into image paths.

    Parameters
    ----------
    paths: Sequence[Path]
        Input file or directory paths.

    Returns
    -------
    list[Path]
        Expanded paths. Directory expansion is non-recursive.
    """

    expanded_paths: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded_paths.extend(
                sorted(
                    child for child in path.iterdir() if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS
                )
            )
        else:
            expanded_paths.append(path)
    return expanded_paths


def get_image_size(image_path: Path) -> tuple[int, int]:
    """Read an image size from disk.

    Parameters
    ----------
    image_path: Path
        Image path.

    Returns
    -------
    tuple[int, int]
        Image width and height in pixels.

    Raises
    ------
    RuntimeError
        If the path cannot be decoded as an image.
    """

    try:
        with Image.open(image_path) as image:
            return image.size
    except (UnidentifiedImageError, OSError) as error:
        raise RuntimeError(str(error)) from error


def build_error_record(
    image_path: Path,
    checks: Sequence[AssessmentCheck],
    review_reason: str,
    error: str,
    *,
    blur_threshold: float,
) -> ImageAssessmentRecord:
    """Build a failed assessment record.

    Parameters
    ----------
    image_path: Path
        Image path.
    checks: Sequence[AssessmentCheck]
        Checks requested for this image.
    review_reason: str
        Review reason to report.
    error: str
        Error message.
    blur_threshold: float
        Blur-effect threshold echoed into the record for traceability.

    Returns
    -------
    ImageAssessmentRecord
        Failed assessment record.
    """

    return ImageAssessmentRecord(
        path=str(image_path),
        filename=image_path.name,
        checks_run=";".join(checks),
        review_flag=True,
        review_reason=review_reason,
        error=error,
        image_tag="",
        median_luminance="",
        mean_luminance="",
        dark_ratio="",
        image_width="",
        image_height="",
        expected_width=str(IMAGE_WIDTH) if "resolution" in checks else "",
        expected_height=str(IMAGE_HEIGHT) if "resolution" in checks else "",
        resolution_valid="",
        blur_score="",
        blur_threshold=f"{blur_threshold}" if "blur" in checks else "",
        blur_valid="",
    )


def assess_image_path(
    image_path: Path,
    checks: Sequence[AssessmentCheck],
    *,
    blur_threshold: float,
) -> ImageAssessmentRecord:
    """Assess one local image path.

    Parameters
    ----------
    image_path: Path
        Image path.
    checks: Sequence[AssessmentCheck]
        Checks to run.
    blur_threshold: float
        Blur-effect score above which the image is flagged as blurred.

    Returns
    -------
    ImageAssessmentRecord
        Assessment record.
    """

    if not image_path.exists():
        return build_error_record(
            image_path,
            checks,
            review_reason="path_not_found",
            error="Path does not exist",
            blur_threshold=blur_threshold,
        )
    if not image_path.is_file():
        return build_error_record(
            image_path,
            checks,
            review_reason="not_a_file",
            error="Path is not a file",
            blur_threshold=blur_threshold,
        )

    review_reasons: list[str] = []
    image_tag = ""
    median_luminance = ""
    mean_luminance = ""
    dark_ratio = ""
    image_width = ""
    image_height = ""
    resolution_valid = ""
    blur_score = ""
    blur_valid = ""

    if "day_night" in checks:
        try:
            day_night_assessment = assess_day_night_from_image_bytes(
                image_path.read_bytes(),
                night_median_threshold=NIGHT_MEDIAN_THRESHOLD,
                night_dark_ratio_threshold=NIGHT_DARK_RATIO_THRESHOLD,
                dark_pixel_threshold=DARK_PIXEL_THRESHOLD,
            )
        except (OSError, RuntimeError) as error:
            return build_error_record(
                image_path,
                checks,
                review_reason="invalid_image",
                error=str(error),
                blur_threshold=blur_threshold,
            )
        image_tag = day_night_assessment.image_tag
        median_luminance = f"{day_night_assessment.median_luminance:.4f}"
        mean_luminance = f"{day_night_assessment.mean_luminance:.4f}"
        dark_ratio = f"{day_night_assessment.dark_ratio:.6f}"
        image_width = str(day_night_assessment.image_width)
        image_height = str(day_night_assessment.image_height)

    if not image_tag:
        if image_path.stem.endswith("_N"):
            image_tag = "N"
        elif image_path.stem.endswith("_D"):
            image_tag = "D"

    if "resolution" in checks:
        if image_width and image_height:
            width = int(image_width)
            height = int(image_height)
        else:
            try:
                width, height = get_image_size(image_path)
            except RuntimeError as error:
                return build_error_record(
                    image_path,
                    checks,
                    review_reason="invalid_image",
                    error=str(error),
                    blur_threshold=blur_threshold,
                )
            image_width = str(width)
            image_height = str(height)
        resolution_assessment = assess_resolution(
            width,
            height,
            expected_width=IMAGE_WIDTH,
            expected_height=IMAGE_HEIGHT,
        )
        resolution_valid = str(resolution_assessment.is_valid)
        if not resolution_assessment.is_valid:
            review_reasons.append("resolution_mismatch")

    if "blur" in checks and image_tag != "N":
        try:
            blur_assessment = assess_blur_from_image_bytes(
                image_path.read_bytes(),
                blur_threshold=blur_threshold,
            )
        except (OSError, RuntimeError) as error:
            return build_error_record(
                image_path,
                checks,
                review_reason="invalid_image",
                error=str(error),
                blur_threshold=blur_threshold,
            )
        blur_score = f"{blur_assessment.blur_score:.6f}"
        blur_valid = str(blur_assessment.is_sharp)
        if not blur_assessment.is_sharp:
            review_reasons.append("blurred")
        if not image_width and not image_height:
            image_width = str(blur_assessment.image_width)
            image_height = str(blur_assessment.image_height)

    return ImageAssessmentRecord(
        path=str(image_path),
        filename=image_path.name,
        checks_run=";".join(checks),
        review_flag=bool(review_reasons),
        review_reason=";".join(review_reasons),
        error="",
        image_tag=image_tag,
        median_luminance=median_luminance,
        mean_luminance=mean_luminance,
        dark_ratio=dark_ratio,
        image_width=image_width,
        image_height=image_height,
        expected_width=str(IMAGE_WIDTH) if "resolution" in checks else "",
        expected_height=str(IMAGE_HEIGHT) if "resolution" in checks else "",
        resolution_valid=resolution_valid,
        blur_score=blur_score,
        blur_threshold=f"{blur_threshold}" if "blur" in checks else "",
        blur_valid=blur_valid,
    )


def write_csv(records: Sequence[ImageAssessmentRecord]) -> None:
    """Write assessment records to stdout as CSV.

    Parameters
    ----------
    records: Sequence[ImageAssessmentRecord]
        Assessment records to write.
    """

    writer = csv.DictWriter(sys.stdout, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for record in records:
        writer.writerow(asdict(record))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the standalone image-assessment CLI.

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
    checks: tuple[AssessmentCheck, ...] = tuple(args.checks or AVAILABLE_CHECKS)
    blur_threshold = BLUR_THRESHOLD if args.blur_threshold is None else args.blur_threshold
    image_paths = expand_input_paths(args.paths)
    records = [assess_image_path(image_path, checks, blur_threshold=blur_threshold) for image_path in image_paths]
    write_csv(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
