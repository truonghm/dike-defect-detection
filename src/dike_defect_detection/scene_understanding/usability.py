"""General image usability checks for defect detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from dike_defect_detection.scene_understanding.metrics import SceneMetrics

SuitabilityStatus = Literal["ok", "maybe", "poor"]

MIN_SCORE = 0.0
MAX_SCORE = 1.0
SCORE_PRECISION = 4
USABLE_SURFACE_OK_RATIO = 0.25
USABLE_SURFACE_OK_LARGEST_COMPONENT_RATIO = 0.15
USABLE_SURFACE_MAYBE_RATIO = 0.12
USABLE_SURFACE_MAYBE_LARGEST_COMPONENT_RATIO = 0.06
DETECTION_USABLE_AREA_SCORE_WEIGHT = 0.45
DETECTION_USABLE_COMPONENT_SCORE_WEIGHT = 0.55


@dataclass(frozen=True, slots=True)
class SceneDecision:
    """Decision record for usability or synthesis suitability.

    Parameters
    ----------
    status: SuitabilityStatus
        Triage status: ``"ok"``, ``"maybe"``, or ``"poor"``.
    score: float
        Heuristic score in ``[0, 1]``.
    reasons: tuple[str, ...]
        Machine-readable decision reasons.
    """

    status: SuitabilityStatus
    score: float
    reasons: tuple[str, ...]


def clamp01(value: float) -> float:
    """Clamp a numeric value to the closed interval ``[0, 1]``."""

    return min(MAX_SCORE, max(MIN_SCORE, value))


def assess_detection_usability(metrics: SceneMetrics) -> SceneDecision:
    """Assess whether an image has enough usable surface for defect detection.

    Parameters
    ----------
    metrics: SceneMetrics
        Scene metrics.

    Returns
    -------
    SceneDecision
        General detection usability decision.
    """

    area_score = clamp01(metrics.usable_surface_area_ratio / USABLE_SURFACE_OK_RATIO)
    component_score = clamp01(
        metrics.usable_surface_largest_component_ratio / USABLE_SURFACE_OK_LARGEST_COMPONENT_RATIO
    )
    score = round(
        DETECTION_USABLE_AREA_SCORE_WEIGHT * area_score + DETECTION_USABLE_COMPONENT_SCORE_WEIGHT * component_score,
        SCORE_PRECISION,
    )
    reasons: list[str] = []

    if (
        metrics.usable_surface_area_ratio >= USABLE_SURFACE_OK_RATIO
        and metrics.usable_surface_largest_component_ratio >= USABLE_SURFACE_OK_LARGEST_COMPONENT_RATIO
    ):
        reasons.append("large_usable_surface")
        return SceneDecision(status="ok", score=score, reasons=tuple(reasons))

    if (
        metrics.usable_surface_area_ratio >= USABLE_SURFACE_MAYBE_RATIO
        or metrics.usable_surface_largest_component_ratio >= USABLE_SURFACE_MAYBE_LARGEST_COMPONENT_RATIO
    ):
        if metrics.usable_surface_largest_component_ratio < USABLE_SURFACE_OK_LARGEST_COMPONENT_RATIO:
            reasons.append("usable_surface_fragmented_or_small")
        if metrics.usable_surface_area_ratio < USABLE_SURFACE_OK_RATIO:
            reasons.append("usable_surface_area_limited")
        return SceneDecision(status="maybe", score=score, reasons=tuple(reasons))

    reasons.append("insufficient_usable_surface")
    return SceneDecision(status="poor", score=score, reasons=tuple(reasons))
