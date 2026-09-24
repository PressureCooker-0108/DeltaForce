"""Classification of systematic grid points against a binary ferrite mask."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

import config
from .boundary import classify_ratio, ferrite_ratio
from .grid import GridPoint


@dataclass(frozen=True)
class ClassifiedPoint:
    """One fully classified ASTM point, optionally overridden by a reviewer.

    Frozen so that captured fields are immutable records and so that snapshots stay
    hashable for caching.
    """

    index: int
    x: int
    y: int
    classification: str
    score: float
    automatic: bool = True

    @property
    def label(self) -> str:
        """Title-case display label for this classification."""
        return config.CATEGORY_LABELS.get(self.classification, self.classification.title())

    @property
    def source(self) -> str:
        """``"auto"`` or ``"manual"``, for the audit trail."""
        return "auto" if self.automatic else "manual"

    def with_classification(self, classification: str, automatic: bool = False) -> "ClassifiedPoint":
        """Return a copy carrying a new classification and its ASTM score."""
        if classification not in config.SCORES:
            raise KeyError(f"Unknown classification {classification!r}")
        return ClassifiedPoint(self.index, self.x, self.y, classification,
                               config.SCORES[classification], automatic)


def classify_point(mask: np.ndarray, point: GridPoint,
                   neighborhood: int = config.DEFAULT_NEIGHBORHOOD) -> ClassifiedPoint:
    """Classify one grid point; every point receives exactly one class and score."""
    kind, score = classify_ratio(ferrite_ratio(mask, point.x, point.y, neighborhood))
    return ClassifiedPoint(point.index, point.x, point.y, kind, score, True)


def classify_points(mask: np.ndarray, points: Iterable[GridPoint],
                    neighborhood: int = config.DEFAULT_NEIGHBORHOOD) -> list[ClassifiedPoint]:
    """Classify every point in a systematic grid."""
    return [classify_point(mask, point, neighborhood) for point in points]
