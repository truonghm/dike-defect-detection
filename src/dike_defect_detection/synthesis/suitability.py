"""Class-specific synthesis suitability rules."""

from __future__ import annotations

from typing import Literal

from dike_defect_detection.scene_understanding.metrics import SceneMetrics
from dike_defect_detection.scene_understanding.usability import SCORE_PRECISION, SceneDecision, clamp01

DefectClass = Literal["erosion", "vegetation", "seepage", "structure_damage", "settlement"]

EROSION_OK_WATER_RATIO = 0.03
EROSION_OK_BOUNDARY_RATIO = 0.10
EROSION_MAYBE_WATER_RATIO = 0.015
EROSION_MAYBE_BOUNDARY_RATIO = 0.04
EROSION_WATER_SCORE_WEIGHT = 0.45
EROSION_BOUNDARY_SCORE_WEIGHT = 0.55

VEGETATION_OK_SOFT_LAND_RATIO = 0.12
VEGETATION_OK_COMPONENT_RATIO = 0.08
VEGETATION_MAYBE_SOFT_LAND_RATIO = 0.05
VEGETATION_AREA_SCORE_WEIGHT = 0.55
VEGETATION_COMPONENT_SCORE_WEIGHT = 0.45

SEEPAGE_OK_SOFT_LAND_RATIO = 0.12
SEEPAGE_OK_COMPONENT_RATIO = 0.08
SEEPAGE_MAYBE_SOFT_LAND_RATIO = 0.05
SEEPAGE_MAX_ROAD_PATH_RATIO = 0.45
SEEPAGE_AREA_SCORE_WEIGHT = 0.55
SEEPAGE_COMPONENT_SCORE_WEIGHT = 0.45
SEEPAGE_BASE_SCORE_MULTIPLIER = 1.0
SEEPAGE_ROAD_PENALTY_WEIGHT = 0.35

STRUCTURE_DAMAGE_OK_RATIO = 0.06
STRUCTURE_DAMAGE_MAYBE_RATIO = 0.025

SETTLEMENT_OK_ROAD_PATH_RATIO = 0.15
SETTLEMENT_OK_COMPONENT_RATIO = 0.10
SETTLEMENT_MAYBE_COMPONENT_RATIO = 0.05
SETTLEMENT_AREA_SCORE_WEIGHT = 0.45
SETTLEMENT_COMPONENT_SCORE_WEIGHT = 0.55


def assess_synthesis_suitability(metrics: SceneMetrics) -> dict[DefectClass, SceneDecision]:
    """Assess per-class synthesis suitability from scene metrics.

    Parameters
    ----------
    metrics: SceneMetrics
        Scene metrics.

    Returns
    -------
    dict[DefectClass, SceneDecision]
        Synthesis suitability decisions keyed by defect class.
    """

    return {
        "erosion": assess_erosion_suitability(metrics),
        "vegetation": assess_vegetation_suitability(metrics),
        "seepage": assess_seepage_suitability(metrics),
        "structure_damage": assess_structure_damage_suitability(metrics),
        "settlement": assess_settlement_suitability(metrics),
    }


def assess_erosion_suitability(metrics: SceneMetrics) -> SceneDecision:
    """Assess suitability for erosion synthesis."""

    water_score = clamp01(metrics.water_area_ratio / EROSION_OK_WATER_RATIO)
    boundary_score = clamp01(metrics.water_land_boundary_ratio / EROSION_OK_BOUNDARY_RATIO)
    score = round(
        EROSION_WATER_SCORE_WEIGHT * water_score + EROSION_BOUNDARY_SCORE_WEIGHT * boundary_score,
        SCORE_PRECISION,
    )
    reasons: list[str] = []

    if metrics.water_area_ratio >= EROSION_OK_WATER_RATIO:
        reasons.append("water_present")
    if metrics.water_land_boundary_ratio >= EROSION_OK_BOUNDARY_RATIO:
        reasons.append("land_water_boundary_sufficient")
    if len(reasons) == 2:
        return SceneDecision(status="ok", score=score, reasons=tuple(reasons))

    if (
        metrics.water_area_ratio >= EROSION_MAYBE_WATER_RATIO
        or metrics.water_land_boundary_ratio >= EROSION_MAYBE_BOUNDARY_RATIO
    ):
        if metrics.water_area_ratio < EROSION_OK_WATER_RATIO:
            reasons.append("water_area_limited")
        if metrics.water_land_boundary_ratio < EROSION_OK_BOUNDARY_RATIO:
            reasons.append("land_water_boundary_limited")
        return SceneDecision(status="maybe", score=score, reasons=tuple(reasons))

    return SceneDecision(status="poor", score=score, reasons=("no_clear_waterline",))


