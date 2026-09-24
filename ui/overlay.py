"""Plotly and OpenCV overlays for the ASTM grid, plus display-scaling helpers.

Display scaling is confined to this module. The measurement always runs on the native
resolution arrays produced by :mod:`segmentation.pipeline`; :func:`fit_for_display`
exists only so the browser is not asked to rasterise a 6 MPix image, and it reports the
scale factor so grid markers stay registered to the pixels underneath them.
"""
from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np
import plotly.graph_objects as go

import config
from astm.grid import GridPoint, draw_grid
from astm.point_classifier import ClassifiedPoint


def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    """Convert ``#rrggbb`` to an OpenCV BGR tuple."""
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return blue, green, red


POINT_COLORS_BGR = {name: hex_to_bgr(color) for name, color in config.CATEGORY_COLORS.items()}


def fit_for_display(array: np.ndarray,
                    max_dimension: int = config.DISPLAY_MAX_DIMENSION) -> tuple[np.ndarray, float]:
    """Downscale an array to fit the browser, returning ``(array, scale)``.

    ``scale`` is ``displayed_size / native_size`` and is exactly what marker
    coordinates must be multiplied by so that a displayed grid lands on the same
    pixels it would in the native image.
    """
    height, width = array.shape[:2]
    longest = max(height, width)
    if longest <= max_dimension:
        return array, 1.0
    scale = max_dimension / float(longest)
    resized = cv2.resize(array, (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                         interpolation=cv2.INTER_AREA)
    return resized, scale


def plotly_grid_figure(display_image: np.ndarray, points: Sequence[ClassifiedPoint], scale: float,
                       title: str = "") -> go.Figure:
    """Selectable grid overlay.

    Each marker's ``customdata`` carries the *native* point index, so a browser click
    is resolved back to the correct grid point regardless of display scaling.
    """
    figure = go.Figure(go.Image(z=display_image))
    if points:
        figure.add_trace(go.Scatter(
            x=[point.x * scale for point in points],
            y=[point.y * scale for point in points],
            mode="markers",
            marker={
                "size": 12,
                "color": [config.CATEGORY_COLORS.get(point.classification, "#888888") for point in points],
                "line": {"color": "white", "width": 1},
                "symbol": ["circle" if point.automatic else "diamond" for point in points],
            },
            customdata=[[point.index, point.label, point.score, point.source] for point in points],
            hovertemplate=("Point %{customdata[0]}<br>%{customdata[1]}<br>"
                           "Score %{customdata[2]}<br>Source %{customdata[3]}<extra></extra>"),
            name="ASTM points",
        ))
    figure.update_layout(
        title={"text": title, "font": {"size": 13}} if title else None,
        height=520,
        margin={"l": 0, "r": 0, "t": 28 if title else 0, "b": 0},
        dragmode="select",
        showlegend=False,
        xaxis={"visible": False, "range": [0, display_image.shape[1]]},
        yaxis={"visible": False, "range": [display_image.shape[0], 0], "scaleanchor": "x"},
    )
    return figure


def draw_numbered_grid(image_rgb: np.ndarray, points: Sequence[ClassifiedPoint],
                       radius: int = 5, numbered: bool = True) -> np.ndarray:
    """Render the grid on an RGB copy of the image, returning RGB."""
    positions = [GridPoint(point.index, point.x, point.y) for point in points]
    colors = {point.index: POINT_COLORS_BGR.get(point.classification, (200, 200, 200)) for point in points}
    drawn_bgr = draw_grid(cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR), positions, colors,
                          radius=radius, numbered=numbered)
    return cv2.cvtColor(drawn_bgr, cv2.COLOR_BGR2RGB)


def heatmap_overlay(image_rgb: np.ndarray, mask: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    """Tint locally ambiguous mask regions (15x15 occupancy between 0.2 and 0.8).

    Visual aid only: nothing downstream reads this image.
    """
    local = cv2.blur((mask > 0).astype(np.float32), (15, 15))
    ambiguous = ((local >= config.MATRIX_RATIO_THRESHOLD) &
                 (local <= config.FERRITE_RATIO_THRESHOLD)).astype(np.uint8)
    overlay = image_rgb.copy()
    overlay[ambiguous > 0] = (255, 140, 0)
    return cv2.addWeighted(overlay, alpha, image_rgb, 1.0 - alpha, 0)


def mask_blend_overlay(image_rgb: np.ndarray, mask: np.ndarray, alpha: float = 0.40) -> np.ndarray:
    """Tint the detected phase green over the original, for report evidence."""
    tint = np.zeros_like(image_rgb)
    tint[:, :] = hex_to_rgb(config.CATEGORY_COLORS["ferrite"])
    overlay = np.where(mask[:, :, None] > 0, tint, image_rgb)
    return cv2.addWeighted(overlay.astype(np.uint8), alpha, image_rgb, 1.0 - alpha, 0)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert ``#rrggbb`` to an RGB tuple."""
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
