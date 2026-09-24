"""Phase 3 ASTM E562 multi-field descriptive statistics."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, stdev
from typing import Iterable

from .counter import FieldCount

# Two-sided 95% Student t critical values, df 1-30; normal approximation above.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
        13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
        18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
        23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052,
        28: 2.048, 29: 2.045, 30: 2.042}


@dataclass(frozen=True)
class StatisticsResult:
    """Competition-facing ASTM field summary, expressed in percent."""

    fields: int
    mean_percent: float
    standard_deviation: float
    confidence_interval: float
    relative_accuracy: float


def summarize_fields(fields: Iterable[FieldCount]) -> StatisticsResult:
    """Summarize independent field fractions with a two-sided 95% CI.

    A single field reports zero variation/CI because replication is required to
    estimate sampling variability. This is deliberately distinct from Phase 2.
    """
    values = [field.point_fraction_percent for field in fields]
    count = len(values)
    if not count:
        return StatisticsResult(0, 0.0, 0.0, 0.0, 0.0)
    average = mean(values)
    if count == 1:
        return StatisticsResult(1, average, 0.0, 0.0, 0.0)
    deviation = stdev(values)
    critical = _T95.get(count - 1, 1.96)
    interval = critical * deviation / sqrt(count)
    accuracy = interval / average * 100 if average else 0.0
    return StatisticsResult(count, average, deviation, interval, accuracy)
