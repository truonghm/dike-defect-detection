"""Input and output helpers for scene-understanding CLIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
UINT8_MAX_VALUE = 255


def collect_image_paths(path: Path) -> list[Path]:
    """Collect image paths from one file or a non-recursive directory.

    Parameters
    ----------
    path: Path
        Image file or flat image directory.

    Returns
    -------
    list[Path]
        Image paths to process.

    Raises
    ------
    ValueError
        If the path is absent, unsupported, or contains no direct image files.
    """

    if path.is_file():
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image extension: {path}")
        return [path]
    if path.is_dir():
        image_paths = sorted(
            child for child in path.iterdir() if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not image_paths:
            raise ValueError(f"No images found in directory: {path}")
        return image_paths
    raise ValueError(f"Path does not exist: {path}")


def save_label_mask(mask: np.ndarray, path: Path) -> None:
    """Save a semantic label mask as a PNG image.

    Parameters
    ----------
    mask: np.ndarray
        Integer label mask.
    path: Path
        Destination PNG path.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    dtype = np.uint8 if int(np.max(mask, initial=0)) <= UINT8_MAX_VALUE else np.uint16
    Image.fromarray(mask.astype(dtype)).save(path)


def write_json(path: Path, data: Any) -> None:
    """Write JSON data with stable indentation.

    Parameters
    ----------
    path: Path
        Destination JSON path.
    data: Any
        JSON-serializable object.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_output_paths(output_dir: Path, image_path: Path) -> tuple[Path, Path]:
    """Build mask and overlay paths for one input image.

    Parameters
    ----------
    output_dir: Path
        Output directory.
    image_path: Path
        Input image path.

    Returns
    -------
    tuple[Path, Path]
        Mask path and overlay path.
    """

    return (
        output_dir / f"{image_path.stem}_oneformer_mask.png",
        output_dir / f"{image_path.stem}_oneformer_overlay.jpg",
    )
