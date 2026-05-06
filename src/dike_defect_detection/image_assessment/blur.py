"""Reusable image blur assessment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image, UnidentifiedImageError
from skimage.measure import blur_effect


@dataclass(frozen=True, slots=True)
class BlurAssessment:
    """Image blur assessment result.

    Parameters
    ----------
    blur_score: float
        ``skimage.measure.blur_effect`` score in ``[0, 1]``. Higher values
        indicate stronger perceived blur.
    blur_threshold: float
        Score threshold above which the image is considered blurred.
    is_sharp: bool
        Whether ``blur_score < blur_threshold``.
    image_width: int
        Original image width in pixels.
    image_height: int
        Original image height in pixels.
    """

    blur_score: float
    blur_threshold: float
    is_sharp: bool
    image_width: int
    image_height: int


def assess_blur_from_image_bytes(
    image_bytes: bytes,
    *,
    blur_threshold: float,
) -> BlurAssessment:
    """Estimate image blur with a no-reference perceptual metric.

    Parameters
    ----------
    image_bytes: bytes
        Raw image bytes.
    blur_threshold: float
        Score threshold above which the image is considered blurred.

    Returns
    -------
    BlurAssessment
        Blur metrics and sharpness flag.

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
    pixels = np.asarray(central_crop)

    blur_score = float(blur_effect(pixels))
    return BlurAssessment(
        blur_score=blur_score,
        blur_threshold=blur_threshold,
        is_sharp=blur_score < blur_threshold,
        image_width=image_width,
        image_height=image_height,
    )
