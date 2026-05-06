"""Helpers for reading image assessment metadata from capture CSV logs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import cast

from dike_defect_detection.image_assessment.constants import CAPTURE_METADATA_FILENAME
from dike_defect_detection.image_assessment.day_night import DayNightTag


def load_image_tag_metadata(directory: Path) -> dict[str, DayNightTag]:
    """Load image day/night tags from a capture metadata CSV if present.

    Parameters
    ----------
    directory: Path
        Image directory that may contain ``camera_capture_log.csv``.

    Returns
    -------
    dict[str, DayNightTag]
        Mapping from image filename to image-content-derived D/N tag. Returns
        an empty mapping when the metadata CSV is absent.

    Raises
    ------
    ValueError
        If the metadata CSV exists but does not have the required columns, or
        contains an invalid image tag.
    """

    metadata_path = directory / CAPTURE_METADATA_FILENAME
    if not metadata_path.exists():
        return {}

    with metadata_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or ())
        required_fields = {"filename", "image_tag"}
        missing_fields = required_fields - fieldnames
        if missing_fields:
            raise ValueError(
                f"Metadata CSV {metadata_path} is missing required columns: {', '.join(sorted(missing_fields))}"
            )

        image_tags: dict[str, DayNightTag] = {}
        for row_index, row in enumerate(reader, start=2):
            filename = (row.get("filename") or "").strip()
            raw_image_tag = (row.get("image_tag") or "").strip()
            if not filename and not raw_image_tag:
                continue
            if raw_image_tag not in {"D", "N"}:
                raise ValueError(
                    f"Metadata CSV {metadata_path} has invalid image_tag on row {row_index}: {raw_image_tag}"
                )
            image_tags[filename] = cast(DayNightTag, raw_image_tag)

    return image_tags
