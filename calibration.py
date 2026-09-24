"""Calibration mode: software point count versus manual reference counts.

The competition is scored on how close the measured ferrite fraction is to a reference
value, so the application needs a way to tune parameters against known counts instead
of guessing. This module discovers calibration images, reads whatever manual counts are
available, runs the exact production pipeline on each and reports the error.

Manual counts are optional. A CSV with a name column and a percentage column is picked
up automatically from any calibration root; column names are matched loosely so that
``image,manual_ferrite_percent``, ``File,Reference`` and ``sample,count`` all work.
"""
from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from astm.grid import generate_grid
from astm.point_classifier import classify_points
from astm.counter import count_field
from segmentation.pipeline import SegmentationParams, segment

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})
MANUAL_COUNT_FILENAMES = ("manual_counts.csv", "expert_counts.csv", "reference_counts.csv")
_NAME_HINTS = ("image", "file", "sample", "specimen", "name", "id")
_VALUE_HINTS = ("manual", "expert", "reference", "measured", "known", "count")


@dataclass(frozen=True)
class CalibrationRow:
    """One calibration image: reference value against software output."""

    image_name: str
    manual_percent: float | None
    software_percent: float
    error_percent: float | None
    absolute_error_percent: float | None
    ferrite_points: int
    boundary_points: int
    total_points: int

    @property
    def band(self) -> str:
        """Coarse quality label used to colour the table."""
        if self.absolute_error_percent is None:
            return "reference missing"
        if self.absolute_error_percent <= 2.0:
            return "excellent"
        if self.absolute_error_percent <= 5.0:
            return "acceptable"
        return "review"


@dataclass(frozen=True)
class CalibrationReport:
    """Aggregate calibration performance over the discovered images."""

    rows: tuple[CalibrationRow, ...]
    mean_error: float
    mean_absolute_error: float
    root_mean_square_error: float
    duplicates_skipped: int = 0

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def scored_count(self) -> int:
        return sum(1 for row in self.rows if row.manual_percent is not None)

    def summary_line(self) -> str:
        duplicate_note = (f" {self.duplicates_skipped} byte-identical duplicate(s) skipped."
                          if self.duplicates_skipped else "")
        if not self.scored_count:
            return f"{self.count} image(s) measured; no manual reference counts found.{duplicate_note}"
        return (f"{self.scored_count} of {self.count} image(s) scored - "
                f"bias {self.mean_error:+.2f}%, MAE {self.mean_absolute_error:.2f}%, "
                f"RMSE {self.root_mean_square_error:.2f}%.{duplicate_note}")


def discover_images(roots: Iterable[str | Path], limit: int = 60) -> list[Path]:
    """Find candidate calibration images under each root, sorted for stable output."""
    found: list[Path] = []
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                found.append(path)
                if len(found) >= limit:
                    return found
    return found


def _pick_column(header: Sequence[str], hints: Sequence[str]) -> int | None:
    lowered = [str(column).strip().lower() for column in header]
    for hint in hints:
        for index, column in enumerate(lowered):
            if hint in column:
                return index
    return None


def load_manual_counts(roots: Iterable[str | Path]) -> tuple[dict[str, float], list[Path]]:
    """Read manual reference counts.

    Returns:
        ``(counts, sources)`` where ``counts`` maps both the full lower-case filename and
        the stem to a percentage, and ``sources`` lists the CSVs that were read.
    """
    counts: dict[str, float] = {}
    sources: list[Path] = []
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        for csv_path in sorted(base.rglob("*.csv")):
            if csv_path.name.lower() not in MANUAL_COUNT_FILENAMES:
                continue
            try:
                with csv_path.open(newline="", encoding="utf-8-sig") as handle:
                    rows = list(csv.reader(handle))
            except OSError:
                continue
            if len(rows) < 2:
                continue
            header = rows[0]
            name_index = _pick_column(header, _NAME_HINTS)
            value_index = _pick_column(header, _VALUE_HINTS)
            name_index = 0 if name_index is None else name_index
            value_index = 1 if value_index is None or value_index == name_index else value_index
            for row in rows[1:]:
                if len(row) <= max(name_index, value_index):
                    continue
                key = row[name_index].strip()
                if not key or key.lower().startswith("#"):
                    continue
                try:
                    value = float(str(row[value_index]).strip().replace("%", ""))
                except ValueError:
                    continue
                counts[key.lower()] = value
                counts[Path(key).stem.lower()] = value
            sources.append(csv_path)
    return counts, sources


def lookup_manual(counts: dict[str, float], image_path: Path) -> float | None:
    """Resolve a manual count for an image by full name, then by stem."""
    return counts.get(image_path.name.lower(), counts.get(image_path.stem.lower()))


def run_calibration(image_paths: Sequence[Path], params: SegmentationParams, *,
                    grid_size: int, rotation: float, offset: tuple[int, int],
                    neighborhood: int, manual_counts: dict[str, float]) -> CalibrationReport:
    """Run the production pipeline over calibration images and score the output."""
    rows: list[CalibrationRow] = []
    seen_digests: set[str] = set()
    duplicates = 0
    for path in image_paths:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        # The supplied folder contains byte-identical copies under different names;
        # counting them twice would bias the error statistics toward one field.
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen_digests:
            duplicates += 1
            continue
        seen_digests.add(digest)
        try:
            result = segment(data, params, keep_stages=False)
        except Exception:
            continue
        height, width = result.mask.shape
        grid = generate_grid(width, height, grid_size, rotation, offset[0], offset[1])
        points = classify_points(result.mask, grid, neighborhood)
        count = count_field(points)
        manual = lookup_manual(manual_counts, path)
        error = None if manual is None else count.point_fraction_percent - manual
        rows.append(CalibrationRow(
            image_name=path.name,
            manual_percent=manual,
            software_percent=count.point_fraction_percent,
            error_percent=error,
            absolute_error_percent=None if error is None else abs(error),
            ferrite_points=count.ferrite_points,
            boundary_points=count.boundary_points,
            total_points=count.total_points,
        ))

    errors = [row.error_percent for row in rows if row.error_percent is not None]
    absolute = [abs(value) for value in errors]
    return CalibrationReport(
        rows=tuple(rows),
        mean_error=float(np.mean(errors)) if errors else 0.0,
        mean_absolute_error=float(np.mean(absolute)) if absolute else 0.0,
        root_mean_square_error=math.sqrt(float(np.mean([value ** 2 for value in errors]))) if errors else 0.0,
        duplicates_skipped=duplicates,
    )
