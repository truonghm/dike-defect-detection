"""Reusable day/night assessment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Literal

import numpy as np
from PIL import Image, UnidentifiedImageError

DayNightTag = Literal["D", "N"]


@dataclass(frozen=True, slots=True)
class DayNightImageAssessment:
    """Image luminance metrics used for day/night tagging.

    Parameters
    ----------
    image_tag: DayNightTag
        Image-content-derived day/night tag.
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
    """

    image_tag: DayNightTag
    median_luminance: float
    mean_luminance: float
    dark_ratio: float
    image_width: int
    image_height: int


def get_time_tag(
    captured_at: datetime,
    *,
    day_start_hour: int,
    day_end_hour: int,
) -> DayNightTag:
    """Infer the expected D/N tag from the local capture timestamp.

    Parameters
    ----------
    captured_at: datetime
        Local capture timestamp.
    day_start_hour: int
        Inclusive local hour when daytime begins.
    day_end_hour: int
        Exclusive local hour when daytime ends.

    Returns
    -------
    DayNightTag
        ``"D"`` if the timestamp is in the configured daytime interval,
        otherwise ``"N"``.
    """

    if day_start_hour <= captured_at.hour < day_end_hour:
        return "D"
    return "N"


def assess_day_night_from_image_bytes(
    image_bytes: bytes,
    *,
    night_median_threshold: float,
    night_dark_ratio_threshold: float,
    dark_pixel_threshold: int,
) -> DayNightImageAssessment:
    """Infer the observed D/N tag from image luminance.

    Parameters
    ----------
    image_bytes: bytes
        Raw image bytes.
    night_median_threshold: float
        Median luminance below which the image is tagged as night.
    night_dark_ratio_threshold: float
        Dark-pixel ratio above which the image is tagged as night.
    dark_pixel_threshold: int
        Luminance threshold used to count dark pixels.

    Returns
    -------
    DayNightImageAssessment
        Luminance metrics and image-content-derived D/N tag.

    Raises
    ------
    RuntimeError
        If ``image_bytes`` cannot be decoded as an image.
    """

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            grayscale_image = image.convert("L")
    except UnidentifiedImageError as error:
        raise RuntimeError("Image bytes are not a valid image") from error

    image_width, image_height = grayscale_image.size
    left = max(0, int(image_width * 0.05))
    top = max(0, int(image_height * 0.15))
    right = min(image_width, int(image_width * 0.95))
    bottom = min(image_height, int(image_height * 0.85))
    central_crop = grayscale_image.crop((left, top, right, bottom))
    pixels = np.asarray(central_crop, dtype=np.float32)

    median_luminance = float(np.median(pixels))
    mean_luminance = float(np.mean(pixels))
    dark_ratio = float(np.mean(pixels < dark_pixel_threshold))
    image_tag: DayNightTag = (
        "N" if median_luminance < night_median_threshold or dark_ratio > night_dark_ratio_threshold else "D"
    )
    return DayNightImageAssessment(
        image_tag=image_tag,
        median_luminance=median_luminance,
        mean_luminance=mean_luminance,
        dark_ratio=dark_ratio,
        image_width=image_width,
        image_height=image_height,
    )
