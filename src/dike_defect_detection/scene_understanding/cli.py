"""Command-line interface for scene understanding."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dike_defect_detection.scene_understanding.groups import build_scene_group_masks
from dike_defect_detection.scene_understanding.io import (
    build_output_paths,
    collect_image_paths,
    save_label_mask,
    write_json,
)
from dike_defect_detection.scene_understanding.labels import LabelSummary
from dike_defect_detection.scene_understanding.metrics import compute_scene_metrics
from dike_defect_detection.scene_understanding.oneformer import DEFAULT_ONEFORMER_MODEL, OneFormerSceneParser
from dike_defect_detection.scene_understanding.overlay import build_overlay_exclusion_mask
from dike_defect_detection.scene_understanding.usability import SCORE_PRECISION
from dike_defect_detection.scene_understanding.visualization import build_semantic_overlay
from dike_defect_detection.synthesis.suitability import assess_synthesis_suitability

DEFAULT_OUTPUT_DIR = Path("outputs/scene_understanding")
DEFAULT_MAX_SIDE = 1024
DEFAULT_TOP_LABELS = 15
ONEFORMER_OUTPUTS_FILENAME = "oneformer_outputs.json"
SCENE_ASSESSMENT_FILENAME = "scene_assessment.json"
DISPLAY_SECONDS_PRECISION = 2
DISPLAY_SCORE_PRECISION = 3
DISPLAY_RATIO_PRECISION = 3


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the scene-understanding CLI parser.

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser.
    """

    parser = argparse.ArgumentParser(
        description="Run OneFormer scene parsing and rough defect-suitability checks on an image or flat directory.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Image file or non-recursive image directory to process.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=f"Directory for masks, overlays, and JSON summaries. Default: {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--model",
        help=f"Hugging Face OneFormer model. Default: {DEFAULT_ONEFORMER_MODEL}.",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        help=f"Resize images so their largest side is at most this many pixels. Default: {DEFAULT_MAX_SIDE}.",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="Inference device. Default: auto.",
    )
    parser.add_argument(
        "--no-amp",
        action="store_true",
        help="Disable CUDA mixed-precision inference.",
    )
    parser.add_argument(
        "--top-labels",
        type=int,
        help=f"Number of label summaries to print and store per image. Default: {DEFAULT_TOP_LABELS}.",
    )
    return parser


def label_summaries_to_json(label_summaries: Sequence[LabelSummary], max_items: int) -> list[dict[str, Any]]:
    """Convert label summaries to JSON-serializable records.

    Parameters
    ----------
    label_summaries: Sequence[LabelSummary]
        Label summary records.
    max_items: int
        Maximum number of summaries to include.

    Returns
    -------
    list[dict[str, Any]]
        JSON records.
    """

    return [asdict(summary) for summary in label_summaries[:max_items]]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scene-understanding CLI.

    Parameters
    ----------
    argv: Sequence[str] | None
        CLI arguments excluding the executable name.

    Returns
    -------
    int
        Process exit code.
    """

    parser = build_argument_parser()
    args = parser.parse_args(argv)
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    model_name = args.model or DEFAULT_ONEFORMER_MODEL
    max_side = DEFAULT_MAX_SIDE if args.max_side is None else args.max_side
    top_labels = DEFAULT_TOP_LABELS if args.top_labels is None else args.top_labels

    if max_side < 1:
        parser.error("--max-side must be positive")
    if top_labels < 1:
        parser.error("--top-labels must be positive")

    try:
        image_paths = collect_image_paths(args.path)
        scene_parser = OneFormerSceneParser(model_name, device_name=args.device, use_amp=not args.no_amp)
    except RuntimeError as error:
        parser.error(str(error))
    except ValueError as error:
        parser.error(str(error))

    oneformer_outputs: dict[str, dict[str, str]] = {}
    scene_assessment: dict[str, dict[str, Any]] = {}
    total_inference_seconds = 0.0

    print(f"model={scene_parser.model_name}")
    print(f"device={scene_parser.device_text}")
    if scene_parser.cuda_name:
        print(f"cuda_name={scene_parser.cuda_name}")
    print(f"amp={scene_parser.use_amp}")
    print(f"load_seconds={scene_parser.load_seconds:.2f}")
    print(f"images={len(image_paths)}")

    for image_path in image_paths:
        result = scene_parser.segment_image(image_path, max_side=max_side)
        total_inference_seconds += result.inference_seconds
        mask_path, overlay_path = build_output_paths(output_dir, image_path)

        overlay_mask = build_overlay_exclusion_mask(result.label_mask.shape[0], result.label_mask.shape[1])
        group_masks = build_scene_group_masks(result.label_mask, result.id_to_label, overlay_mask)
        metrics = compute_scene_metrics(group_masks)
        synthesis_suitability = assess_synthesis_suitability(metrics)

        save_label_mask(result.label_mask, mask_path)
        overlay_image = build_semantic_overlay(
            result.image,
            result.label_mask,
            result.id_to_label,
            result.label_summaries,
        )
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay_image.save(overlay_path, quality=92)

        input_key = str(image_path.resolve())
        oneformer_outputs[input_key] = {
            "mask_path": str(mask_path.resolve()),
            "overlay_path": str(overlay_path.resolve()),
        }
        scene_assessment[input_key] = {
            "mask_path": str(mask_path.resolve()),
            "overlay_path": str(overlay_path.resolve()),
            "processed_image_width": result.image.width,
            "processed_image_height": result.image.height,
            "inference_seconds": round(result.inference_seconds, SCORE_PRECISION),
            "top_labels": label_summaries_to_json(result.label_summaries, top_labels),
            "metrics": asdict(metrics),
            "synthesis_suitability": {
                defect_class: asdict(decision) for defect_class, decision in synthesis_suitability.items()
            },
        }

        print(f"\nimage={image_path}")
        print(f"inference_seconds={result.inference_seconds:.{DISPLAY_SECONDS_PRECISION}f}")
        print(f"mask={mask_path}")
        print(f"overlay={overlay_path}")
        print("synthesis_suitability")
        for defect_class, decision in synthesis_suitability.items():
            print(
                f"{defect_class}\t{decision.status}\t"
                f"{decision.score:.{DISPLAY_SCORE_PRECISION}f}\t{';'.join(decision.reasons)}"
            )
        print("top_labels")
        for summary in result.label_summaries[:top_labels]:
            print(
                f"{summary.label_id:3d}\t{summary.area_ratio:.{DISPLAY_RATIO_PRECISION}f}\t"
                f"RGB{summary.color}\t{summary.label}"
            )

    oneformer_outputs_path = output_dir / ONEFORMER_OUTPUTS_FILENAME
    scene_assessment_path = output_dir / SCENE_ASSESSMENT_FILENAME
    write_json(oneformer_outputs_path, oneformer_outputs)
    write_json(scene_assessment_path, scene_assessment)
    print(f"\noneformer_outputs={oneformer_outputs_path}")
    print(f"scene_assessment={scene_assessment_path}")
    print(f"total_inference_seconds={total_inference_seconds:.{DISPLAY_SECONDS_PRECISION}f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
