"""Individually callable morphology operations for ferrite masks.

All functions return new arrays; no input mask is ever mutated. Opening removes
specks that cannot contain the structuring element, closing fills pinholes and
bridges hairline gaps. Both are binary-set operations, so an oversized kernel can
destroy thin ferrite features, which is why the kernel size is operator-visible.
"""
from __future__ import annotations

import cv2
import numpy as np

import config


def kernel(size: int = config.DEFAULT_MORPHOLOGY_KERNEL) -> np.ndarray:
    """Create an elliptical structuring element of odd size ``>= 3``."""
    safe = max(3, int(size) | 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (safe, safe))


def opening(mask: np.ndarray, size: int = config.DEFAULT_MORPHOLOGY_KERNEL) -> np.ndarray:
    """Erode then dilate: remove bright specks smaller than the kernel."""
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel(size))


def closing(mask: np.ndarray, size: int = config.DEFAULT_MORPHOLOGY_KERNEL) -> np.ndarray:
    """Dilate then erode: fill small holes and bridge hairline gaps."""
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel(size))


def erode(mask: np.ndarray, size: int = config.DEFAULT_MORPHOLOGY_KERNEL) -> np.ndarray:
    """Shrink bright regions by the kernel radius."""
    return cv2.erode(mask, kernel(size))


def dilate(mask: np.ndarray, size: int = config.DEFAULT_MORPHOLOGY_KERNEL) -> np.ndarray:
    """Grow bright regions by the kernel radius."""
    return cv2.dilate(mask, kernel(size))
