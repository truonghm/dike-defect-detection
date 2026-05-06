from __future__ import annotations

import argparse
import math
import random
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ImageSample:
    """Summary of a single image's metadata and quality metrics.

    Parameters
    ----------
    path
        File path for the image.
    width_px
        Image width in pixels.
    height_px
        Image height in pixels.
    relative_altitude_m
        Relative altitude extracted from XMP, in meters.
    calibrated_focal_px
        Calibrated focal length from XMP, in pixels.
    gsd_mm_per_px
        Estimated ground sampling distance in millimeters per pixel.
    sharpness_var_laplacian
        Variance of Laplacian (higher is sharper).
    """

    path: Path
    width_px: int
    height_px: int
    relative_altitude_m: float | None
    calibrated_focal_px: float | None
    gsd_mm_per_px: float | None
    sharpness_var_laplacian: float


def _rational_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        if value.denominator == 0:
            return None
        return float(value.numerator) / float(value.denominator)
    if isinstance(value, tuple) and len(value) == 2:
        num, den = value
        if den == 0:
            return None
        return float(num) / float(den)
    return None


def _extract_xmp_block(data: bytes) -> str | None:
    start = data.find(b"<x:xmpmeta")
    if start == -1:
        return None
    end = data.find(b"</x:xmpmeta>", start)
    if end == -1:
        return None
    return data[start : end + len(b"</x:xmpmeta>")].decode("utf-8", errors="ignore")


def _find_xmp_number(xmp: str, key: str) -> float | None:
    patterns = (
        rf"{key}=&quot;([+-]?[0-9]*\.?[0-9]+)&quot;",
        rf"{key}=\"([+-]?[0-9]*\.?[0-9]+)\"",
        rf"<{key}[^>]*>([+-]?[0-9]*\.?[0-9]+)</",
        rf"<[^>]*:{key}[^>]*>([+-]?[0-9]*\.?[0-9]+)</",
        rf"{key}=([+-]?[0-9]*\.?[0-9]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, xmp)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


def _variance_of_laplacian(gray: np.ndarray) -> float:
    padded = np.pad(gray, ((1, 1), (1, 1)), mode="edge")
    center = padded[1:-1, 1:-1]
    lap = -4.0 * center + padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:]
    return float(lap.var())


def _collect_images(path: Path) -> list[Path]:
    exts = {".jpg", ".jpeg"}
    return sorted([p for p in path.iterdir() if p.is_file() and p.suffix.lower() in exts])


def _pick_sample(paths: list[Path], sample_rate: float) -> list[Path]:
    if sample_rate >= 1.0:
        return paths
    sample_size = max(1, int(math.ceil(len(paths) * sample_rate)))
    return random.sample(paths, sample_size)


def _read_sample(path: Path) -> ImageSample:
    with Image.open(path) as image:
        width, height = image.size

        gray = image.convert("L")
        scale_width = 1024
        if gray.width > scale_width:
            scale_height = int(scale_width * gray.height / gray.width)
            gray = gray.resize((scale_width, scale_height), Image.Resampling.LANCZOS)
        gray_array = np.asarray(gray, dtype=np.float32)
        sharpness = _variance_of_laplacian(gray_array)

    data = path.read_bytes()
    xmp = _extract_xmp_block(data)
    relative_altitude_m = _find_xmp_number(xmp, "RelativeAltitude") if xmp else None
    calibrated_focal_px = _find_xmp_number(xmp, "CalibratedFocalLength") if xmp else None

    gsd_mm_per_px = None
    if relative_altitude_m is not None and calibrated_focal_px:
        gsd_mm_per_px = (relative_altitude_m * 1000.0) / calibrated_focal_px

    return ImageSample(
        path=path,
        width_px=width,
        height_px=height,
        relative_altitude_m=relative_altitude_m,
        calibrated_focal_px=calibrated_focal_px,
        gsd_mm_per_px=gsd_mm_per_px,
        sharpness_var_laplacian=sharpness,
    )


def _format_value(value: float | None, precision: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{precision}f}"


def _summary_stats(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample UAV images and extract metadata and sharpness.")
    parser.add_argument(
        "--path",
        type=Path,
        required=True,
        help="Directory containing images to analyze.",
    )
    parser.add_argument(
        "--sample",
        type=float,
        default=None,
        help="Sample rate in (0, 1]; defaults to 1.0 or 0.1 if >=30 images.",
    )
    return parser.parse_args()


def main() -> None:
    """Run analysis for a directory of UAV images.

    Returns
    -------
    None
    """
    args = _parse_args()
    image_dir = args.path
    if not image_dir.exists() or not image_dir.is_dir():
        raise SystemExit(f"Path is not a directory: {image_dir}")

    images = _collect_images(image_dir)
    if not images:
        raise SystemExit(f"No JPG/JPEG images found in {image_dir}")

    sample_rate: float
    if args.sample is None:
        sample_rate = 0.1 if len(images) >= 30 else 1.0
    else:
        sample_rate = args.sample
    if not (0.0 < sample_rate <= 1.0):
        raise SystemExit("--sample must be in (0, 1]")

    sampled = _pick_sample(images, sample_rate)
    samples = [_read_sample(path) for path in sampled]

    for sample in samples:
        print(
            f"{sample.path.name}\t"
            f"{sample.width_px}x{sample.height_px}\t"
            f"RelAlt={_format_value(sample.relative_altitude_m)}\t"
            f"CalFocalPx={_format_value(sample.calibrated_focal_px)}\t"
            f"GSD(mm/px)={_format_value(sample.gsd_mm_per_px)}\t"
            f"LaplacianVar={sample.sharpness_var_laplacian:.2f}"
        )

    gsd_values = [s.gsd_mm_per_px for s in samples if s.gsd_mm_per_px is not None]
    alt_values = [s.relative_altitude_m for s in samples if s.relative_altitude_m is not None]
    sharpness_values = [s.sharpness_var_laplacian for s in samples]

    print("\nSummary")
    print(f"Images total: {len(images)}")
    print(f"Images sampled: {len(samples)} (sample rate {sample_rate:.2f})")
    print(f"Unique resolutions: {sorted({(s.width_px, s.height_px) for s in samples})}")

    if gsd_values:
        stats = _summary_stats(gsd_values)
        print(
            "GSD(mm/px): "
            f"min={stats['min']:.2f}, max={stats['max']:.2f}, "
            f"mean={stats['mean']:.2f}, median={stats['median']:.2f}"
        )
    else:
        print("GSD(mm/px): n/a")

    if alt_values:
        stats = _summary_stats(alt_values)
        print(
            "RelAlt(m): "
            f"min={stats['min']:.2f}, max={stats['max']:.2f}, "
            f"mean={stats['mean']:.2f}, median={stats['median']:.2f}"
        )
    else:
        print("RelAlt(m): n/a")

    if sharpness_values:
        stats = _summary_stats(sharpness_values)
        print(
            "LaplacianVar: "
            f"min={stats['min']:.2f}, max={stats['max']:.2f}, "
            f"mean={stats['mean']:.2f}, median={stats['median']:.2f}"
        )


if __name__ == "__main__":
    main()
