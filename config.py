"""Central defaults, bands and thresholds for the ASTM E562 delta-ferrite workflow.

Every tunable that the UI, the segmentation stages and the ASTM modules share lives
here so that a single edit changes the whole pipeline. Modules import this file
instead of repeating literals, which previously allowed the inline implementation
in ``app.py`` to drift away from the reusable modules.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
APP_VERSION = "v1.0 Competition Build"
APP_TITLE = "ASTM E562 Delta Ferrite Measurement"
APP_CAPTION = "Systematic point counting on stainless-steel metallographic micrographs"

DEFAULT_CONFIDENCE_LEVEL = 0.95

# --------------------------------------------------------------------------- #
# Enhancement (LAB -> CLAHE -> bilateral)
# --------------------------------------------------------------------------- #
DEFAULT_CLAHE_CLIP_LIMIT = 2.0
CLAHE_CLIP_RANGE = (0.5, 8.0)
DEFAULT_CLAHE_TILE_SIZE = 8
CLAHE_TILE_RANGE = (2, 32)

# Bilateral filter parameters are deliberately fixed: they are a denoise aid, not a
# measurement knob, and exposing them encouraged the operator to "tune" the answer.
BILATERAL_DIAMETER = 5
BILATERAL_SIGMA_COLOR = 50
BILATERAL_SIGMA_SPACE = 50

# --------------------------------------------------------------------------- #
# Segmentation (threshold, polarity, morphology, components)
# --------------------------------------------------------------------------- #
# Internal mode identifiers. Display labels live in THRESHOLD_MODE_LABELS.
THRESHOLD_MODES = ("auto", "adaptive", "otsu")
THRESHOLD_MODE_LABELS = {
    "auto": "Auto (recommended)",
    "adaptive": "Adaptive only",
    "otsu": "Otsu only",
}
DEFAULT_THRESHOLD_MODE = "auto"

DEFAULT_BLOCK_SIZE = 35
BLOCK_SIZE_RANGE = (3, 151)
DEFAULT_ADAPTIVE_C = 5
ADAPTIVE_C_RANGE = (-30, 30)

# Otsu separability gate. ``eta`` is the between-class variance divided by total
# variance of the L histogram at the Otsu threshold (Otsu 1979). Measured on the
# supplied dataset it is 0.83-0.88, i.e. every supplied field is strongly bimodal,
# which means a *global* threshold is the physically valid model and a locally
# varying adaptive threshold would fabricate texture. Above this gate the pipeline
# uses the Otsu result; below it the adaptive result is kept.
OTSU_SEPARABILITY_GATE = 0.70
OTSU_SEPARABILITY_RANGE = (0.30, 0.95)

# The adaptive mask is also rejected when its coverage is implausible. The previous
# band (0.5%-85%) never triggered on any real micrograph, leaving the Otsu fallback
# as dead code, and produced a discontinuity when it finally did fire.
ADAPTIVE_COVERAGE_LOW = 0.02
ADAPTIVE_COVERAGE_HIGH = 0.60

POLARITY_DARK = "dark"
POLARITY_BRIGHT = "bright"
POLARITY_LABELS = {POLARITY_DARK: "Dark = Ferrite", POLARITY_BRIGHT: "Bright = Ferrite"}

# Delta ferrite in austenitic/duplex stainless steel etches darker than the
# austenite matrix for the etches used by the supplied specimens: the dark
# constituent forms discrete, compact islands (measured solidity 0.76, aspect 1.55)
# covering ~14-20% of field 8265-*, which matches a typical delta-ferrite level.
# The alternative reading (bright = ferrite) would report 80-85%, which is not a
# delta-ferrite level for these specimens. The operator can still override.
DEFAULT_POLARITY = POLARITY_DARK

DEFAULT_MORPHOLOGY_KERNEL = 3
MORPHOLOGY_KERNEL_RANGE = (3, 15)

DEFAULT_MINIMUM_AREA = 20
MINIMUM_AREA_RANGE = (1, 2000)

# --------------------------------------------------------------------------- #
# ASTM point classification
# --------------------------------------------------------------------------- #
DEFAULT_NEIGHBORHOOD = 5
NEIGHBORHOOD_RANGE = (3, 15)

# Point-fraction decision thresholds on the local white-pixel occupancy ratio.
FERRITE_RATIO_THRESHOLD = 0.80
MATRIX_RATIO_THRESHOLD = 0.20

FERRITE_SCORE = 1.0
BOUNDARY_SCORE = 0.50
MATRIX_SCORE = 0.0
SCORES = {"ferrite": FERRITE_SCORE, "boundary": BOUNDARY_SCORE, "matrix": MATRIX_SCORE}

CATEGORY_ORDER = ("ferrite", "boundary", "matrix")
CATEGORY_LABELS = {"ferrite": "Ferrite", "boundary": "Boundary", "matrix": "Matrix"}
CATEGORY_COLORS = {"ferrite": "#18a558", "boundary": "#f4c430", "matrix": "#e34b4b"}

# --------------------------------------------------------------------------- #
# ASTM E562 grid
# --------------------------------------------------------------------------- #
DEFAULT_GRID_SIZE = 100
SUPPORTED_GRID_SIZES = (100, 49, 25, 16)
DEFAULT_GRID_ROTATION = 0.0
GRID_ROTATION_RANGE = (-180.0, 180.0)
DEFAULT_GRID_OFFSET = 0
GRID_OFFSET_RANGE = (-600, 600)
GRID_MARGIN = 8

# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #
# Longest edge used when rasterising an image for the browser. Analysis always runs
# at native resolution; this only bounds what is shipped to the page.
DISPLAY_MAX_DIMENSION = 2048

# Report evidence is embedded at a lower resolution and as JPEG: a full-resolution
# PNG bundle produced a 16 MB PDF, which is impractical to submit or email.
REPORT_EVIDENCE_MAX_DIMENSION = 1000
REPORT_EVIDENCE_JPEG_QUALITY = 80

CACHE_TTL_SECONDS = 3600
