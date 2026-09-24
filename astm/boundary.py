"""Neighborhood-based approximation of the ASTM E562 half-point boundary rule."""
from __future__ import annotations

import numpy as np

import config


def ferrite_ratio(mask: np.ndarray, x: int, y: int, neighborhood: int = config.DEFAULT_NEIGHBORHOOD) -> float:
    """Return local ferrite occupancy in an edge-clipped ``neighborhood`` window."""
    radius = max(1, int(neighborhood)) // 2
    height, width = mask.shape[:2]
    window = mask[max(0, y - radius): min(height, y + radius + 1),
                  max(0, x - radius): min(width, x + radius + 1)]
    if window.size == 0:
        return 0.0
    return float(np.count_nonzero(window)) / window.size


def classify_ratio(ratio: float) -> tuple[str, float]:
    """Map local occupancy to the ASTM-inspired ferrite / boundary / matrix score.

    ``ratio > 0.80`` is a full ferrite hit, ``0.20 <= ratio <= 0.80`` is a boundary
    hit worth half a point, and anything lower is matrix. Every ratio maps to exactly
    one class, so no grid point can ever be left unclassified.
    """
    if ratio > config.FERRITE_RATIO_THRESHOLD:
        return "ferrite", config.FERRITE_SCORE
    if ratio >= config.MATRIX_RATIO_THRESHOLD:
        return "boundary", config.BOUNDARY_SCORE
    return "matrix", config.MATRIX_SCORE
