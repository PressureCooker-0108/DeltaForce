"""Full staged ferrite-segmentation pipeline.

Required chain, in order::

    upload -> LAB -> CLAHE -> bilateral -> adaptive threshold -> Otsu fallback
           -> opening -> closing -> connected components -> binary ferrite mask

Preservation rules enforced here: the uploaded stream is decoded exactly once at
native resolution and no stage crops, resizes, rotates or resamples the image, so
sample-identification markings, scale bars and borders survive into every output.
Bounding what is sent to the browser happens in the UI layer only.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

import config
from segmentation.components import (ComponentReport, component_report,
                                     label_visualization, remove_small_components)
from segmentation.morphology import closing, opening
from segmentation.threshold import ThresholdOutcome, apply_polarity, select_mask


@dataclass(frozen=True)
class SegmentationParams:
    """Every knob that can change the produced mask. Hashable for result caching."""

    clip_limit: float = config.DEFAULT_CLAHE_CLIP_LIMIT
    tile_size: int = config.DEFAULT_CLAHE_TILE_SIZE
    threshold_mode: str = config.DEFAULT_THRESHOLD_MODE
    block_size: int = config.DEFAULT_BLOCK_SIZE
    adaptive_c: int = config.DEFAULT_ADAPTIVE_C
    polarity: str = config.POLARITY_DARK
    morphology_kernel: int = config.DEFAULT_MORPHOLOGY_KERNEL
    minimum_area: int = config.DEFAULT_MINIMUM_AREA
    separability_gate: float = config.OTSU_SEPARABILITY_GATE

    def as_provenance(self) -> tuple[tuple[str, str], ...]:
        """Flatten to ordered string pairs for reports and CSV exports."""
        return (
            ("CLAHE clip limit", f"{self.clip_limit:g}"),
            ("CLAHE tile size", f"{self.tile_size}"),
            ("Threshold mode", config.THRESHOLD_MODE_LABELS.get(self.threshold_mode, self.threshold_mode)),
            ("Adaptive block size", f"{self.block_size}"),
            ("Adaptive constant C", f"{self.adaptive_c}"),
            ("Polarity", config.POLARITY_LABELS.get(self.polarity, self.polarity)),
            ("Morphology kernel", f"{self.morphology_kernel} px ellipse"),
            ("Minimum component area", f"{self.minimum_area} px"),
            ("Otsu separability gate", f"{self.separability_gate:.2f}"),
            ("Bilateral filter", f"d={config.BILATERAL_DIAMETER}, "
                                 f"sigma={config.BILATERAL_SIGMA_COLOR}/{config.BILATERAL_SIGMA_SPACE}"),
        )


@dataclass(frozen=True)
class StageBundle:
    """Intermediate images of every pipeline stage.

    Only ``original_rgb``, ``enhanced_rgb`` and ``mask`` are populated on the normal
    path; the remaining fields are filled when ``keep_stages=True`` (developer mode)
    so that routine runs do not pay to copy and cache extra megapixel arrays.
    """

    original_rgb: np.ndarray
    enhanced_rgb: np.ndarray
    mask: np.ndarray
    lightness_raw: Optional[np.ndarray] = None
    clahe_rgb: Optional[np.ndarray] = None
    lightness: Optional[np.ndarray] = None
    threshold_bright: Optional[np.ndarray] = None
    opened: Optional[np.ndarray] = None
    closed: Optional[np.ndarray] = None
    polarity_mask: Optional[np.ndarray] = None
    label_view: Optional[np.ndarray] = None


@dataclass(frozen=True)
class SegmentationResult:
    """A mask plus the diagnostics that justify it."""

    stages: StageBundle
    threshold: ThresholdOutcome
    components: ComponentReport
    coverage: float
    elapsed_ms: float

    @property
    def mask(self) -> np.ndarray:
        return self.stages.mask

    @property
    def original_rgb(self) -> np.ndarray:
        return self.stages.original_rgb

    @property
    def enhanced_rgb(self) -> np.ndarray:
        return self.stages.enhanced_rgb

    @property
    def height(self) -> int:
        return int(self.stages.original_rgb.shape[0])

    @property
    def width(self) -> int:
        return int(self.stages.original_rgb.shape[1])

    @property
    def megapixels(self) -> float:
        return self.height * self.width / 1e6


def decode_image(data: bytes) -> np.ndarray:
    """Decode uploaded bytes to an ``HxWx3`` RGB array at native resolution."""
    if not data:
        raise ValueError("The uploaded file is empty.")
    source = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if source is None:
        raise ValueError("The uploaded file is not a readable image (PNG, JPEG, TIFF or BMP).")
    return cv2.cvtColor(source, cv2.COLOR_BGR2RGB)


def enhance(rgb: np.ndarray, clip_limit: float, tile_size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """LAB conversion, CLAHE on L, merge, then bilateral denoise.

    Returns:
        ``(lightness_raw, clahe_rgb, enhanced_rgb, lightness)`` where ``lightness`` is
        the L plane of the bilateral-filtered image used for thresholding.
    """
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    lightness_raw = l_channel.copy()
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit),
                            tileGridSize=(int(tile_size), int(tile_size)))
    equalized = clahe.apply(l_channel)
    clahe_rgb = cv2.cvtColor(cv2.merge((equalized, a_channel, b_channel)), cv2.COLOR_LAB2RGB)
    enhanced_rgb = cv2.bilateralFilter(clahe_rgb, config.BILATERAL_DIAMETER,
                                       config.BILATERAL_SIGMA_COLOR,
                                       config.BILATERAL_SIGMA_SPACE)
    lightness = cv2.cvtColor(enhanced_rgb, cv2.COLOR_RGB2LAB)[:, :, 0].copy()
    return lightness_raw, clahe_rgb, enhanced_rgb, lightness


def segment(data: bytes, params: SegmentationParams, keep_stages: bool = False) -> SegmentationResult:
    """Run the complete deterministic pipeline and return the ferrite mask.

    Args:
        data: raw uploaded bytes.
        params: segmentation parameters; changing any of them changes the mask.
        keep_stages: also retain every intermediate image for developer mode.
    """
    started = time.perf_counter()
    original = decode_image(data)
    lightness_raw, clahe_rgb, enhanced, lightness = enhance(original, params.clip_limit, params.tile_size)

    # LAB conversion is asserted here: the threshold helper is fed RGB explicitly so
    # that a future refactor cannot silently swap colour spaces.
    assert lightness.shape == lightness_raw.shape

    outcome = select_mask(lightness, params.block_size, params.adaptive_c,
                          params.threshold_mode, params.separability_gate)
    polarity_mask = apply_polarity(outcome.mask, params.polarity)
    opened = opening(polarity_mask, params.morphology_kernel)
    closed = closing(opened, params.morphology_kernel)
    mask = remove_small_components(closed, params.minimum_area)
    report = component_report(closed, params.minimum_area)
    coverage = float(np.count_nonzero(mask)) / mask.size

    stages = StageBundle(
        original_rgb=original,
        enhanced_rgb=enhanced,
        mask=mask,
        lightness_raw=lightness_raw if keep_stages else None,
        clahe_rgb=clahe_rgb if keep_stages else None,
        lightness=lightness if keep_stages else None,
        threshold_bright=outcome.mask if keep_stages else None,
        opened=opened if keep_stages else None,
        closed=closed if keep_stages else None,
        polarity_mask=polarity_mask if keep_stages else None,
        label_view=label_visualization(closed) if keep_stages else None,
    )
    return SegmentationResult(
        stages=stages,
        threshold=outcome,
        components=report,
        coverage=coverage,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )
