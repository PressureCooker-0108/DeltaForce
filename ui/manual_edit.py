"""Manual override semantics for reviewer point corrections.

Overrides are stored as ``{point_index: classification}`` so that a correction survives
mask recomputation, and are applied to a freshly classified grid on every run. Applying
an override never mutates the automatic classification, which keeps the audit trail
between "what the algorithm said" and "what the reviewer decided".
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import config
from astm.point_classifier import ClassifiedPoint

_CYCLE = ("ferrite", "boundary", "matrix")


def cycle_classification(point: ClassifiedPoint) -> ClassifiedPoint:
    """Cycle Ferrite -> Boundary -> Matrix -> Ferrite in one click."""
    if point.classification not in _CYCLE:
        raise KeyError(f"Cannot cycle unknown classification {point.classification!r}")
    nxt = _CYCLE[(_CYCLE.index(point.classification) + 1) % len(_CYCLE)]
    return point.with_classification(nxt, automatic=False)


def apply_overrides(points: Iterable[ClassifiedPoint],
                    overrides: Mapping[int, str]) -> list[ClassifiedPoint]:
    """Return the grid with reviewer overrides applied.

    Points without an override keep their automatic classification and flag, so the
    returned list is always complete: no point can remain unclassified.
    """
    resolved: list[ClassifiedPoint] = []
    for point in points:
        requested = overrides.get(point.index)
        if requested is None or requested not in config.SCORES:
            resolved.append(point)
        else:
            resolved.append(point.with_classification(requested, automatic=False))
    return resolved


def correction_count(points: Sequence[ClassifiedPoint]) -> int:
    """How many points carry a reviewer override."""
    return sum(1 for point in points if not point.automatic)
