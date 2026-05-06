"""Calibrate the blur threshold from a directory of representative images."""

# TODO: implement separate blur thresholds for day and night images.

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from dike_defect_detection.image_assessment.blur import assess_blur_from_image_bytes
from dike_defect_detection.image_assessment.constants import BLUR_THRESHOLD, IMAGE_EXTENSIONS
from dike_defect_detection.image_assessment.metadata import load_image_tag_metadata

DEFAULT_PERCENTILE = 95.0


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the calibrate-blur-threshold CLI parser.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Calibrate a blur threshold by computing per-image blur scores in a "
            "representative directory and printing a high percentile of the "
            "distribution. If camera_capture_log.csv is present, images tagged "
            "as night are skipped, since the current threshold applies to day "
            "images only."
        ),
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory of representative images. Non-recursive.",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        help=(f"Percentile of the blur-score distribution used as the threshold. Default: {DEFAULT_PERCENTILE}."),
    )
    return parser


def collect_blur_scores(directory: Path) -> list[float]:
    """Compute blur scores for day images in a directory.

    Parameters
    ----------
    directory: Path
        Directory of images. Non-recursive. If ``camera_capture_log.csv`` is
        present, images with ``image_tag`` equal to ``N`` are skipped. Filename
        suffixes are not parsed for day/night tags.

    Returns
    -------
    list[float]
        Blur scores for successfully scored day images.
    """

    image_tag_metadata = load_image_tag_metadata(directory)
    scores: list[float] = []
    for image_path in sorted(directory.iterdir()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if image_tag_metadata.get(image_path.name) == "N":
            continue
        try:
            assessment = assess_blur_from_image_bytes(
                image_path.read_bytes(),
                blur_threshold=BLUR_THRESHOLD,
            )
        except (OSError, RuntimeError) as error:
            print(f"skipped {image_path.name}: {error}", file=sys.stderr)
            continue
        scores.append(assessment.blur_score)
    return scores


def main(argv: Sequence[str] | None = None) -> int:
    """Run the calibrate-blur-threshold CLI.

    Parameters
    ----------
    argv: Sequence[str] | None
        CLI arguments excluding the executable name. If omitted, arguments are
        read from ``sys.argv``.

    Returns
    -------
    int
        Process exit code. ``0`` on success, ``1`` when no images could be
        scored.
    """

    parser = build_argument_parser()
    args = parser.parse_args(argv)
    percentile = DEFAULT_PERCENTILE if args.percentile is None else args.percentile
    if not 0.0 < percentile <= 100.0:
        parser.error("--percentile must be in (0, 100]")
    if not args.directory.is_dir():
        parser.error(f"directory does not exist: {args.directory}")

    try:
        scores = collect_blur_scores(args.directory)
    except ValueError as error:
        parser.error(str(error))
    if not scores:
        print("no scoreable day images in directory", file=sys.stderr)
        return 1

    threshold = float(np.percentile(scores, percentile))
    print(f"scored {len(scores)} images", file=sys.stderr)
    print(f"{threshold:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
