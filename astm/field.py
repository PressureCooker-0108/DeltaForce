"""Immutable per-field capture for the multi-field ASTM E562 workflow.

A :class:`FieldSnapshot` freezes everything needed to reproduce and defend a single
field's point fraction: the specimen identity, the exact segmentation parameters, the
grid geometry, every point classification with its origin (automatic or reviewer
override), the derived count, and a timestamp. Because it is a frozen dataclass of
hashable values, later slider movement cannot retroactively change a captured field.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from astm.counter import FieldCount, count_field
from astm.point_classifier import ClassifiedPoint


@dataclass(frozen=True)
class FieldSnapshot:
    """A frozen, auditable record of one measured field."""

    field_id: str
    label: str
    image_name: str
    image_sha256: str
    image_width: int
    image_height: int
    grid_type: int
    grid_rotation: float
    grid_offset_x: int
    grid_offset_y: int
    neighborhood: int
    threshold_method: str
    parameters: tuple[tuple[str, str], ...]
    points: tuple[ClassifiedPoint, ...]
    count: FieldCount
    captured_at: str

    @property
    def image_size(self) -> tuple[int, int]:
        return self.image_width, self.image_height

    @property
    def megapixels(self) -> float:
        return self.image_width * self.image_height / 1e6

    @property
    def manual_corrections(self) -> int:
        """How many points the reviewer overrode away from the automatic result."""
        return sum(1 for point in self.points if not point.automatic)

    @property
    def short_hash(self) -> str:
        return self.image_sha256[:12]

    def provenance_rows(self) -> list[tuple[str, str]]:
        """Ordered key/value pairs for a report header or metadata table."""
        return [
            ("Field", self.label),
            ("Field ID", self.field_id),
            ("Sample / image", self.image_name),
            ("SHA-256", self.image_sha256),
            ("Native resolution", f"{self.image_width:,} x {self.image_height:,} px "
                                  f"({self.megapixels:.2f} MPix)"),
            ("Grid", f"{self.grid_type} points ({self.grid_columns} x {self.grid_rows})"),
            ("Grid rotation", f"{self.grid_rotation:g} deg"),
            ("Grid offset", f"({self.grid_offset_x}, {self.grid_offset_y}) px"),
            ("Neighborhood", f"{self.neighborhood} x {self.neighborhood}"),
            ("Threshold", self.threshold_method),
            *self.parameters,
            ("Reviewer corrections", str(self.manual_corrections)),
            ("Captured at (UTC)", self.captured_at),
        ]

    @property
    def grid_rows(self) -> int:
        from astm.grid import grid_shape
        return grid_shape(self.grid_type)[0]

    @property
    def grid_columns(self) -> int:
        from astm.grid import grid_shape
        return grid_shape(self.grid_type)[1]

    def point_rows(self) -> list[dict[str, object]]:
        """Per-point audit rows: index, coordinates, ratio class and origin."""
        return [
            {"Point": point.index + 1,
             "x": point.x,
             "y": point.y,
             "Class": point.label,
             "Score": point.score,
             "Source": point.source}
            for point in self.points
        ]


def capture_field(
    *,
    field_id: str,
    label: str,
    image_name: str,
    image_sha256: str,
    image_size: tuple[int, int],
    grid_type: int,
    grid_rotation: float,
    grid_offset: tuple[int, int],
    neighborhood: int,
    threshold_method: str,
    parameters: tuple[tuple[str, str], ...],
    points: Sequence[ClassifiedPoint],
) -> FieldSnapshot:
    """Build an immutable snapshot from the current review state."""
    frozen_points = tuple(points)
    return FieldSnapshot(
        field_id=field_id,
        label=label,
        image_name=image_name,
        image_sha256=image_sha256,
        image_width=int(image_size[0]),
        image_height=int(image_size[1]),
        grid_type=int(grid_type),
        grid_rotation=float(grid_rotation),
        grid_offset_x=int(grid_offset[0]),
        grid_offset_y=int(grid_offset[1]),
        neighborhood=int(neighborhood),
        threshold_method=threshold_method,
        parameters=tuple(parameters),
        points=frozen_points,
        count=count_field(frozen_points),
        captured_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )
