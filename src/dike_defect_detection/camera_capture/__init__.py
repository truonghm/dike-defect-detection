"""Camera snapshot capture helpers."""

from dike_defect_detection.camera_capture.mappings import (
    NEW_PROVINCE_ABBR,
    OLD_PROVINCE_ABBR,
    CameraSite,
    get_camera_filename_prefix,
    load_camera_sites,
)

__all__ = [
    "NEW_PROVINCE_ABBR",
    "OLD_PROVINCE_ABBR",
    "CameraSite",
    "get_camera_filename_prefix",
    "load_camera_sites",
]
