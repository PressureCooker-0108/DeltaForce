"""ASTM E562 delta-ferrite measurement dashboard.

Runs fully offline. The pipeline is LAB -> CLAHE -> bilateral -> adaptive threshold ->
Otsu fallback -> opening -> closing -> connected components, followed by systematic
point counting on a 16/25/49/100 point ASTM grid. Images are decoded once at native
resolution and are never cropped or resampled for measurement, so sample
identification markings, scale bars and borders survive into every result and export.
"""
from __future__ import annotations

import hashlib
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import streamlit as st

import calibration
import config
import reporting
from astm.counter import count_field
from astm.field import FieldSnapshot, capture_field
from astm.grid import generate_grid, grid_shape, in_bounds
from astm.point_classifier import classify_points
from astm.statistics import summarize_fields
from segmentation.pipeline import SegmentationParams, segment
from ui import overlay as ov
from ui.manual_edit import apply_overrides, correction_count, cycle_classification

SAMPLE_ROOTS = ("samples", "Total photos")
UPLOAD_TYPES = ["png", "jpg", "jpeg", "tif", "tiff", "bmp"]

# --------------------------------------------------------------------------- #
# Cached compute
# --------------------------------------------------------------------------- #


@st.cache_data(show_spinner=False, max_entries=24)
def run_pipeline(data: bytes, params: SegmentationParams, keep_stages: bool):
    """Cached segmentation. The cache key covers every parameter that moves the mask."""
    return segment(data, params, keep_stages)


@st.cache_data(show_spinner=False, max_entries=96)
def display_png(array: np.ndarray, max_dimension: int = config.DISPLAY_MAX_DIMENSION) -> bytes:
    """Encode an array as PNG for the browser, bounded to ``max_dimension``."""
    image = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR) if array.ndim == 2 else \
        cv2.cvtColor(np.ascontiguousarray(array[:, :, :3]), cv2.COLOR_RGB2BGR)
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > max_dimension:
        scale = max_dimension / float(longest)
        image = cv2.resize(image, (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                           interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".png", image, [int(cv2.IMWRITE_PNG_COMPRESSION), 6])
    if not ok:
        raise ValueError("Could not encode the image for display.")
    return buffer.tobytes()


@st.cache_data(show_spinner=False, max_entries=32)
def evidence_jpeg(array: np.ndarray, max_dimension: int = config.REPORT_EVIDENCE_MAX_DIMENSION,
                  quality: int = config.REPORT_EVIDENCE_JPEG_QUALITY) -> bytes:
    """Encode an array as JPEG for the PDF evidence figures.

    Deliberately separate from :func:`display_png`: full-resolution lossless PNGs made
    the submission report roughly 16 MB, which is impractical to hand in.
    """
    image = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR) if array.ndim == 2 else \
        cv2.cvtColor(np.ascontiguousarray(array[:, :, :3]), cv2.COLOR_RGB2BGR)
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > max_dimension:
        scale = max_dimension / float(longest)
        image = cv2.resize(image, (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                           interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("Could not encode the evidence image.")
    return buffer.tobytes()


@st.cache_data(show_spinner=False, max_entries=8)
def build_report_pdf(fields: tuple, image_name: str, image_size: tuple, grid_size: int,
                     provenance: tuple, evidence: tuple, notes: str) -> bytes:
    """Render the submission PDF in a temporary directory and return its bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "astm_e562_report.pdf"
        reporting.create_pdf_report(
            target, image_name, image_size, grid_size,
            [snapshot.count for snapshot in fields], summarize_fields([s.count for s in fields]),
            provenance=list(provenance), evidence=list(evidence), notes=notes or None,
        )
        return target.read_bytes()


@st.cache_data(show_spinner=False, max_entries=4)
def run_calibration_cached(paths: tuple, params: SegmentationParams, grid_size: int, rotation: float,
                           offset: tuple, neighborhood: int, counts: tuple) -> calibration.CalibrationReport:
    """Cached calibration sweep over the discovered dataset."""
    return calibration.run_calibration([Path(p) for p in paths], params, grid_size=grid_size,
                                       rotation=rotation, offset=offset, neighborhood=neighborhood,
                                       manual_counts=dict(counts))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def initialize_state() -> None:
    """Create the persistent state required by the review and multi-field workflow."""
    defaults: dict[str, Any] = {
        "overrides": {},
        "fields": [],
        "analyzed_signature": None,
        "active_selection": frozenset(),
        "grid_signature": None,
        "calibration_report": None,
        "report_notes": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sample_library() -> dict[str, Path]:
    """Index every micrograph shipped with the project so it can be demoed offline."""
    library: dict[str, Path] = {}
    for root in SAMPLE_ROOTS:
        base = Path(root)
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in calibration.IMAGE_SUFFIXES:
                library.setdefault(path.name, path)
    return library


def safe_stem(name: str) -> str:
    """Turn a sample name into a filesystem-safe stem, preserving identification."""
    cleaned = "".join(character if (character.isalnum() or character in "-_.") else "_" for character in name)
    return (cleaned.strip("_") or "sample")[:80]


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #

st.set_page_config(page_title=config.APP_TITLE, page_icon="🔬", layout="wide")
initialize_state()

library = sample_library()

with st.sidebar:
    st.title("ASTM E562")
    st.caption(f"{config.APP_VERSION} · offline")

    st.header("1 · Sample")
    source_mode = st.radio("Image source", ["Upload", "Dataset"], horizontal=True, key="source_mode")
    data: bytes | None = None
    image_name: str | None = None
    if source_mode == "Upload":
        uploaded = st.file_uploader("Micrograph", type=UPLOAD_TYPES, key="uploader")
        if uploaded is not None:
            data = uploaded.getvalue()
            image_name = uploaded.name
    elif library:
        choice = st.selectbox("Dataset micrograph", list(library), key="dataset_choice")
        data = library[choice].read_bytes()
        image_name = choice
    else:
        st.warning("No dataset folder found. Add micrographs to `samples/` or use Upload.")

    st.header("2 · Enhancement")
    clip_limit = st.slider("CLAHE clip limit", *config.CLAHE_CLIP_RANGE,
                           config.DEFAULT_CLAHE_CLIP_LIMIT, 0.1, key="clip_limit")
    tile_size = st.slider("CLAHE tile size", *config.CLAHE_TILE_RANGE,
                          config.DEFAULT_CLAHE_TILE_SIZE, 2, key="tile_size")

    st.header("3 · Segmentation")
    threshold_mode = st.selectbox(
        "Threshold mode", config.THRESHOLD_MODES,
        index=config.THRESHOLD_MODES.index(config.DEFAULT_THRESHOLD_MODE),
        format_func=lambda key: config.THRESHOLD_MODE_LABELS[key], key="threshold_mode",
        help="Auto uses the global Otsu threshold when the L histogram is strongly "
             "bimodal, and the adaptive result otherwise.")
    block_size = st.slider("Adaptive block size", *config.BLOCK_SIZE_RANGE,
                           config.DEFAULT_BLOCK_SIZE, 2, key="block_size",
                           help="Must be odd; forced odd if changed programmatically.")
    adaptive_c = st.slider("Adaptive threshold C", *config.ADAPTIVE_C_RANGE,
                           config.DEFAULT_ADAPTIVE_C, 1, key="adaptive_c")
    polarity = st.radio("Polarity", [config.POLARITY_DARK, config.POLARITY_BRIGHT],
                        index=0, format_func=lambda key: config.POLARITY_LABELS[key],
                        key="polarity",
                        help="Which brightness corresponds to delta ferrite for this etch.")
    morphology_kernel = st.slider("Morphology kernel", *config.MORPHOLOGY_KERNEL_RANGE,
                                  config.DEFAULT_MORPHOLOGY_KERNEL, 2, key="morphology_kernel")
    minimum_area = st.slider("Minimum component area (px)", *config.MINIMUM_AREA_RANGE,
                             config.DEFAULT_MINIMUM_AREA, 1, key="minimum_area")
    separability_gate = st.slider("Otsu bimodality gate (eta)", *config.OTSU_SEPARABILITY_RANGE,
                                  config.OTSU_SEPARABILITY_GATE, 0.05, key="separability_gate")

    st.header("4 · ASTM grid")
    grid_type = st.radio("Grid type", list(config.SUPPORTED_GRID_SIZES), index=0,
                         format_func=lambda value: f"{value} points", key="grid_type")
    rotation = st.slider("Grid rotation (deg)", *config.GRID_ROTATION_RANGE,
                         config.DEFAULT_GRID_ROTATION, 1.0, key="rotation")
    offset_x = st.slider("Grid offset X (px)", *config.GRID_OFFSET_RANGE,
                         config.DEFAULT_GRID_OFFSET, 5, key="offset_x")
    offset_y = st.slider("Grid offset Y (px)", *config.GRID_OFFSET_RANGE,
                         config.DEFAULT_GRID_OFFSET, 5, key="offset_y")
    neighborhood = st.slider("Point neighborhood", *config.NEIGHBORHOOD_RANGE,
                             config.DEFAULT_NEIGHBORHOOD, 2, key="neighborhood",
                             help="Window used to decide each point's class. ASTM default is 5x5.")

    st.divider()
    analyze_clicked = st.button("Analyze", type="primary", width="stretch", key="analyze")
    reset_clicked = st.button("Reset", width="stretch", key="reset",
                              help="Clears reviewer corrections and unpublishes the result.")
    clear_fields_clicked = st.button("Clear captured fields", width="stretch", key="clear_fields")

    st.header("5 · Display")
    developer_mode = st.toggle("Developer mode", key="developer_mode",
                               help="Show every intermediate pipeline stage.")
    show_numbers = st.toggle("Show point numbers", value=False, key="show_numbers")
    show_ambiguity = st.toggle("Ambiguity heatmap", value=False, key="show_ambiguity")

if data is None or image_name is None:
    st.title(config.APP_TITLE)
    st.info("Select a micrograph from the dataset, or upload one, to run the ASTM E562 pipeline.")
    st.caption("The application runs entirely offline. Nothing is uploaded anywhere.")
    st.stop()

if reset_clicked:
    st.session_state.overrides = {}
    st.session_state.analyzed_signature = None
    st.session_state.active_selection = frozenset()
    st.rerun()
if clear_fields_clicked:
    st.session_state.fields = []
    st.session_state.calibration_report = None
    st.rerun()

params = SegmentationParams(
    clip_limit=float(clip_limit), tile_size=int(tile_size), threshold_mode=str(threshold_mode),
    block_size=int(block_size), adaptive_c=int(adaptive_c), polarity=str(polarity),
    morphology_kernel=int(morphology_kernel), minimum_area=int(minimum_area),
    separability_gate=float(separability_gate),
)

file_id = hashlib.sha256(data).hexdigest()

# Geometry changes move the grid, so index-keyed overrides would silently land on
# different pixels. Clearing them here closes that measurement-integrity hole.
grid_signature = f"{file_id}|{grid_type}|{rotation}|{offset_x}|{offset_y}"
if st.session_state.grid_signature != grid_signature:
    st.session_state.grid_signature = grid_signature
    st.session_state.overrides = {}
    st.session_state.active_selection = frozenset()

try:
    with st.spinner("Running LAB enhancement and ferrite segmentation…"):
        result = run_pipeline(data, params, bool(developer_mode))
except Exception as error:  # a decode/parameter failure must not kill the session
    st.error(f"Pipeline error: {error}")
    st.stop()

native_height, native_width = result.height, result.width
grid = generate_grid(native_width, native_height, int(grid_type), float(rotation),
                     float(offset_x), float(offset_y), config.GRID_MARGIN)
automatic_points = classify_points(result.mask, grid, int(neighborhood))
points = apply_overrides(automatic_points, st.session_state.overrides)
field_count = count_field(points)
rows, columns = grid_shape(int(grid_type))

# Publication signature covers everything that defines the number except reviewer
# edits, so a correction updates the dashboard live but a parameter change does not
# silently republish a different measurement.
signature = hashlib.sha256(repr((file_id, params, grid_type, rotation, offset_x, offset_y,
                                 neighborhood)).encode()).hexdigest()
if analyze_clicked:
    st.session_state.analyzed_signature = signature
published = st.session_state.analyzed_signature == signature
stale = st.session_state.analyzed_signature is not None and not published

# --------------------------------------------------------------------------- #
# Header / provenance
# --------------------------------------------------------------------------- #
title_column, badge_column = st.columns([4, 1])
with title_column:
    st.title(config.APP_TITLE)
    st.caption(f"{config.APP_CAPTION} · {config.APP_VERSION}")
with badge_column:
    st.write("")
    if published:
        st.success("PUBLISHED")
    else:
        st.warning("PRELIMINARY")

st.markdown(
    f"**Sample:** `{image_name}` &nbsp;|&nbsp; **SHA-256:** `{file_id[:16]}` &nbsp;|&nbsp; "
    f"**Native resolution:** {native_width:,} × {native_height:,} px "
    f"({result.megapixels:.2f} MPix) &nbsp;|&nbsp; **Threshold:** {result.threshold.method}"
)

if stale:
    st.warning("Parameters changed since the last Analyze. Press **Analyze** to republish the result.")
if not in_bounds(grid, native_width, native_height):
    st.error("Grid points fell outside the image bounds; reduce the rotation or offset.")

# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
top_left, top_right = st.columns(2)
with top_left:
    st.subheader("1 · Original image")
    st.image(display_png(result.original_rgb), width="stretch")
    st.caption(f"Native {native_width:,} × {native_height:,} px. Markings and scale bar preserved; "
               "display is scaled for the browser only.")
with top_right:
    st.subheader("2 · Enhanced image")
    st.image(display_png(result.enhanced_rgb), width="stretch")
    st.caption("LAB L-channel CLAHE, then edge-preserving bilateral filter.")

bottom_left, bottom_right = st.columns(2)
with bottom_left:
    st.subheader("3 · Ferrite mask")
    mask_view = ov.heatmap_overlay(result.original_rgb, result.mask) if show_ambiguity else result.mask
    st.image(display_png(np.asarray(mask_view)), width="stretch")
    st.caption(f"White = detected delta ferrite. Coverage {result.coverage * 100:.2f}% of field "
               f"({result.components.kept:,} of {result.components.total:,} components kept).")
with bottom_right:
    st.subheader("4 · ASTM grid overlay")
    if show_numbers:
        st.image(display_png(ov.draw_numbered_grid(result.original_rgb, points, radius=3, numbered=True)),
                 width="stretch")
        st.caption(f"{grid_type}-point grid ({rows} × {columns}), rotation {rotation:g}°, "
                   f"offset ({offset_x}, {offset_y}) px. Click a circle in the interactive overlay below to cycle its class.")
    display_image, display_scale = ov.fit_for_display(result.original_rgb)
    event = st.plotly_chart(
        ov.plotly_grid_figure(display_image, points, display_scale),
        on_select="rerun", selection_mode="points", key="astm_overlay", width="stretch",
    )
    st.caption(f"{grid_type}-point grid ({rows} × {columns}), rotation {rotation:g}°, "
               f"offset ({offset_x}, {offset_y}) px. Green = ferrite (1), yellow = boundary (0.5), "
               "red = matrix (0). Click a circle to cycle its class; diamonds are reviewer overrides.")

# Click-to-cycle. Plotly keeps a cumulative selection, so the previously selected set
# is diffed and only genuinely newly selected points are cycled. The previous
# `selected[-1]` approach could act on the wrong point or silently do nothing.
if not show_numbers:
    selected: set[int] = set()
    if isinstance(event, dict):
        for item in ((event.get("selection") or {}).get("points") or []):
            custom = item.get("customdata")
            if custom:
                selected.add(int(custom[0]))
    newly_selected = selected - set(st.session_state.active_selection)
    st.session_state.active_selection = frozenset(selected)
    if newly_selected:
        for index in sorted(newly_selected):
            if 0 <= index < len(points):
                st.session_state.overrides[index] = cycle_classification(points[index]).classification
        st.rerun()

# --------------------------------------------------------------------------- #
# Live dashboard
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Live results")
if not published:
    st.info("Preliminary values. Press **Analyze** to publish this field.")

card_columns = st.columns(6)
card_columns[0].metric("Ferrite %", f"{field_count.point_fraction_percent:.2f}%")
card_columns[1].metric("Ferrite points", field_count.ferrite_points)
card_columns[2].metric("Boundary points", field_count.boundary_points)
card_columns[3].metric("Matrix points", field_count.matrix_points)
card_columns[4].metric("Total grid points", field_count.total_points)
card_columns[5].metric("Grid type", f"{grid_type}", help=f"{rows} × {columns} lattice")
st.caption(
    f"Pp = 100 × (F + 0.5B) / N = 100 × ({field_count.ferrite_points} + 0.5 × "
    f"{field_count.boundary_points}) / {field_count.total_points} = "
    f"**{field_count.point_fraction_percent:.2f}%** · "
    f"Otsu separability η = {result.threshold.separability:.3f} · "
    f"reviewer corrections: {correction_count(points)} · "
    f"pipeline {result.elapsed_ms:.0f} ms"
)

# --------------------------------------------------------------------------- #
# Multi-field ASTM statistics
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Multi-field ASTM statistics")
capture_column, fields_column = st.columns([1, 3])
with capture_column:
    if st.button("Add current field", width="stretch", disabled=not published,
                 help="Capture an immutable snapshot of this field's parameters, grid and points."):
        index = len(st.session_state.fields) + 1
        st.session_state.fields.append(capture_field(
            field_id=uuid.uuid4().hex[:8], label=f"Field {index}", image_name=image_name,
            image_sha256=file_id, image_size=(native_width, native_height), grid_type=int(grid_type),
            grid_rotation=float(rotation), grid_offset=(int(offset_x), int(offset_y)),
            neighborhood=int(neighborhood), threshold_method=result.threshold.method,
            parameters=params.as_provenance(), points=points,
        ))
        st.rerun()
    if not published:
        st.caption("Press Analyze first.")

fields: list[FieldSnapshot] = st.session_state.fields
with fields_column:
    if not fields:
        st.info("Capture at least two independent fields to obtain a confidence interval.")
    else:
        summary = summarize_fields([snapshot.count for snapshot in fields])
        stat_columns = st.columns(4)
        stat_columns[0].metric("Fields", summary.fields)
        stat_columns[1].metric("Mean ferrite", f"{summary.mean_percent:.2f}%")
        stat_columns[2].metric("Std deviation", f"{summary.standard_deviation:.2f}%")
        if summary.fields > 1:
            stat_columns[3].metric(f"{int(config.DEFAULT_CONFIDENCE_LEVEL * 100)}% CI",
                                   f"± {summary.confidence_interval:.2f}%",
                                   help=f"Relative accuracy {summary.relative_accuracy:.2f}%")
        else:
            stat_columns[3].metric("95% CI", "n/a",
                                   help="A single field cannot estimate sampling variability.")
        st.dataframe([{
            "Field": snapshot.label,
            "Sample": snapshot.image_name,
            "Ferrite %": round(snapshot.count.point_fraction_percent, 2),
            "F": snapshot.count.ferrite_points,
            "B": snapshot.count.boundary_points,
            "M": snapshot.count.matrix_points,
            "Grid": snapshot.grid_type,
            "Corrections": snapshot.manual_corrections,
        } for snapshot in fields], width="stretch")

# --------------------------------------------------------------------------- #
# Manual correction
# --------------------------------------------------------------------------- #
with st.expander("Manual point correction and audit trail", expanded=False):
    st.caption("Every point carries a class and an origin. Corrections update the dashboard "
               "immediately and are recorded as reviewer decisions.")
    edit_columns = st.columns([1, 1, 1, 1, 2])
    point_number = edit_columns[0].number_input("Point #", min_value=1, max_value=max(1, len(points)),
                                                value=1, step=1, key="edit_point")
    target_point = points[point_number - 1] if points else None
    if target_point is not None:
        current_index = config.CATEGORY_ORDER.index(target_point.classification)
        target_class = edit_columns[1].selectbox("Class", list(config.CATEGORY_ORDER),
                                                 index=current_index,
                                                 format_func=lambda key: config.CATEGORY_LABELS[key],
                                                 key="edit_class")
        edit_columns[2].write("")
        if edit_columns[2].button("Apply", width="stretch", key="apply_edit"):
            st.session_state.overrides[target_point.index] = target_class
            st.rerun()
        edit_columns[3].write("")
        if edit_columns[3].button("Clear", width="stretch", key="clear_edit", disabled=target_point.automatic):
            st.session_state.overrides.pop(target_point.index, None)
            st.rerun()
        edit_columns[4].caption(
            f"Point {target_point.index + 1} at ({target_point.x}, {target_point.y}) px · "
            f"automatic = {config.CATEGORY_LABELS[automatic_points[target_point.index].classification]} · "
            f"effective = {target_point.label} · source = {target_point.source}"
        )
    if st.session_state.overrides:
        if st.button(f"Clear all {len(st.session_state.overrides)} corrections", key="clear_all_edits"):
            st.session_state.overrides = {}
            st.rerun()
    st.dataframe([{
        "Point": point.index + 1, "x": point.x, "y": point.y,
        "Automatic": config.CATEGORY_LABELS[automatic_points[point.index].classification],
        "Effective": point.label, "Score": point.score, "Source": point.source,
    } for point in points], width="stretch", height=280)

# --------------------------------------------------------------------------- #
# Developer mode
# --------------------------------------------------------------------------- #
if developer_mode and result.stages.lightness is not None:
    st.divider()
    st.subheader("Developer mode · pipeline stages")
    st.caption("Diagnostics only. Analysis always uses the native-resolution mask from stage 9.")
    dev_rows = [
        [("LAB L-channel (raw)", result.stages.lightness_raw),
         ("CLAHE on L", result.stages.clahe_rgb),
         ("Bilateral enhanced", result.stages.enhanced_rgb)],
        [("Threshold output (bright = white)", result.stages.threshold_bright),
         ("After opening", result.stages.opened),
         ("After closing", result.stages.closed)],
        [("Polarity applied", result.stages.polarity_mask),
         ("Connected components", result.stages.label_view),
         ("Final ferrite mask", result.mask)],
    ]
    for row in dev_rows:
        columns_dev = st.columns(3)
        for column, (caption, image) in zip(columns_dev, row):
            with column:
                st.image(display_png(np.asarray(image)), width="stretch", caption=caption)
    diagnostics = st.columns(4)
    diagnostics[0].metric("Otsu threshold", f"{result.threshold.otsu_value:.0f}")
    diagnostics[1].metric("Separability η", f"{result.threshold.separability:.3f}")
    diagnostics[2].metric("Adaptive coverage", f"{result.threshold.adaptive_coverage * 100:.1f}%")
    diagnostics[3].metric("Mask coverage", f"{result.coverage * 100:.2f}%")
    st.caption(
        f"Method: {result.threshold.method} · components {result.components.total:,} total, "
        f"{result.components.kept:,} kept, {result.components.rejected:,} rejected · "
        f"largest component {result.components.largest_area:,} px "
        f"({result.components.field_fraction * 100:.2f}% of field) · "
        f"median component {result.components.median_area:.0f} px"
    )

# --------------------------------------------------------------------------- #
# Calibration mode
# --------------------------------------------------------------------------- #
st.divider()
with st.expander("Calibration mode · software vs manual ASTM counts", expanded=False):
    dataset_images = calibration.discover_images(SAMPLE_ROOTS)
    manual_counts, manual_sources = calibration.load_manual_counts(SAMPLE_ROOTS)
    st.caption(
        f"{len(dataset_images)} image(s) discovered under {', '.join(f'`{root}`' for root in SAMPLE_ROOTS)}. "
        f"Manual reference counts: "
        + (", ".join(f"`{path.name}`" for path in manual_sources) if manual_sources else "none found")
    )
    if manual_sources:
        preview = {path: value for path, value in list(manual_counts.items())[:5]}
        st.caption("Reference values detected (first entries): "
                   + ", ".join(f"{key}={value:g}%" for key, value in preview.items()))
    else:
        st.caption("Add `samples/calibration/manual_counts.csv` with `image,manual_percent` columns "
                   "to score the pipeline against known values.")
    if st.button("Run calibration with current parameters", key="run_calibration"):
        with st.spinner("Measuring every calibration image…"):
            st.session_state.calibration_report = run_calibration_cached(
                tuple(str(path) for path in dataset_images), params, int(grid_type), float(rotation),
                (int(offset_x), int(offset_y)), int(neighborhood),
                tuple(sorted(manual_counts.items())),
            )
    report: calibration.CalibrationReport | None = st.session_state.calibration_report
    if report is not None:
        st.write(report.summary_line())
        st.dataframe([{
            "Image": row.image_name,
            "Manual %": None if row.manual_percent is None else round(row.manual_percent, 2),
            "Software %": round(row.software_percent, 2),
            "Error %": None if row.error_percent is None else round(row.error_percent, 2),
            "Abs error %": None if row.absolute_error_percent is None else round(row.absolute_error_percent, 2),
            "Verdict": row.band,
            "F": row.ferrite_points, "B": row.boundary_points, "N": row.total_points,
        } for row in report.rows], width="stretch")

# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Export ASTM results")
st.caption("Exports carry the sample name, its SHA-256, the native resolution, the grid geometry "
           "and every parameter that produced the mask.")

report_fields = tuple(fields) if fields else (capture_field(
    field_id=uuid.uuid4().hex[:8], label="Field 1", image_name=image_name, image_sha256=file_id,
    image_size=(native_width, native_height), grid_type=int(grid_type), grid_rotation=float(rotation),
    grid_offset=(int(offset_x), int(offset_y)), neighborhood=int(neighborhood),
    threshold_method=result.threshold.method, parameters=params.as_provenance(), points=points,
),)

st.session_state.report_notes = st.text_input("Reviewer notes (optional)", value=st.session_state.report_notes,
                                              key="notes_input")
provenance = report_fields[0].provenance_rows()

try:
    with st.spinner("Preparing report evidence…"):
        evidence = (
            ("Original image (native resolution, markings preserved)",
             evidence_jpeg(result.original_rgb)),
            ("Ferrite mask", evidence_jpeg(np.asarray(result.mask))),
            ("ASTM grid overlay",
             evidence_jpeg(ov.draw_numbered_grid(result.original_rgb, points, radius=4, numbered=True))),
            ("Detected phase over original",
             evidence_jpeg(ov.mask_blend_overlay(result.original_rgb, result.mask))),
        )
        pdf_bytes = build_report_pdf(report_fields, image_name, (native_width, native_height),
                                     int(grid_type), tuple(provenance), evidence,
                                     st.session_state.report_notes)
    report_error = None
except Exception as error:  # a report failure must not take the dashboard down
    pdf_bytes = b""
    report_error = error

stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
stem = safe_stem(Path(image_name).stem)
export_columns = st.columns(5)
with export_columns[0]:
    if pdf_bytes:
        st.download_button("PDF report", pdf_bytes, file_name=f"astm_e562_{stem}_{stamp}.pdf",
                           mime="application/pdf", width="stretch", disabled=not published)
    else:
        st.button("PDF report", disabled=True, width="stretch")
with export_columns[1]:
    st.download_button("Field CSV", reporting.fields_to_csv(report_fields),
                       file_name=f"astm_e562_{stem}_fields_{stamp}.csv", mime="text/csv",
                       width="stretch", disabled=not published)
with export_columns[2]:
    st.download_button("Point CSV", reporting.points_to_csv(points, report_fields[0].label),
                       file_name=f"astm_e562_{stem}_points_{stamp}.csv", mime="text/csv",
                       width="stretch")
with export_columns[3]:
    st.download_button("Mask PNG", display_png(np.asarray(result.mask), 100000),
                       file_name=f"astm_e562_{stem}_mask.png", mime="image/png", width="stretch")
with export_columns[4]:
    st.download_button("Overlay PNG",
                       display_png(ov.draw_numbered_grid(result.original_rgb, points, radius=5), 100000),
                       file_name=f"astm_e562_{stem}_overlay.png", mime="image/png", width="stretch")

if report_error is not None:
    st.warning(f"Report rendering failed: {report_error}")
if not published:
    st.caption("Press **Analyze** to enable the final report and field exports.")

with st.expander("Provenance and parameters", expanded=False):
    st.dataframe([{"Property": key, "Value": value} for key, value in provenance], width="stretch")
