"""LAB lightness extraction, adaptive/Otsu thresholding and the polarity decision.

The previous version of this module silently assumed a BGR input while the active
pipeline produced RGB, so wiring the module into the app would have changed every
result (measured: L differs by up to 21 levels and 2.8% of pixels flip class).
Every function here now states and validates its colour-space contract.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

import config

_VALID_INPUT_COLORS = ("BGR", "RGB")


def lab_lightness(image: np.ndarray, input_color: str = "BGR") -> np.ndarray:
    """Return the LAB ``L`` channel of ``image`` as an ``HxW`` uint8 array.

    Args:
        image: ``HxWx3`` or ``HxWx4`` uint8 array. An alpha channel is ignored.
        input_color: ``"BGR"`` (OpenCV native) or ``"RGB"`` (Streamlit/Plotly native).

    Raises:
        ValueError: if the array is not a 3- or 4-channel image, or ``input_color``
            is not recognised. Failing loudly is deliberate: a silent colour-space
            mix-up changes the measurement without changing any visible behaviour.
    """
    if image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError(f"lab_lightness expects HxWx3 or HxWx4, got shape {image.shape}")
    key = str(input_color).upper()
    if key not in _VALID_INPUT_COLORS:
        raise ValueError(f"input_color must be one of {_VALID_INPUT_COLORS}, got {input_color!r}")
    colour = np.ascontiguousarray(image[:, :, :3])
    rgb = colour if key == "RGB" else cv2.cvtColor(colour, cv2.COLOR_BGR2RGB)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].copy()


def adaptive_threshold(lightness: np.ndarray, block_size: int = config.DEFAULT_BLOCK_SIZE,
                       c_value: int = config.DEFAULT_ADAPTIVE_C) -> np.ndarray:
    """Gaussian adaptive threshold; block size is forced odd and at least 3."""
    block = max(3, int(block_size) | 1)
    return cv2.adaptiveThreshold(
        lightness, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, int(c_value)
    )


def otsu_threshold(lightness: np.ndarray) -> tuple[np.ndarray, float]:
    """Global Otsu threshold. Returns ``(mask, threshold_value)``."""
    value, mask = cv2.threshold(lightness, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return mask, float(value)


def otsu_separability(lightness: np.ndarray, threshold: float) -> float:
    """Return Otsu's goodness-of-threshold measure ``eta`` in ``[0, 1]``.

    ``eta = sigma_between^2 / sigma_total^2``. It says how cleanly the histogram
    splits into two classes at ``threshold``: values near 1 mean a genuine two-phase
    intensity distribution, low values mean the image has no usable phase contrast
    and any binarisation is arbitrary.
    """
    values = np.asarray(lightness, dtype=np.float32).ravel()
    total_variance = float(values.var())
    if total_variance <= 0.0:
        return 0.0
    lower = values <= threshold
    weight_low = float(np.count_nonzero(lower)) / values.size
    weight_high = 1.0 - weight_low
    if weight_low <= 0.0 or weight_high <= 0.0:
        return 0.0
    mean_low = float(values[lower].mean())
    mean_high = float(values[~lower].mean())
    return (weight_low * weight_high * (mean_low - mean_high) ** 2) / total_variance


def apply_polarity(bright_mask: np.ndarray, polarity: str) -> np.ndarray:
    """Convert a "white = bright pixel" mask into the requested ferrite polarity."""
    if polarity == config.POLARITY_DARK:
        return cv2.bitwise_not(bright_mask)
    if polarity == config.POLARITY_BRIGHT:
        return bright_mask.copy()
    raise ValueError(f"polarity must be {config.POLARITY_DARK!r} or {config.POLARITY_BRIGHT!r}")


@dataclass(frozen=True)
class ThresholdOutcome:
    """Binary mask plus the diagnostics that justify how it was produced."""

    mask: np.ndarray
    method: str
    otsu_value: float
    separability: float
    adaptive_coverage: float
    used_otsu: bool


def select_mask(lightness: np.ndarray, block_size: int = config.DEFAULT_BLOCK_SIZE,
                c_value: int = config.DEFAULT_ADAPTIVE_C, mode: str = config.DEFAULT_THRESHOLD_MODE,
                separability_gate: float = config.OTSU_SEPARABILITY_GATE) -> ThresholdOutcome:
    """Produce a "white = bright" mask using the adaptive-first, Otsu-fallback rule.

    Order of operations follows the required pipeline (adaptive threshold, then Otsu
    fallback), but the *decision* is based on threshold quality rather than on an
    arbitrary coverage window:

    * ``mode="adaptive"`` - always keep the adaptive result.
    * ``mode="otsu"`` - always use the global Otsu result.
    * ``mode="auto"`` - use Otsu when the adaptive coverage is implausible, or when
      the L histogram is strongly bimodal (``eta >= separability_gate``). Bimodality
      means a single global threshold describes the specimen, while a locally varying
      threshold would manufacture texture as phase.
    """
    if mode not in config.THRESHOLD_MODES:
        raise ValueError(f"mode must be one of {config.THRESHOLD_MODES}, got {mode!r}")

    adaptive = adaptive_threshold(lightness, block_size, c_value)
    adaptive_coverage = float(np.count_nonzero(adaptive)) / adaptive.size
    otsu_mask, otsu_value = otsu_threshold(lightness)
    eta = otsu_separability(lightness, otsu_value)

    if mode == "adaptive":
        return ThresholdOutcome(adaptive, "Adaptive threshold (forced)", otsu_value, eta,
                                adaptive_coverage, False)
    if mode == "otsu":
        return ThresholdOutcome(otsu_mask, "Otsu global (forced)", otsu_value, eta,
                                adaptive_coverage, True)

    degenerate = not (config.ADAPTIVE_COVERAGE_LOW <= adaptive_coverage <= config.ADAPTIVE_COVERAGE_HIGH)
    bimodal = eta >= separability_gate
    if degenerate or bimodal:
        reason = "bimodal L histogram" if bimodal else "adaptive coverage out of band"
        return ThresholdOutcome(otsu_mask, f"Otsu global ({reason}, eta={eta:.2f})",
                                otsu_value, eta, adaptive_coverage, True)
    return ThresholdOutcome(adaptive, f"Adaptive threshold (eta={eta:.2f} below gate)",
                            otsu_value, eta, adaptive_coverage, False)
