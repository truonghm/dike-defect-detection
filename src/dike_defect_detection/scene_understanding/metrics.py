"""Metrics computed from normalized scene group masks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.measure import label as connected_component_labels

from dike_defect_detection.scene_understanding.groups import SceneGroupMasks

CONNECTED_COMPONENT_CONNECTIVITY = 2


@dataclass(frozen=True, slots=True)
class SceneMetrics:
    """Scene metrics used for detection usability and synthesis suitability.

    Parameters
    ----------
    image_width: int
        Processed image width in pixels.
    image_height: int
        Processed image height in pixels.
    water_area_ratio: float
        Fraction of pixels assigned to water.
    soft_land_area_ratio: float
        Fraction of pixels assigned to soft land-like surfaces.
    hard_surface_area_ratio: float
        Fraction of pixels assigned to hard surfaces.
    road_path_area_ratio: float
        Fraction of pixels assigned to road/path-like surfaces.
    structure_area_ratio: float
        Fraction of pixels assigned to structure-like labels.
    vegetation_occluder_area_ratio: float
        Fraction of pixels assigned to tree/plant occluders.
    dynamic_occluder_area_ratio: float
        Fraction of pixels assigned to people/vehicles/boats.
    sky_area_ratio: float
        Fraction of pixels assigned to sky.
    overlay_excluded_ratio: float
        Fraction of pixels excluded by deterministic text-overlay boxes.
    usable_surface_area_ratio: float
        Fraction of pixels in usable inspection/synthesis target surfaces.
    usable_surface_largest_component_ratio: float
        Largest connected usable-surface component as a fraction of all pixels.
    soft_land_largest_component_ratio: float
        Largest connected soft-land component as a fraction of all pixels.
    road_path_largest_component_ratio: float
        Largest connected road/path component as a fraction of all pixels.
    structure_largest_component_ratio: float
        Largest connected structure component as a fraction of all pixels.
    water_land_boundary_length_px: int
        Number of usable land pixels adjacent to water.
    water_land_boundary_ratio: float
        Boundary length normalized by the larger image side.
    """

    image_width: int
    image_height: int
    water_area_ratio: float
    soft_land_area_ratio: float
    hard_surface_area_ratio: float
    road_path_area_ratio: float
    structure_area_ratio: float
    vegetation_occluder_area_ratio: float
    dynamic_occluder_area_ratio: float
    sky_area_ratio: float
    overlay_excluded_ratio: float
    usable_surface_area_ratio: float
    usable_surface_largest_component_ratio: float
    soft_land_largest_component_ratio: float
    road_path_largest_component_ratio: float
    structure_largest_component_ratio: float
    water_land_boundary_length_px: int
    water_land_boundary_ratio: float


def area_ratio(mask: np.ndarray) -> float:
    """Compute the fraction of true pixels in a mask."""

    return float(np.mean(mask))


def largest_component_area_ratio(mask: np.ndarray) -> float:
    """Compute the largest connected component area ratio for a mask."""

    if not bool(np.any(mask)):
        return 0.0
    components = connected_component_labels(mask, connectivity=CONNECTED_COMPONENT_CONNECTIVITY)
    counts = np.bincount(components.ravel())
    if len(counts) <= 1:
        return 0.0
    return float(np.max(counts[1:]) / mask.size)


def dilate_four_connected(mask: np.ndarray) -> np.ndarray:
    """Dilate a boolean mask by one pixel with 4-connectivity."""

    dilated = mask.copy()
    dilated[1:, :] |= mask[:-1, :]
    dilated[:-1, :] |= mask[1:, :]
    dilated[:, 1:] |= mask[:, :-1]
    dilated[:, :-1] |= mask[:, 1:]
    return dilated


def compute_water_land_boundary_length(water_mask: np.ndarray, land_mask: np.ndarray) -> int:
    """Count land pixels adjacent to water.

    Parameters
    ----------
    water_mask: np.ndarray
        Boolean water mask.
    land_mask: np.ndarray
        Boolean candidate land mask.

    Returns
    -------
    int
        Number of candidate land pixels adjacent to water.
    """

    return int(np.sum(dilate_four_connected(water_mask) & land_mask))


def compute_scene_metrics(group_masks: SceneGroupMasks) -> SceneMetrics:
    """Compute scene metrics from normalized scene group masks.

    Parameters
    ----------
    group_masks: SceneGroupMasks
        Scene group masks.

    Returns
    -------
    SceneMetrics
        Metrics used by downstream decisions.
    """

    masks = group_masks.masks
    height, width = masks["water"].shape
    water_land_boundary_length = compute_water_land_boundary_length(masks["water"], masks["usable_surface"])
    return SceneMetrics(
        image_width=width,
        image_height=height,
        water_area_ratio=area_ratio(masks["water"]),
        soft_land_area_ratio=area_ratio(masks["soft_land"]),
        hard_surface_area_ratio=area_ratio(masks["hard_surface"]),
        road_path_area_ratio=area_ratio(masks["road_path"]),
        structure_area_ratio=area_ratio(masks["structure"]),
        vegetation_occluder_area_ratio=area_ratio(masks["vegetation_occluder"]),
        dynamic_occluder_area_ratio=area_ratio(masks["dynamic_occluder"]),
        sky_area_ratio=area_ratio(masks["sky"]),
        overlay_excluded_ratio=area_ratio(masks["overlay"]),
        usable_surface_area_ratio=area_ratio(masks["usable_surface"]),
        usable_surface_largest_component_ratio=largest_component_area_ratio(masks["usable_surface"]),
        soft_land_largest_component_ratio=largest_component_area_ratio(masks["soft_land"] & ~masks["exclude"]),
        road_path_largest_component_ratio=largest_component_area_ratio(masks["road_path"] & ~masks["exclude"]),
        structure_largest_component_ratio=largest_component_area_ratio(masks["structure"] & ~masks["exclude"]),
        water_land_boundary_length_px=water_land_boundary_length,
        water_land_boundary_ratio=float(water_land_boundary_length / max(width, height)),
    )
