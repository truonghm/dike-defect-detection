"""Scene group masks derived from semantic labels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from dike_defect_detection.scene_understanding.labels import SCENE_GROUPS, SceneGroup, get_scene_groups


@dataclass(frozen=True, slots=True)
class SceneGroupMasks:
    """Boolean masks for normalized scene groups.

    Parameters
    ----------
    masks: dict[SceneGroup, np.ndarray]
        Mapping from scene group name to boolean mask.
    """

    masks: dict[SceneGroup, np.ndarray]

    def get(self, group: SceneGroup) -> np.ndarray:
        """Return a group mask by name."""

        return self.masks[group]


def build_scene_group_masks(
    label_mask: np.ndarray,
    id_to_label: Mapping[int, str],
    overlay_mask: np.ndarray,
) -> SceneGroupMasks:
    """Build normalized scene group masks from a semantic label mask.

    Parameters
    ----------
    label_mask: np.ndarray
        Integer semantic label mask.
    id_to_label: Mapping[int, str]
        Label identifier to label name mapping.
    overlay_mask: np.ndarray
        Boolean text-overlay exclusion mask.

    Returns
    -------
    SceneGroupMasks
        Scene group masks.
    """

    masks = {group: np.zeros(label_mask.shape, dtype=bool) for group in SCENE_GROUPS}
    for raw_label_id in np.unique(label_mask):
        label_id = int(raw_label_id)
        label = id_to_label.get(label_id, str(label_id))
        label_pixels = label_mask == label_id
        for group in get_scene_groups(label):
            masks[group] |= label_pixels

    masks["overlay"] = overlay_mask.astype(bool)
    masks["exclude"] = masks["sky"] | masks["vegetation_occluder"] | masks["dynamic_occluder"] | masks["overlay"]
    masks["usable_surface"] = (masks["soft_land"] | masks["hard_surface"]) & ~masks["water"] & ~masks["exclude"]
    return SceneGroupMasks(masks=masks)