def assess_vegetation_suitability(metrics: SceneMetrics) -> SceneDecision:
    """Assess suitability for vegetation encroachment synthesis."""

    area_score = clamp01(metrics.soft_land_area_ratio / VEGETATION_OK_SOFT_LAND_RATIO)
    component_score = clamp01(metrics.soft_land_largest_component_ratio / VEGETATION_OK_COMPONENT_RATIO)
    score = round(
        VEGETATION_AREA_SCORE_WEIGHT * area_score + VEGETATION_COMPONENT_SCORE_WEIGHT * component_score,
        SCORE_PRECISION,
    )
    if (
        metrics.soft_land_area_ratio >= VEGETATION_OK_SOFT_LAND_RATIO
        and metrics.soft_land_largest_component_ratio >= VEGETATION_OK_COMPONENT_RATIO
    ):
        return SceneDecision(status="ok", score=score, reasons=("land_surface_sufficient",))
    if metrics.soft_land_area_ratio >= VEGETATION_MAYBE_SOFT_LAND_RATIO:
        return SceneDecision(status="maybe", score=score, reasons=("land_surface_limited",))
    return SceneDecision(status="poor", score=score, reasons=("land_surface_insufficient",))


def assess_seepage_suitability(metrics: SceneMetrics) -> SceneDecision:
    """Assess suitability for seepage or sand-boil synthesis."""

    area_score = clamp01(metrics.soft_land_area_ratio / SEEPAGE_OK_SOFT_LAND_RATIO)
    component_score = clamp01(metrics.soft_land_largest_component_ratio / SEEPAGE_OK_COMPONENT_RATIO)
    road_penalty = clamp01(metrics.road_path_area_ratio / SEEPAGE_MAX_ROAD_PATH_RATIO)
    score = round(
        clamp01(
            (SEEPAGE_AREA_SCORE_WEIGHT * area_score + SEEPAGE_COMPONENT_SCORE_WEIGHT * component_score)
            * (SEEPAGE_BASE_SCORE_MULTIPLIER - SEEPAGE_ROAD_PENALTY_WEIGHT * road_penalty)
        ),
        SCORE_PRECISION,
    )

    if (
        metrics.soft_land_area_ratio >= SEEPAGE_OK_SOFT_LAND_RATIO
        and metrics.soft_land_largest_component_ratio >= SEEPAGE_OK_COMPONENT_RATIO
        and metrics.road_path_area_ratio <= SEEPAGE_MAX_ROAD_PATH_RATIO
    ):
        return SceneDecision(status="ok", score=score, reasons=("soft_land_surface_sufficient",))
    if metrics.soft_land_area_ratio >= SEEPAGE_MAYBE_SOFT_LAND_RATIO:
        reasons = ["soft_land_surface_limited"]
        if metrics.road_path_area_ratio > SEEPAGE_MAX_ROAD_PATH_RATIO:
            reasons.append("road_surface_dominant")
        return SceneDecision(status="maybe", score=score, reasons=tuple(reasons))
    return SceneDecision(status="poor", score=score, reasons=("soft_land_surface_insufficient",))


def assess_structure_damage_suitability(metrics: SceneMetrics) -> SceneDecision:
    """Assess suitability for structure-damage synthesis."""

    score = round(clamp01(metrics.structure_area_ratio / STRUCTURE_DAMAGE_OK_RATIO), SCORE_PRECISION)
    if metrics.structure_area_ratio >= STRUCTURE_DAMAGE_OK_RATIO:
        return SceneDecision(status="ok", score=score, reasons=("structure_surface_sufficient",))
    if metrics.structure_area_ratio >= STRUCTURE_DAMAGE_MAYBE_RATIO:
        return SceneDecision(status="maybe", score=score, reasons=("structure_surface_limited",))
    return SceneDecision(status="poor", score=score, reasons=("structure_surface_insufficient",))


def assess_settlement_suitability(metrics: SceneMetrics) -> SceneDecision:
    """Assess suitability for settlement synthesis."""

    area_score = clamp01(metrics.road_path_area_ratio / SETTLEMENT_OK_ROAD_PATH_RATIO)
    component_score = clamp01(metrics.road_path_largest_component_ratio / SETTLEMENT_OK_COMPONENT_RATIO)
    score = round(
        SETTLEMENT_AREA_SCORE_WEIGHT * area_score + SETTLEMENT_COMPONENT_SCORE_WEIGHT * component_score,
        SCORE_PRECISION,
    )
    if (
        metrics.road_path_area_ratio >= SETTLEMENT_OK_ROAD_PATH_RATIO
        and metrics.road_path_largest_component_ratio >= SETTLEMENT_OK_COMPONENT_RATIO
    ):
        return SceneDecision(status="ok", score=score, reasons=("continuous_road_path_surface_sufficient",))
    if metrics.road_path_largest_component_ratio >= SETTLEMENT_MAYBE_COMPONENT_RATIO:
        return SceneDecision(status="maybe", score=score, reasons=("road_path_surface_limited",))
    return SceneDecision(status="poor", score=score, reasons=("road_path_surface_insufficient",))
