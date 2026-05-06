"""Reusable scene-understanding processing helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dike_defect_detection.scene_understanding.groups import build_scene_group_masks
from dike_defect_detection.scene_understanding.io import build_output_paths, save_label_mask, write_json
from dike_defect_detection.scene_understanding.labels import LabelSummary
from dike_defect_detection.scene_understanding.metrics import compute_scene_metrics
from dike_defect_detection.scene_understanding.oneformer import DEFAULT_ONEFORMER_MODEL, OneFormerSceneParser
from dike_defect_detection.scene_understanding.overlay import build_overlay_exclusion_mask
from dike_defect_detection.scene_understanding.usability import SCORE_PRECISION, SceneDecision
from dike_defect_detection.scene_understanding.visualization import build_semantic_overlay
from dike_defect_detection.synthesis.suitability import DefectClass, assess_synthesis_suitability

DEFAULT_OUTPUT_DIR = Path("outputs/scene_understanding")
DEFAULT_MAX_SIDE = 1024
DEFAULT_TOP_LABELS = 15
ONEFORMER_OUTPUTS_FILENAME = "oneformer_outputs.json"
SCENE_ASSESSMENT_FILENAME = "scene_assessment.json"


@dataclass(frozen=True, slots=True)
class SceneImageProcessingResult:
    """Processing result for one scene-understanding input image.

    Parameters
    ----------
    image_path: Path
        Input image path.
    mask_path: Path
        Saved semantic label mask path.
    overlay_path: Path
        Saved semantic overlay path.
    inference_seconds: float
        OneFormer inference time in seconds.
    label_summaries: tuple[LabelSummary, ...]
        Per-label summaries sorted by descending area.
    synthesis_suitability: Mapping[DefectClass, SceneDecision]
        Synthesis suitability decisions keyed by defect class.
    """

    image_path: Path
    mask_path: Path
    overlay_path: Path
    inference_seconds: float
    label_summaries: tuple[LabelSummary, ...]
    synthesis_suitability: Mapping[DefectClass, SceneDecision]


@dataclass(frozen=True, slots=True)
class SceneUnderstandingRunResult:
    """Processing result for a scene-understanding batch.

    Parameters
    ----------
    output_dir: Path
        Directory containing masks, overlays, and JSON summaries.
    oneformer_outputs_path: Path
        Path to the OneFormer output summary JSON.
    scene_assessment_path: Path
        Path to the scene assessment JSON.
    image_results: tuple[SceneImageProcessingResult, ...]
        Per-image processing results.
    total_inference_seconds: float
        Total OneFormer inference time across processed images.
    model_name: str
        OneFormer model identifier.
    device_text: str
        Selected inference device as display text.
    cuda_name: str
        CUDA device name, or an empty string when CUDA is not used.
    use_amp: bool
        Whether CUDA mixed precision was enabled.
    load_seconds: float
        Model loading time in seconds.
    """

    output_dir: Path
    oneformer_outputs_path: Path
    scene_assessment_path: Path
    image_results: tuple[SceneImageProcessingResult, ...]
    total_inference_seconds: float
    model_name: str
    device_text: str
    cuda_name: str
    use_amp: bool
    load_seconds: float


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


def process_scene_image(
    image_path: Path,
    scene_parser: OneFormerSceneParser,
    output_dir: Path,
    *,
    max_side: int,
    top_labels: int,
) -> tuple[SceneImageProcessingResult, dict[str, str], dict[str, Any]]:
    """Run scene understanding for one image and save derived artifacts.

    Parameters
    ----------
    image_path: Path
        Input image path.
    scene_parser: OneFormerSceneParser
        Loaded OneFormer parser.
    output_dir: Path
        Directory for masks and overlays.
    max_side: int
        Maximum image side length for inference.
    top_labels: int
        Maximum label summaries to include in JSON.

    Returns
    -------
    tuple[SceneImageProcessingResult, dict[str, str], dict[str, Any]]
        Display/result object, OneFormer output JSON record, and scene assessment JSON record.
    """

    result = scene_parser.segment_image(image_path, max_side=max_side)
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

    oneformer_output = {
        "mask_path": str(mask_path.resolve()),
        "overlay_path": str(overlay_path.resolve()),
    }
    scene_assessment = {
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

    image_result = SceneImageProcessingResult(
        image_path=image_path,
        mask_path=mask_path,
        overlay_path=overlay_path,
        inference_seconds=result.inference_seconds,
        label_summaries=result.label_summaries,
        synthesis_suitability=synthesis_suitability,
    )
    return image_result, oneformer_output, scene_assessment


def run_scene_understanding_for_paths(
    image_paths: Sequence[Path],
    output_dir: Path,
    *,
    model_name: str = DEFAULT_ONEFORMER_MODEL,
    max_side: int = DEFAULT_MAX_SIDE,
    device_name: str = "auto",
    use_amp: bool = True,
    top_labels: int = DEFAULT_TOP_LABELS,
) -> SceneUnderstandingRunResult:
    """Run scene understanding for explicit image paths.

    Parameters
    ----------
    image_paths: Sequence[Path]
        Image paths to process. The function never scans parent directories.
    output_dir: Path
        Directory for masks, overlays, and JSON summaries.
    model_name: str
        Hugging Face OneFormer model identifier.
    max_side: int
        Maximum image side length for inference.
    device_name: str
        Inference device name, either ``auto``, ``cuda``, or ``cpu``.
    use_amp: bool
        Whether to use CUDA mixed precision when CUDA is selected.
    top_labels: int
        Maximum label summaries to store per image.

    Returns
    -------
    SceneUnderstandingRunResult
        Batch processing summary.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    oneformer_outputs_path = output_dir / ONEFORMER_OUTPUTS_FILENAME
    scene_assessment_path = output_dir / SCENE_ASSESSMENT_FILENAME

    oneformer_outputs: dict[str, dict[str, str]] = {}
    scene_assessment: dict[str, dict[str, Any]] = {}
    image_results: list[SceneImageProcessingResult] = []
    total_inference_seconds = 0.0
    resolved_model_name = model_name
    device_text = ""
    cuda_name = ""
    resolved_use_amp = use_amp
    load_seconds = 0.0

    if image_paths:
        scene_parser = OneFormerSceneParser(model_name, device_name=device_name, use_amp=use_amp)
        resolved_model_name = scene_parser.model_name
        device_text = scene_parser.device_text
        cuda_name = scene_parser.cuda_name
        resolved_use_amp = scene_parser.use_amp
        load_seconds = scene_parser.load_seconds
        for image_path in image_paths:
            image_result, oneformer_output, assessment = process_scene_image(
                image_path,
                scene_parser,
                output_dir,
                max_side=max_side,
                top_labels=top_labels,
            )
            input_key = str(image_path.resolve())
            oneformer_outputs[input_key] = oneformer_output
            scene_assessment[input_key] = assessment
            image_results.append(image_result)
            total_inference_seconds += image_result.inference_seconds

    write_json(oneformer_outputs_path, oneformer_outputs)
    write_json(scene_assessment_path, scene_assessment)
    return SceneUnderstandingRunResult(
        output_dir=output_dir,
        oneformer_outputs_path=oneformer_outputs_path,
        scene_assessment_path=scene_assessment_path,
        image_results=tuple(image_results),
        total_inference_seconds=total_inference_seconds,
        model_name=resolved_model_name,
        device_text=device_text,
        cuda_name=cuda_name,
        use_amp=resolved_use_amp,
        load_seconds=load_seconds,
    )


def write_scene_understanding_error(
    output_dir: Path,
    image_paths: Sequence[Path],
    error: str,
) -> tuple[Path, Path]:
    """Write scene-understanding JSON files for a failed batch.

    Parameters
    ----------
    output_dir: Path
        Scene-understanding batch output directory.
    image_paths: Sequence[Path]
        Input images that were scheduled for processing.
    error: str
        Failure message to record.

    Returns
    -------
    tuple[Path, Path]
        OneFormer output JSON path and scene assessment JSON path.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    oneformer_outputs_path = output_dir / ONEFORMER_OUTPUTS_FILENAME
    scene_assessment_path = output_dir / SCENE_ASSESSMENT_FILENAME
    oneformer_outputs: dict[str, dict[str, str]] = {}
    scene_assessment = {
        str(image_path.resolve()): {
            "error": error,
        }
        for image_path in image_paths
    }
    write_json(oneformer_outputs_path, oneformer_outputs)
    write_json(scene_assessment_path, scene_assessment)
    return oneformer_outputs_path, scene_assessment_path
