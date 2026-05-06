"""Visualization helpers for semantic scene masks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from dike_defect_detection.scene_understanding.labels import LabelSummary, get_label_color

DEFAULT_LEGEND_MAX_ITEMS = 10
COLOR_CHANNEL_COUNT = 3
OVERLAY_IMAGE_WEIGHT = 0.55
OVERLAY_MASK_WEIGHT = 0.45
LEGEND_LINE_HEIGHT_PX = 16
LEGEND_MARGIN_PX = 8
LEGEND_BOX_WIDTH_PX = 230
LEGEND_EDGE_OFFSET_PX = 8
LEGEND_BACKGROUND_RGBA = (0, 0, 0, 155)
LEGEND_TEXT_RGB = (255, 255, 255)
LEGEND_SWATCH_SIZE_PX = 10
LEGEND_SWATCH_Y_OFFSET_PX = 3
LEGEND_TEXT_X_OFFSET_PX = 16
LEGEND_TEXT_ALPHA = 235
LEGEND_SWATCH_OUTLINE_ALPHA = 220
LEGEND_LABEL_MAX_CHARS = 24
LEGEND_PERCENT_SCALE = 100
LEGEND_PERCENT_PRECISION = 1


def colorize_label_mask(label_mask: np.ndarray, id_to_label: Mapping[int, str]) -> np.ndarray:
    """Colorize an integer semantic label mask.

    Parameters
    ----------
    label_mask: np.ndarray
        Integer semantic label mask.
    id_to_label: Mapping[int, str]
        Label identifier to label name mapping.

    Returns
    -------
    np.ndarray
        RGB color mask.
    """

    palette = np.zeros((int(np.max(label_mask, initial=0)) + 1, COLOR_CHANNEL_COUNT), dtype=np.uint8)
    for label_id in range(len(palette)):
        label = id_to_label.get(label_id, str(label_id))
        palette[label_id] = get_label_color(label_id, label)
    return palette[label_mask]


def draw_compact_legend(
    overlay: Image.Image,
    label_summaries: Sequence[LabelSummary],
    *,
    max_items: int = DEFAULT_LEGEND_MAX_ITEMS,
) -> Image.Image:
    """Draw a compact label legend onto an overlay image.

    Parameters
    ----------
    overlay: Image.Image
        RGB overlay image.
    label_summaries: Sequence[LabelSummary]
        Label summaries sorted by area.
    max_items: int
        Maximum number of labels to display.

    Returns
    -------
    Image.Image
        Overlay image with a legend.
    """

    font = ImageFont.load_default()
    items = label_summaries[:max_items]
    box_height = LEGEND_MARGIN_PX * 2 + LEGEND_LINE_HEIGHT_PX * len(items)
    x0 = max(0, overlay.width - LEGEND_BOX_WIDTH_PX - LEGEND_EDGE_OFFSET_PX)
    y0 = max(0, overlay.height - box_height - LEGEND_EDGE_OFFSET_PX)

    base = overlay.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rectangle((x0, y0, x0 + LEGEND_BOX_WIDTH_PX, y0 + box_height), fill=LEGEND_BACKGROUND_RGBA)

    for index, summary in enumerate(items):
        y = y0 + LEGEND_MARGIN_PX + index * LEGEND_LINE_HEIGHT_PX
        draw.rectangle(
            (
                x0 + LEGEND_MARGIN_PX,
                y + LEGEND_SWATCH_Y_OFFSET_PX,
                x0 + LEGEND_MARGIN_PX + LEGEND_SWATCH_SIZE_PX,
                y + LEGEND_SWATCH_Y_OFFSET_PX + LEGEND_SWATCH_SIZE_PX,
            ),
            fill=summary.color,
            outline=(*LEGEND_TEXT_RGB, LEGEND_SWATCH_OUTLINE_ALPHA),
        )
        text = (
            f"{summary.area_ratio * LEGEND_PERCENT_SCALE:4.{LEGEND_PERCENT_PRECISION}f}% "
            f"{summary.label[:LEGEND_LABEL_MAX_CHARS]}"
        )
        draw.text(
            (x0 + LEGEND_MARGIN_PX + LEGEND_TEXT_X_OFFSET_PX, y),
            text,
            fill=(*LEGEND_TEXT_RGB, LEGEND_TEXT_ALPHA),
            font=font,
        )

    return Image.alpha_composite(base, layer).convert("RGB")


def build_semantic_overlay(
    image: Image.Image,
    label_mask: np.ndarray,
    id_to_label: Mapping[int, str],
    label_summaries: Sequence[LabelSummary],
) -> Image.Image:
    """Build a semantic segmentation overlay with a compact legend.

    Parameters
    ----------
    image: Image.Image
        RGB source image.
    label_mask: np.ndarray
        Integer semantic label mask.
    id_to_label: Mapping[int, str]
        Label identifier to label name mapping.
    label_summaries: Sequence[LabelSummary]
        Label summaries sorted by area.

    Returns
    -------
    Image.Image
        RGB overlay image.
    """

    rgb = np.asarray(image, dtype=np.uint8)
    colors = colorize_label_mask(label_mask, id_to_label)
    overlay = ((OVERLAY_IMAGE_WEIGHT * rgb) + (OVERLAY_MASK_WEIGHT * colors)).astype(np.uint8)
    return draw_compact_legend(Image.fromarray(overlay), label_summaries)
