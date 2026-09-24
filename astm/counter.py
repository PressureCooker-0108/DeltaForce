"""Per-field ASTM E562 point-count arithmetic (without Phase 3 statistics)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .point_classifier import ClassifiedPoint


@dataclass(frozen=True)
class FieldCount:
    ferrite_points: int
    boundary_points: int
    matrix_points: int
    total_points: int
    point_fraction_percent: float


def count_field(points: Iterable[ClassifiedPoint]) -> FieldCount:
    """Calculate ASTM per-field Pp(i) using full and half boundary scores."""
    values = list(points)
    ferrite = sum(p.classification == "ferrite" for p in values)
    boundary = sum(p.classification == "boundary" for p in values)
    matrix = sum(p.classification == "matrix" for p in values)
    total = len(values)
    fraction = (ferrite + 0.5 * boundary) / total * 100 if total else 0.0
    return FieldCount(ferrite, boundary, matrix, total, fraction)
