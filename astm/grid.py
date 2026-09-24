"""Image-aware systematic grid generation for ASTM E562 point counts."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, cos, radians, sin, sqrt
from typing import Iterable

import cv2
import numpy as np

import config


@dataclass(frozen=True)
class GridPoint:
    """A zero-based, image-coordinate ASTM grid point."""

    index: int
    x: int
    y: int


def grid_shape(count: int) -> tuple[int, int]:
    """Return ``(rows, cols)`` for ``count`` points, square whenever possible."""
    if count < 1:
        raise ValueError("count must be >= 1")
    root = int(sqrt(count))
    if root * root == count:
        return root, root
    return root, ceil(count / root)


def generate_grid(
    image_width: int,
    image_height: int,
    count: int = config.DEFAULT_GRID_SIZE,
    angle_degrees: float = 0.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    margin: int = config.GRID_MARGIN,
) -> list[GridPoint]:
    """Generate a rotated systematic grid whose points all remain inside the image.

    The lattice is a square of side ``span`` centred on the image, reduced by
    ``|cos t| + |sin t|`` so that a rotated square of that side still fits inside the
    limiting image dimension. That keeps spacing equal in both axes, keeps every point
    at least ``margin`` pixels from every edge at any rotation, and - unlike a
    rotate-then-drop approach - never silently loses points. Requested translation is
    clamped rather than clipping or dropping points.
    """
    if count < 1 or image_width <= 2 * margin or image_height <= 2 * margin:
        return []
    rows, cols = grid_shape(count)
    theta = radians(angle_degrees)
    clearance = min(image_width, image_height) / 2 - margin
    span = 0.0 if count == 1 else 2 * clearance / (abs(cos(theta)) + abs(sin(theta)))
    xs = np.linspace(-span / 2, span / 2, cols)
    ys = np.linspace(-span / 2, span / 2, rows)
    base = np.array([(x, y) for y in ys for x in xs], dtype=np.float64)[:count]
    rotation = np.array([[cos(theta), -sin(theta)], [sin(theta), cos(theta)]])
    points = base @ rotation.T + np.array([image_width / 2, image_height / 2])
    min_shift = np.array([margin, margin]) - points.min(axis=0)
    max_shift = np.array([image_width - 1 - margin, image_height - 1 - margin]) - points.max(axis=0)
    points = points + np.clip(np.array([offset_x, offset_y]), min_shift, max_shift)
    return [GridPoint(index=i, x=int(round(x)), y=int(round(y))) for i, (x, y) in enumerate(points)]


def in_bounds(points: Iterable[GridPoint], image_width: int, image_height: int) -> bool:
    """True when every point lies strictly inside the image."""
    return all(0 <= p.x < image_width and 0 <= p.y < image_height for p in points)


def draw_grid(image: np.ndarray, points: Iterable[GridPoint],
              colors: dict[int, tuple[int, int, int]], radius: int = 5,
              numbered: bool = True) -> np.ndarray:
    """Return a copy of a BGR/BGRA image with coloured, optionally numbered points."""
    output = image.copy()
    for point in points:
        color = colors.get(point.index, (220, 220, 220))
        if output.ndim == 3 and output.shape[2] == 4 and len(color) == 3:
            color = (*color, 255)
        cv2.circle(output, (point.x, point.y), radius, color, thickness=2, lineType=cv2.LINE_AA)
        if numbered:
            cv2.putText(output, str(point.index + 1),
                        (point.x + radius + 2, point.y - radius - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34, color, 1, cv2.LINE_AA)
    return output
