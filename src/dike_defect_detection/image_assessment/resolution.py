"""Reusable image resolution assessment helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolutionAssessment:
    """Image resolution validation result.

    Parameters
    ----------
    image_width: int
        Observed image width in pixels.
    image_height: int
        Observed image height in pixels.
    expected_width: int
        Expected image width in pixels.
    expected_height: int
        Expected image height in pixels.
    is_valid: bool
        Whether observed and expected resolutions match exactly.
    """

    image_width: int
    image_height: int
    expected_width: int
    expected_height: int
    is_valid: bool


def assess_resolution(
    image_width: int,
    image_height: int,
    *,
    expected_width: int,
    expected_height: int,
) -> ResolutionAssessment:
    """Validate an image resolution against an expected resolution.

    Parameters
    ----------
    image_width: int
        Observed image width in pixels.
    image_height: int
        Observed image height in pixels.
    expected_width: int
        Expected image width in pixels.
    expected_height: int
        Expected image height in pixels.

    Returns
    -------
    ResolutionAssessment
        Resolution validation result.
    """

    return ResolutionAssessment(
        image_width=image_width,
        image_height=image_height,
        expected_width=expected_width,
        expected_height=expected_height,
        is_valid=image_width == expected_width and image_height == expected_height,
    )
