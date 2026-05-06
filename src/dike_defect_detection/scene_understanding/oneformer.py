"""OneFormer semantic segmentation backend."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from dike_defect_detection.scene_understanding.labels import LabelSummary, get_label_color

DEFAULT_ONEFORMER_MODEL = "shi-labs/oneformer_ade20k_swin_tiny"


@dataclass(frozen=True, slots=True)
class OneFormerResult:
    """OneFormer semantic segmentation result.

    Parameters
    ----------
    image: Image.Image
        RGB image used for inference, after optional resizing.
    label_mask: np.ndarray
        Integer semantic label mask with the same spatial size as ``image``.
    id_to_label: dict[int, str]
        Model label identifier to human-readable label mapping.
    label_summaries: tuple[LabelSummary, ...]
        Per-label area summaries sorted by descending area.
    inference_seconds: float
        Model forward-pass time in seconds.
    """

    image: Image.Image
    label_mask: np.ndarray
    id_to_label: dict[int, str]
    label_summaries: tuple[LabelSummary, ...]
    inference_seconds: float


def load_rgb_image(path: Path, max_side: int) -> Image.Image:
    """Load an image as RGB and optionally resize it for inference.

    Parameters
    ----------
    path: Path
        Image path.
    max_side: int
        Maximum output side length. Images smaller than this are unchanged.

    Returns
    -------
    Image.Image
        RGB image.
    """

    image = Image.open(path).convert("RGB")
    if max(image.size) <= max_side:
        return image
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image


class OneFormerSceneParser:
    """Thin wrapper around Hugging Face OneFormer semantic segmentation."""

    def __init__(self, model_name: str, *, device_name: str, use_amp: bool) -> None:
        """Load a OneFormer model for repeated image inference.

        Parameters
        ----------
        model_name: str
            Hugging Face model identifier.
        device_name: str
            ``"auto"``, ``"cuda"``, or ``"cpu"``.
        use_amp: bool
            Whether to use CUDA mixed precision when CUDA is selected.

        Raises
        ------
        RuntimeError
            If optional vision dependencies are unavailable.
        SystemExit
            If CUDA is requested but unavailable.
        """

        try:
            import torch
            from transformers import OneFormerForUniversalSegmentation, OneFormerProcessor
        except ImportError as error:
            raise RuntimeError(
                "OneFormer scene parsing requires the vision optional dependencies. "
                "Run with `uv run --extra vision python -m dike_defect_detection.scene_understanding ...`."
            ) from error

        load_start = time.perf_counter()
        self.model_name = model_name
        self.torch: Any = torch
        self.device = self._resolve_device(device_name)
        self.use_amp = self.device.type == "cuda" and use_amp
        if self.device.type == "cuda":
            torch.set_float32_matmul_precision("high")
        self.processor: Any = OneFormerProcessor.from_pretrained(model_name)
        self.model: Any = OneFormerForUniversalSegmentation.from_pretrained(model_name).to(self.device).eval()
        self.load_seconds = time.perf_counter() - load_start

    def _resolve_device(self, device_name: str) -> Any:
        torch = self.torch
        if device_name == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if device_name == "cuda" and not torch.cuda.is_available():
            raise SystemExit("CUDA was requested, but torch.cuda.is_available() is false.")
        return torch.device(device_name)

    @property
    def device_text(self) -> str:
        """Return the selected device as display text."""

        return str(self.device)

    @property
    def cuda_name(self) -> str:
        """Return the CUDA device name, or an empty string for CPU."""

        if self.device.type != "cuda":
            return ""
        return str(self.torch.cuda.get_device_name(self.device))

    def segment_image(self, image_path: Path, *, max_side: int) -> OneFormerResult:
        """Run semantic segmentation on one image.

        Parameters
        ----------
        image_path: Path
            Image path.
        max_side: int
            Maximum side length used for inference.

        Returns
        -------
        OneFormerResult
            Segmentation mask and label summaries.
        """

        image = load_rgb_image(image_path, max_side)
        inputs = self.processor(images=image, task_inputs=["semantic"], return_tensors="pt").to(self.device)

        inference_start = time.perf_counter()
        with self.torch.inference_mode():
            if self.use_amp:
                with self.torch.autocast(device_type="cuda", dtype=self.torch.float16):
                    outputs = self.model(**inputs)
            else:
                outputs = self.model(**inputs)
        if self.device.type == "cuda":
            self.torch.cuda.synchronize()
        inference_seconds = time.perf_counter() - inference_start

        segmentation = self.processor.post_process_semantic_segmentation(
            outputs,
            target_sizes=[image.size[::-1]],
        )[0]
        label_mask = segmentation.cpu().numpy().astype(np.int32)
        id_to_label = {int(label_id): str(label) for label_id, label in self.model.config.id2label.items()}
        label_summaries = summarize_labels(label_mask, id_to_label)
        return OneFormerResult(
            image=image,
            label_mask=label_mask,
            id_to_label=id_to_label,
            label_summaries=label_summaries,
            inference_seconds=inference_seconds,
        )


def summarize_labels(label_mask: np.ndarray, id_to_label: dict[int, str]) -> tuple[LabelSummary, ...]:
    """Summarize label areas in a semantic mask.

    Parameters
    ----------
    label_mask: np.ndarray
        Integer semantic label mask.
    id_to_label: dict[int, str]
        Label identifier to label name mapping.

    Returns
    -------
    tuple[LabelSummary, ...]
        Label summaries sorted by descending area.
    """

    label_ids, counts = np.unique(label_mask, return_counts=True)
    total = label_mask.size
    summaries = []
    for label_id, count in sorted(zip(label_ids, counts, strict=True), key=lambda item: item[1], reverse=True):
        normalized_label_id = int(label_id)
        label = id_to_label.get(normalized_label_id, str(normalized_label_id))
        summaries.append(
            LabelSummary(
                label_id=normalized_label_id,
                label=label,
                area_ratio=float(count / total),
                color=get_label_color(normalized_label_id, label),
            )
        )
    return tuple(summaries)
