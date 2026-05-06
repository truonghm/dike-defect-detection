"""Command-line interface for scene understanding."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from dike_defect_detection.scene_understanding.io import collect_image_paths
from dike_defect_detection.scene_understanding.oneformer import DEFAULT_ONEFORMER_MODEL
from dike_defect_detection.scene_understanding.processing import (
    DEFAULT_MAX_SIDE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TOP_LABELS,
    run_scene_understanding_for_paths,
)

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
        run_result = run_scene_understanding_for_paths(
            image_paths,
            output_dir,
            model_name=model_name,
            max_side=max_side,
            device_name=args.device,
            use_amp=not args.no_amp,
            top_labels=top_labels,
        )
    except RuntimeError as error:
        parser.error(str(error))
    except ValueError as error:
        parser.error(str(error))

    print(f"model={run_result.model_name}")
    print(f"device={run_result.device_text}")
    if run_result.cuda_name:
        print(f"cuda_name={run_result.cuda_name}")
    print(f"amp={run_result.use_amp}")
    print(f"load_seconds={run_result.load_seconds:.2f}")
    print(f"images={len(image_paths)}")

    for image_result in run_result.image_results:
        print(f"\nimage={image_result.image_path}")
        print(f"inference_seconds={image_result.inference_seconds:.{DISPLAY_SECONDS_PRECISION}f}")
        print(f"mask={image_result.mask_path}")
        print(f"overlay={image_result.overlay_path}")
        print("synthesis_suitability")
        for defect_class, decision in image_result.synthesis_suitability.items():
            print(
                f"{defect_class}\t{decision.status}\t"
                f"{decision.score:.{DISPLAY_SCORE_PRECISION}f}\t{';'.join(decision.reasons)}"
            )
        print("top_labels")
        for summary in image_result.label_summaries[:top_labels]:
            print(
                f"{summary.label_id:3d}\t{summary.area_ratio:.{DISPLAY_RATIO_PRECISION}f}\t"
                f"RGB{summary.color}\t{summary.label}"
            )

    print(f"\noneformer_outputs={run_result.oneformer_outputs_path}")
    print(f"scene_assessment={run_result.scene_assessment_path}")
    print(f"total_inference_seconds={run_result.total_inference_seconds:.{DISPLAY_SECONDS_PRECISION}f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
