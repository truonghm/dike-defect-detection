"""Deterministic exclusion masks for camera text overlays."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TIMESTAMP_X_MIN_RATIO = 0.62
TIMESTAMP_Y_MAX_RATIO = 0.14
SITE_NAME_X_MAX_RATIO = 0.58
SITE_NAME_Y_MIN_RATIO = 0.86


@dataclass(frozen=True, slots=True)
class OverlayExclusionConfig:
    """Relative camera-overlay exclusion boxes.

    Parameters
    ----------
    timestamp_x_min: float
        Left x-coordinate ratio for the top-right timestamp box.
    timestamp_y_max: float
        Bottom y-coordinate ratio for the top-right timestamp box.
    site_name_x_max: float
        Right x-coordinate ratio for the bottom-left site-name box.
    site_name_y_min: float
        Top y-coordinate ratio for the bottom-left site-name box.
    """

    timestamp_x_min: float = TIMESTAMP_X_MIN_RATIO
    timestamp_y_max: float = TIMESTAMP_Y_MAX_RATIO
    site_name_x_max: float = SITE_NAME_X_MAX_RATIO
    site_name_y_min: float = SITE_NAME_Y_MIN_RATIO


DEFAULT_OVERLAY_EXCLUSION_CONFIG = OverlayExclusionConfig()


def build_overlay_exclusion_mask(
    height: int,
    width: int,
    config: OverlayExclusionConfig = DEFAULT_OVERLAY_EXCLUSION_CONFIG,
) -> np.ndarray:
    """Build an approximate text-overlay exclusion mask.

    Parameters
    ----------
    height: int
        Image height in pixels.
    width: int
        Image width in pixels.
    config: OverlayExclusionConfig
        Relative exclusion box configuration.

    Returns
    -------
    np.ndarray
        Boolean mask where ``True`` means excluded overlay pixels.
    """

    mask = np.zeros((height, width), dtype=bool)
    timestamp_x0 = min(width, max(0, int(round(width * config.timestamp_x_min))))
    timestamp_y1 = min(height, max(0, int(round(height * config.timestamp_y_max))))
    site_name_x1 = min(width, max(0, int(round(width * config.site_name_x_max))))
    site_name_y0 = min(height, max(0, int(round(height * config.site_name_y_min))))

    mask[:timestamp_y1, timestamp_x0:] = True
    mask[site_name_y0:, :site_name_x1] = True
    return mask
