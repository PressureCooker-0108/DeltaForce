"""Report and data export for completed ASTM E562 field analyses.

Two audiences are served here:

* :func:`create_pdf_report` produces the submission artefact - specimen identity,
  native resolution, the exact parameters that produced the mask, per-field point
  counts, the ASTM statistics and the visual evidence.
* :func:`points_to_csv` and :func:`fields_to_csv` produce the machine-readable audit
  trails that back those numbers up.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable, Sequence

from astm.counter import FieldCount
from astm.point_classifier import ClassifiedPoint
from astm.statistics import StatisticsResult

_ACCENT = "#173f46"
_GRID = "#9aaab2"
_SHADE = "#e8f4f1"


def points_to_csv(points: Iterable[ClassifiedPoint], field_label: str = "Field 1") -> str:
    """Serialise every grid point, its class, score and origin."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["field", "point", "x", "y", "classification", "score", "source"])
    for point in points:
        writer.writerow([field_label, point.index + 1, point.x, point.y,
                         point.classification, point.score, point.source])
    return buffer.getvalue()


def fields_to_csv(fields: Sequence[object]) -> str:
    """Serialise captured fields: provenance, parameters and ASTM counts."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["field", "field_id", "sample", "sha256", "width", "height", "grid_type",
                     "rotation_deg", "offset_x", "offset_y", "ferrite_points", "boundary_points",
                     "matrix_points", "total_points", "pp_percent", "reviewer_corrections",
                     "captured_at", "parameters"])
    for field in fields:
        parameters = " | ".join(f"{key}={value}" for key, value in field.parameters)
        writer.writerow([field.label, field.field_id, field.image_name, field.image_sha256,
                         field.image_width, field.image_height, field.grid_type,
                         field.grid_rotation, field.grid_offset_x, field.grid_offset_y,
                         field.count.ferrite_points, field.count.boundary_points,
                         field.count.matrix_points, field.count.total_points,
                         f"{field.count.point_fraction_percent:.4f}", field.manual_corrections,
                         field.captured_at, parameters])
    return buffer.getvalue()


def _styled_table(data, col_widths, *, header: bool = True, font_size: int = 9):
    """Build a consistently styled ReportLab table."""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(_GRID)),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_ACCENT)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    table.setStyle(TableStyle(style))
    return table


def create_pdf_report(
    output_path: str | Path,
    image_name: str,
    image_size: tuple[int, int],
    grid_size: int,
    fields: Sequence[FieldCount],
    summary: StatisticsResult,
    *,
    provenance: Sequence[tuple[str, str]] | None = None,
    evidence: Sequence[tuple[str, bytes]] | None = None,
    notes: str | None = None,
) -> Path:
    """Create the ASTM E562 measurement summary PDF and return its path.

    Args:
        output_path: destination file; missing parent directories are created.
        image_name: sample identification, preserved verbatim from the upload.
        image_size: ``(width, height)`` in native pixels.
        grid_size: points per field.
        fields: per-field counts, in capture order.
        summary: ASTM statistics over ``fields``.
        provenance: optional key/value rows; when omitted the report falls back to the
            basic image metadata.
        evidence: optional ``(caption, png_bytes)`` pairs rendered as figures.
        notes: optional free-text reviewer note.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from io import BytesIO
    from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()

    document = SimpleDocTemplate(str(target), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                                 topMargin=17 * mm, bottomMargin=17 * mm,
                                 title=f"ASTM E562 - {image_name}")
    story = [
        Paragraph("ASTM E562 Delta Ferrite Measurement", styles["Title"]),
        Paragraph("Systematic point-counting report", styles["Heading3"]),
        Spacer(1, 6 * mm),
    ]

    rows = [["Property", "Value"]]
    rows += [[key, value] for key, value in (provenance or [
        ("Sample / image", image_name),
        ("Native resolution", f"{image_size[0]:,} x {image_size[1]:,} px"),
        ("Grid", f"{grid_size} points per field"),
        ("Fields captured", str(summary.fields)),
    ])]
    story.append(_styled_table(rows, [50 * mm, 115 * mm]))
    story += [Spacer(1, 7 * mm), Paragraph("ASTM field statistics", styles["Heading2"])]

    statistics_rows = [
        ["Metric", "Value"],
        ["Fields", str(summary.fields)],
        ["Mean ferrite fraction", f"{summary.mean_percent:.2f}%"],
        ["Standard deviation", f"{summary.standard_deviation:.2f}%"],
    ]
    if summary.fields > 1:
        statistics_rows += [
            ["95% confidence interval (two-sided)", f"+/- {summary.confidence_interval:.2f}%"],
            ["Relative accuracy", f"{summary.relative_accuracy:.2f}%"],
        ]
    else:
        statistics_rows.append(["95% confidence interval", "Not estimable from a single field"])
    story.append(_styled_table(statistics_rows, [95 * mm, 70 * mm]))

    story += [Spacer(1, 7 * mm), Paragraph("Per-field point counts", styles["Heading2"])]
    field_rows = [["Field", "Ferrite", "Boundary", "Matrix", "Total", "Pp(i)"]]
    field_rows += [[str(index), str(field.ferrite_points), str(field.boundary_points),
                    str(field.matrix_points), str(field.total_points),
                    f"{field.point_fraction_percent:.2f}%"]
                   for index, field in enumerate(fields, 1)]
    story.append(_styled_table(field_rows, [22 * mm, 26 * mm, 28 * mm, 26 * mm, 24 * mm, 33 * mm]))

    if evidence:
        story += [Spacer(1, 7 * mm), Paragraph("Visual evidence", styles["Heading2"])]
        for caption, png_bytes in evidence:
            try:
                reader = ImageReader(BytesIO(png_bytes))
                width_px, height_px = reader.getSize()
                draw_width = 80 * mm
                draw_height = draw_width * height_px / max(1, width_px)
                story.append(Paragraph(caption, styles["BodyText"]))
                story.append(RLImage(BytesIO(png_bytes), width=draw_width, height=draw_height))
                story.append(Spacer(1, 4 * mm))
            except Exception as error:  # evidence is additive; never fail the report for it
                story.append(Paragraph(f"[evidence image unavailable: {error}]", styles["BodyText"]))

    story += [Spacer(1, 6 * mm), Paragraph("Method", styles["Heading2"])]
    story.append(Paragraph(
        "Each grid point is classified from the ferrite occupancy of a local neighborhood: "
        f"occupancy above {0.80:.2f} scores 1 (ferrite), between 0.20 and 0.80 scores 0.5 "
        "(boundary) and below 0.20 scores 0 (matrix). The reported fraction is "
        "Pp = 100 x (F + 0.5B) / N, which is the ASTM E562 systematic point-count estimator. "
        "Volume fraction is inferred from area fraction under the Delesse principle for a "
        "representative, unbiased planar section. Results depend on the number and "
        "representativeness of the sampled fields; a single field reports no confidence "
        "interval because replication is required to estimate sampling variability.",
        styles["BodyText"]))
    if notes:
        story += [Spacer(1, 4 * mm), Paragraph("Reviewer notes", styles["Heading2"]),
                  Paragraph(notes, styles["BodyText"])]

    document.build(story)
    return target
