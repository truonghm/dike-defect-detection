"""Scene label metadata for OneFormer-based scene understanding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Color = tuple[int, int, int]
FALLBACK_COLOR_SEED_OFFSET = 1009
FALLBACK_COLOR_MIN_VALUE = 60
FALLBACK_COLOR_MAX_VALUE_EXCLUSIVE = 230
FALLBACK_COLOR_CHANNEL_COUNT = 3

SceneGroup = Literal[
    "water",
    "soft_land",
    "hard_surface",
    "road_path",
    "structure",
    "vegetation_occluder",
    "dynamic_occluder",
    "sky",
    "overlay",
    "exclude",
    "usable_surface",
]


@dataclass(frozen=True, slots=True)
class LabelSummary:
    """Area summary for one semantic label in a predicted mask.

    Parameters
    ----------
    label_id: int
        Numeric model label identifier.
    label: str
        Human-readable label name.
    area_ratio: float
        Fraction of image pixels assigned to this label.
    color: Color
        RGB color used for visual overlays.
    """

    label_id: int
    label: str
    area_ratio: float
    color: Color


SCENE_GROUPS: tuple[SceneGroup, ...] = (
    "water",
    "soft_land",
    "hard_surface",
    "road_path",
    "structure",
    "vegetation_occluder",
    "dynamic_occluder",
    "sky",
    "overlay",
    "exclude",
    "usable_surface",
)

COLOR_BY_LABEL: dict[str, Color] = {
    "sky": (135, 206, 235),
    "sea": (40, 110, 220),
    "water": (40, 110, 220),
    "river": (40, 110, 220),
    "grass": (70, 170, 70),
    "tree": (20, 100, 40),
    "plant": (45, 140, 60),
    "palm, palm tree": (25, 110, 45),
    "earth, ground": (150, 105, 70),
    "sand": (220, 190, 120),
    "field": (135, 165, 80),
    "dirt track": (140, 115, 85),
    "road, route": (120, 120, 120),
    "path": (150, 150, 150),
    "wall": (150, 90, 180),
    "building": (220, 130, 60),
    "house": (230, 150, 80),
    "bridge, span": (200, 60, 60),
    "grandstand, covered stand": (175, 80, 145),
    "pier": (130, 105, 90),
    "stairway, staircase": (135, 135, 135),
    "bannister, banister, balustrade, balusters, handrail": (170, 160, 150),
    "rock, stone": (115, 105, 95),
    "mountain, mount": (125, 130, 95),
    "signboard, sign": (245, 215, 70),
    "person": (245, 85, 85),
    "car": (245, 110, 110),
    "truck": (210, 80, 80),
    "minibike, motorbike": (190, 70, 70),
    "boat": (90, 170, 220),
}

GROUPS_BY_LABEL: dict[str, tuple[SceneGroup, ...]] = {
    "sea": ("water",),
    "water": ("water",),
    "river": ("water",),
    "grass": ("soft_land",),
    "earth, ground": ("soft_land",),
    "sand": ("soft_land",),
    "field": ("soft_land",),
    "dirt track": ("soft_land", "road_path"),
    "road, route": ("hard_surface", "road_path"),
    "path": ("hard_surface", "road_path"),
    "wall": ("hard_surface", "structure"),
    "rock, stone": ("hard_surface",),
    "building": ("structure",),
    "house": ("structure",),
    "bridge, span": ("hard_surface", "structure"),
    "grandstand, covered stand": ("hard_surface", "structure"),
    "pier": ("hard_surface", "structure"),
    "stairway, staircase": ("hard_surface", "structure"),
    "bannister, banister, balustrade, balusters, handrail": ("structure",),
    "fence": ("structure",),
    "tree": ("vegetation_occluder",),
    "plant": ("vegetation_occluder",),
    "palm, palm tree": ("vegetation_occluder",),
    "sky": ("sky",),
    "person": ("dynamic_occluder",),
    "car": ("dynamic_occluder",),
    "truck": ("dynamic_occluder",),
    "bus": ("dynamic_occluder",),
    "minibike, motorbike": ("dynamic_occluder",),
    "bicycle": ("dynamic_occluder",),
    "boat": ("dynamic_occluder",),
}


def fallback_color(label_id: int) -> Color:
    """Generate a deterministic fallback color for an unknown label.

    Parameters
    ----------
    label_id: int
        Numeric model label identifier.

    Returns
    -------
    Color
        Deterministic RGB color.
    """

    import numpy as np

    rng = np.random.default_rng(label_id + FALLBACK_COLOR_SEED_OFFSET)
    values = rng.integers(
        FALLBACK_COLOR_MIN_VALUE,
        FALLBACK_COLOR_MAX_VALUE_EXCLUSIVE,
        size=FALLBACK_COLOR_CHANNEL_COUNT,
    )
    return int(values[0]), int(values[1]), int(values[2])


def get_label_color(label_id: int, label: str) -> Color:
    """Get the RGB overlay color for a model label.

    Parameters
    ----------
    label_id: int
        Numeric model label identifier.
    label: str
        Human-readable label name.

    Returns
    -------
    Color
        RGB color.
    """

    color = COLOR_BY_LABEL.get(label.lower())
    if color is not None:
        return color
    return fallback_color(label_id)


def get_scene_groups(label: str) -> tuple[SceneGroup, ...]:
    """Map a model label name to one or more scene groups.

    Parameters
    ----------
    label: str
        Human-readable model label.

    Returns
    -------
    tuple[SceneGroup, ...]
        Scene groups assigned to the label.
    """

    return GROUPS_BY_LABEL.get(label.lower(), ())
