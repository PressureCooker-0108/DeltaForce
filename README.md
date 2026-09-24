# Aayodhyam 2.0 — ASTM E562 Delta Ferrite Measurement

Offline Streamlit application that estimates the delta-ferrite volume fraction of
stainless-steel metallographic micrographs using **ASTM E562 systematic point counting**.

Images are decoded once at native resolution and are never cropped, resized or
border-trimmed, so sample-identification markings and scale bars survive into every
result and export.

## Run

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Use the Windows Python launcher (`py`) on this machine; bare `python` is not on `PATH`.
Nothing is uploaded anywhere and no network access is required at run time.

## Pipeline

```
upload -> LAB -> CLAHE (L channel) -> bilateral filter
       -> adaptive threshold -> Otsu fallback
       -> opening -> closing -> connected components -> binary ferrite mask
```

Then: systematic grid -> 5×5 neighborhood classification -> `Pp(i)` -> statistics.

### Why the Otsu fallback actually fires

Otsu's separability measure `η` (between-class variance over total variance of the L
histogram) is computed at every run. Measured on the supplied dataset it is **0.83–0.88**
for all six unique fields, i.e. the enhanced L histogram is strongly bimodal and a single
global threshold is the physically valid model. Adaptive thresholding with a small block
size instead follows local texture and produced a near-solid mask covering ~70 % of every
field. In `Auto` mode the pipeline therefore uses the Otsu result whenever `η` exceeds the
gate (default 0.70) or the adaptive coverage is implausible; `Adaptive only` and
`Otsu only` remain available for comparison. The chosen method, `η` and the coverage are
shown in the UI and recorded in the report.

## Point counting

| Class | Local ferrite occupancy | Score | Colour |
|---|---|---|---|
| Ferrite | `> 0.80` | 1 | green |
| Boundary | `0.20 – 0.80` | 0.5 | yellow |
| Matrix | `< 0.20` | 0 | red |

`Pp (%) = 100 × (F + 0.5B) / N`. Every point always receives exactly one class, so no
point can remain unclassified. Grid types are **100 (default), 49, 25 and 16** points,
with equal spacing, rotation and clamped translation; every point is verified to stay
inside the image.

## Features

- **Four synchronised panels** — original, enhanced, ferrite mask, ASTM grid overlay.
- **Live dashboard** — ferrite %, ferrite/boundary/matrix counts, total points, grid type,
  plus the worked `Pp` substitution, `η` and pipeline time.
- **Manual correction** — click a marker in the overlay to cycle its class, or use the
  numbered point editor. Corrections update the dashboard immediately and are recorded as
  reviewer decisions distinct from the automatic result.
- **Multi-field ASTM statistics** — *Add current field* freezes an immutable snapshot
  (sample hash, native resolution, every parameter, grid geometry, all 100 point classes
  and their origin). Mean, sample standard deviation, two-sided 95 % confidence interval
  and relative accuracy are then reported. A single field deliberately reports no CI.
- **Calibration mode** — runs the pipeline over every discovered image and scores it
  against manual reference counts from `samples/calibration/manual_counts.csv`.
- **Developer mode** — shows L-channel, CLAHE, threshold, opening, closing, polarity,
  connected components and the final mask, with component diagnostics.
- **Exports** — PDF report (provenance, parameters, field table, statistics, evidence
  figures), field CSV, per-point CSV, mask PNG and numbered overlay PNG.

## Reproducibility and safety

- Changing the grid type, rotation or offset clears reviewer corrections, because
  index-keyed overrides would otherwise land on different pixels.
- Changing a parameter after *Analyze* marks the result stale instead of silently
  republishing a different measurement. Reviewer edits still update live.
- Reports and exports carry the sample name, its SHA-256, native resolution, grid
  geometry and every parameter that produced the mask.

## Known limitations

- The grid is a square of side `min(width, height) − 2 × margin`, centred on the field.
  On a 3088 × 2076 field it samples the central 2060 px square and not the outer thirds.
  Use the grid offset to move the sampled region; this is a deliberate trade-off because
  the construction guarantees equal spacing and in-bounds points at any rotation.
- Default polarity is `Dark = Ferrite`. For the supplied specimens the dark constituent
  forms discrete compact islands (measured solidity 0.76, aspect 1.55) at ~14–20 % in
  field set 8265, which is a typical delta-ferrite level; reading ferrite as the bright
  phase reports 80–85 %. **Verify polarity against your etch before trusting a number** —
  the toggle is in the sidebar and the choice is recorded in the report.
- Results depend on how many representative fields are sampled. A single field has no
  estimable confidence interval.
- Point counting is a sampling method: expect a few percentage points of variation
  between grid rotations and offsets on the same field. Capture several fields.
- TIFF support depends on the OpenCV build; multi-page TIFF frame selection is not
  exposed. `IMREAD_COLOR` discards alpha and EXIF.

## Repository map

```
app.py                        Streamlit dashboard (entry point)
config.py                     Central defaults, bands and thresholds
segmentation/threshold.py     LAB lightness, adaptive/Otsu selection, polarity
segmentation/morphology.py    Elliptical opening/closing/erode/dilate
segmentation/components.py    Vectorised component filter and diagnostics
segmentation/pipeline.py      Staged pipeline returning every intermediate
astm/grid.py                  16/25/49/100 point grid, rotation, translation
astm/boundary.py              Local occupancy and half-point decision
astm/point_classifier.py      ClassifiedPoint model and batch classification
astm/counter.py               Per-field Pp(i) arithmetic
astm/statistics.py            Mean, sample SD, 95 % CI, relative accuracy
astm/field.py                 Immutable FieldSnapshot for multi-field capture
ui/overlay.py                 Plotly overlay, numbered overlay, display scaling
ui/manual_edit.py             Override semantics and cycling
reporting.py                  PDF report and CSV exports
calibration.py                Calibration sweep against manual counts
samples/                      Calibration/demo dataset scaffold (see samples/README.md)
```

The retained `main.js`, `preload.js`, `renderer.js`, `index.html` and `styles.css` are the
Phase 1 Electron image-preparation prototype. They are not part of the Streamlit
application and share no code with it.
"# DeltaForce" 
