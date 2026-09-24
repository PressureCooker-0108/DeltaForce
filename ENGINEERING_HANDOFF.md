# ASTM E562 Delta Ferrite Measurement Application — Engineering Handoff

**Repository:** `Aayodhyam 2.0`  
**Observed version:** `v0.3 Competition MVP` (from `config.py`)  
**Runtime currently intended for use:** Python + Streamlit (`app.py`)  
**Observed state:** a working single-field, 100-point Streamlit MVP exists. Phase 3 utilities exist as isolated Python modules but are not wired into the Streamlit UI. An older Electron/JavaScript Phase 1 prototype is also retained in the repository. This document distinguishes active code from retained code; do not assume both applications run as a single system.

---

## 1. Mission, measurement model, and scope

The application helps a metallography operator estimate the delta-ferrite volume fraction in stainless-steel micrographs. It does so by enhancing an uploaded image, producing a candidate binary ferrite mask, placing a systematic grid, classifying grid points, permitting operator corrections, and calculating a single-field point fraction.

The scientific basis is stereology. Under the Delesse principle, for a representative planar section sampled without bias, area fraction estimates volume fraction. ASTM E562 operationalizes that idea through systematic point counting: record what phase lies under each test point, then estimate phase fraction from the proportion of hits. In this implementation, a ferrite hit counts as `1`, a matrix hit counts as `0`, and an ambiguous boundary hit counts as `0.5`.

For one field with `N` points, `F` ferrite points, and `B` boundary points, the implemented estimator is:

```text
Pp (%) = 100 × (F + 0.5B) / N
```

This is an operator-assistance tool, not an autonomous metallurgical certification system. The segmentation mask is a visual classifier aid; the manual point override is essential because etching, illumination, polishing, alloy variation, and imaging conditions can make contrast ambiguous.

### 1.1 Why ASTM E562

ASTM E562 is appropriate because the product requirement is a phase-fraction measurement, not merely object detection. A systematic grid turns the image into discrete, auditable observations. It is faster to review than tracing every island, tolerates irregular particle geometry, and can report a repeatable per-field result. The 100-point default makes the percentage easy to interpret (each full point is one percentage point before boundary weighting) while giving lower sampling granularity than 16, 25, or 49 point grids.

### 1.2 Why classical computer vision, not deep learning

The product uses deterministic OpenCV operations: LAB conversion, CLAHE, bilateral filtering, adaptive thresholding/Otsu fallback, morphology, and connected components. This choice is appropriate for a competition MVP because it has no dataset-training dependency, runs locally, exposes physically understandable controls, and yields a mask an operator can inspect. A deep model would require carefully annotated, representative micrographs across preparation conditions, scanner/camera settings, alloys, magnifications, and etches; without that calibration it can confidently generalize poorly. Classical CV is not inherently more accurate—it is more transparent and tractable at the current maturity.

### 1.3 Non-negotiable preservation rule

Sample-identification marks, borders, and all source pixels must remain visible. Neither active implementation crops nor resizes the image array during processing. UI rendering may scale a display to fit the browser, but that is not a destructive image transformation. Future work must not crop to remove labels, remove borders, or use a resized image for measurement while presenting it as original-resolution analysis.

---

## 2. Truthful maturity assessment

| Capability | Status | Evidence / caveat |
|---|---|---|
| Upload PNG/JPEG/TIFF/BMP | Active Streamlit UI | `st.file_uploader`; OpenCV decoder is used. TIFF support depends on OpenCV build. |
| Original/enhanced/mask/grid visual review | Active | Four panels in `app.py`. |
| LAB/CLAHE/bilateral segmentation preparation | Active | Implemented inline in `process_image`. |
| Adaptive threshold, Otsu fallback, morphology, area filter | Active | Implemented inline in `process_image`. |
| One 10×10 rotatable grid | Active | `app.py.generate_grid`. |
| 5×5 auto classification and click-cycle override | Active | `app.py.classify_points`, Plotly selection, session state. |
| Per-field point fraction | Active after **Analyze** | Dashboard metric in `app.py`. |
| Multiple grid sizes / translation | Library only | `astm/grid.py`; active Streamlit UI exposes only 100 points and no translation. |
| Multiple independent fields / CI / relative accuracy | Library only | `astm/statistics.py`; no collection workflow in `app.py`. |
| PDF report | Library only | `reporting.py`; no UI action invokes it. |
| Enhanced image export in Streamlit | Missing | Electron prototype has export; current Streamlit app does not. |
| Automated tests | Missing | No test files were present at inspection. |
| Standards validation against expert counts | Missing | Sample images exist but no labels, protocol, or recorded acceptance results. |

Do not describe this repository as competition-ready. Before that claim, it needs representative-field capture, standards-reviewed statistical workflow, image/export provenance, test coverage, calibrated defaults, and validation against manual ASTM counts.

---

## 3. Repository map and ownership

```text
app.py                         Active Streamlit MVP entry point
requirements.txt               Python runtime dependencies
config.py                      Central constants, currently mostly unused

astm/                          Reusable Phase 2/3 domain primitives; not imported by app.py
  grid.py                      Grid geometry and OpenCV overlay renderer
  boundary.py                  5×5 occupancy and half-point decision logic
  point_classifier.py          Point-class data model and batch classification
  counter.py                   Single-field counting data model and arithmetic
  statistics.py                Multi-field mean, SD, 95% CI, relative accuracy

segmentation/                  Reusable segmentation primitives; not imported by app.py
  threshold.py                 LAB L extraction, adaptive/Otsu thresholding
  morphology.py                Elliptical-kernel morphology operations
  components.py                Small-component removal

ui/                            Reusable review helpers; not imported by app.py
  overlay.py                   OpenCV grid overlay / ambiguity heatmap
  manual_edit.py               Classification cycling

reporting.py                   PDF generator consuming astm.counter/statistics models

main.js, preload.js, renderer.js, index.html, styles.css
                               Retained Electron + OpenCV.js Phase 1 application
package.json, package-lock.json JavaScript dependency manifest and lockfile
node_modules/                  Installed JavaScript dependencies; generated, not source

Total photos/                  Eight unlabelled example micrographs, not a structured dataset
App                           Empty directory at inspection
README.md                      Outdated project description; do not treat as executable truth
__pycache__/                   Generated Python bytecode; not source
```

### 3.1 Active dependency graph

```text
browser
  ↓ HTTP/WebSocket reruns
Streamlit app.py
  ├─ streamlit: upload, controls, state, panels, metrics
  ├─ OpenCV: decode → color conversion → filtering → segmentation
  ├─ NumPy: byte buffer, channel/matrix operations, grid coordinates
  └─ Plotly: selectable ASTM overlay

uploaded bytes
  ↓ process_image
original RGB + enhanced RGB + uint8 binary mask + method label
  ↓ generate_grid / classify_points
100 point records
  ↓ overlay_figure / metrics
clickable display + one-field result cards
```

### 3.2 Intended modular dependency graph (not yet wired)

```text
future UI controller
  ↓
segmentation.threshold → segmentation.morphology → segmentation.components
  ↓                                               ↓
astm.grid → astm.point_classifier → astm.counter → astm.statistics
                                      ↓
                                ui.overlay / ui.manual_edit
                                      ↓
                                 reporting.create_pdf_report
```

This is a sound direction for Phase 3: refactor `app.py` to call the modules rather than duplicating their logic, but do it with regression tests first. The inline app and module versions differ in names, casing, grid options, and image-color assumptions.

---

## 4. Active application: `app.py`

### 4.1 Purpose and startup

`app.py` is the runnable product. Start it from the repository root with:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Use `py -m streamlit`, not bare `streamlit`, on this Windows host: the Python Scripts directory may not be on `PATH`.

At module import, `st.set_page_config` sets page title, icon, and wide layout. Streamlit re-executes top-level code after interactions, so persistent user state lives in `st.session_state` and costly image processing is cached.

### 4.2 `process_image(data, clip_limit, adaptive_c, minimum_area)`

**Purpose:** executes the active fixed image-to-mask pipeline.  
**Parameters:** raw file bytes; floating CLAHE clip limit; adaptive threshold constant `C`; area in pixels.  
**Returns:** `(original_rgb, enhanced_rgb, refined_mask, threshold_method)`. The first two arrays are H×W×3 `uint8`; mask is H×W `uint8` with `0` matrix and `255` candidate ferrite.  
**Side effects:** cache entry only. No filesystem writes and no mutation of uploaded bytes.  
**Errors/edges:** malformed files cause `ValueError`; OpenCV force-decodes colour using `IMREAD_COLOR`, so alpha and source EXIF are not retained by the active app. Very small images can make adaptive thresholding fail because its fixed 35-pixel block must fit OpenCV's requirements.

Implementation trace:

```text
bytes
 ↓ np.frombuffer(..., uint8)             zero-copy view where possible
 ↓ cv2.imdecode(..., IMREAD_COLOR)       BGR pixel matrix
 ↓ cv2.cvtColor(BGR→RGB)                 browser-friendly original image
 ↓ cv2.cvtColor(RGB→LAB), cv2.split       L, a, b planes
 ↓ CLAHE.apply(L) + cv2.merge             contrast-enhanced LAB
 ↓ cv2.cvtColor(LAB→RGB)                  enhanced colour image
 ↓ cv2.bilateralFilter                    edge-preserving denoise
 ↓ cv2.cvtColor(RGB→LAB)[:, :, 0]         processed L plane
 ↓ adaptive threshold OR Otsu fallback    provisional binary mask
 ↓ opening, closing                       cleaned mask
 ↓ connected components + area rule       refined binary ferrite mask
```

`cv2.imdecode` parses encoded bytes in memory, avoiding an intermediate uploaded file. `IMREAD_COLOR` normalizes image to a three-channel BGR output. `cv2.cvtColor` transforms each pixel from BGR to RGB because Streamlit/Plotly expect RGB ordering; the array's dimensions are unchanged.

LAB separates luminance from chromatic axes. `L` encodes perceived lightness; `a` approximately spans green↔red; `b` approximately spans blue↔yellow. Equalizing only L improves local illumination contrast without independently distorting the two chromatic channels. RGB channels intertwine brightness and colour, so equalizing RGB separately can introduce false colours and unstable phase contrast.

`cv2.createCLAHE(clipLimit, tileGridSize=(8,8))` partitions L into tiles, builds a limited histogram equalization mapping per tile, then interpolates between tile mappings. Global histogram equalization would remap every pixel using one image-wide histogram, often over-amplifying polished/etched regions and making illumination gradients worse. CLAHE clips an over-full histogram bin and redistributes the excess, limiting noise amplification. The active UI varies only the clip limit; tile size is fixed at 8×8.

`cv2.bilateralFilter(enhanced, 5, 50, 50)` replaces each pixel using nearby pixels that are both spatially close and similar in intensity. Its weight is conceptually:

```text
w(p,q) = exp(-||p-q||² / 2σspace²) × exp(-||I(p)-I(q)||² / 2σcolor²)
```

The spatial term limits distance; the intensity term prevents smoothing across a strong grain/phase edge. A Gaussian blur uses only spatial distance and blurs grain boundaries, which are exactly the features the subsequent mask and human reviewer need to retain.

`cv2.adaptiveThreshold` compares each pixel with a Gaussian-weighted local mean over a 35×35 neighborhood:

```text
mask(x,y) = 255 when L(x,y) > localGaussianMean(x,y) − C, otherwise 0
```

The UI's **Adaptive Threshold** slider is this `C`, not a direct global brightness cutoff. Larger C generally makes the `>` condition easier to meet and can increase white-mask coverage. The code measures coverage; under 0.5% or over 85% is treated as implausibly empty/full, so `cv2.threshold(... THRESH_OTSU)` is used instead. Otsu evaluates candidate global thresholds from the image histogram and selects the one minimizing weighted within-class variance (equivalently maximizing between-class variance). It is a fallback when local adaptive results degenerate, not a guarantee of correct metallurgical phase polarity.

Morphological opening is erosion then dilation: it removes small bright specks that cannot contain the kernel. Closing is dilation then erosion: it fills small black holes and bridges very small gaps in bright regions. Both use an elliptical 3×3 structuring element. The ellipse gives less axis-biased cleanup than a square. These are binary-set operations, so excessive kernel size can destroy thin ferrite features or merge adjacent islands.

`cv2.connectedComponentsWithStats(mask, connectivity=8)` labels each connected white region, treating diagonal adjacency as connected. `stats[label, CC_STAT_AREA]` is its pixel area. The loop deliberately skips label 0 (background) and copies only components whose area meets the slider's threshold. This removes dust/salt noise but can erase genuine small ferrite islands; the threshold needs specimen-specific calibration.

### 4.3 `generate_grid(width, height, rotation)`

**Purpose:** create exactly 100 grid coordinates as a 10×10 lattice.  
**Parameters:** image dimensions in pixels and rotation in degrees.  
**Returns:** 100 `(x, y)` rounded integer tuples.  
**Side effects:** none.  
**Edges:** assumes sensible image dimensions. For images whose smaller half dimension is ≤8 pixels, calculated span becomes non-positive. The current uploader will normally receive much larger micrographs.

The function reserves 8 pixels of margin. It uses a rotation matrix

```text
[cos θ  -sin θ]
[sin θ   cos θ]
```

and computes a lattice span reduced by `|cos θ| + |sin θ|`. That reduction bounds the rotated square inside the limiting image dimension, so no grid point is dropped, cropped, or moved outside the image. `np.linspace` makes equal coordinates in each dimension. The grid is centred at `(width/2,height/2)` and then rotated. The current **Generate Grid** button resets overrides but changing rotation itself immediately recomputes grid coordinates; it does not persist a grid separately.

### 4.4 `classify_points(mask, grid, overrides)`

**Purpose:** make a categorical decision for every grid coordinate.  
**Inputs:** binary mask, coordinates, and point-index→manual-category override map.  
**Returns:** one dict per point with index, position, category, and numeric score.  
**Edges:** slices are clipped to image boundaries. Grid generation normally prevents edge points, so a full 5×5 area is expected.

For each point, a 5×5 window is extracted (`y-2:y+3`, `x-2:x+3`). Its ferrite occupancy is nonzero pixel count divided by window area. The decision tree is:

```text
ratio > 0.80        → Ferrite, 1.0, green
0.20 ≤ ratio ≤ 0.80 → Boundary, 0.5, yellow
ratio < 0.20        → Matrix,  0.0, red
manual override     → replaces automatic category and score
```

Five pixels is a practical compromise: it makes a point robust to a one-pixel mask artifact while remaining local enough not to smear a true boundary over a large part of a grain. It is a heuristic approximation of boundary review, not a verbatim substitute for every ASTM boundary convention. A thick or incorrectly segmented boundary can be falsely marked mixed; a too-aggressive morphology operation can make it falsely uniform. The operator must review uncertain points.

### 4.5 `overlay_figure`, `metrics`, `cycle_override`, `initialize_state`

`overlay_figure(image, points)` builds a Plotly `go.Image` plus a `go.Scatter` trace. It does not modify the original NumPy array. Marker colour is driven by category and `customdata` stores the stable point index/category/score for selection callbacks. Hidden axes use the image pixel coordinate range, with y reversed so `(0,0)` is top-left. This is why clicking visual markers maps back to image coordinates without scaling error.

`metrics(points)` counts categories and returns six dashboard values. It uses the half-point formula above and protects the empty-grid case from division by zero. The returned dictionary's insertion order determines visual card order.

`cycle_override(current)` implements `Ferrite → Boundary → Matrix → Ferrite`; it throws `KeyError` for an unknown category, which is intentional fail-fast behavior for a corrupted state.

`initialize_state()` establishes `file_id`, `overrides`, `grid_ready`, `analyzed`, and `last_selection`. `file_id` is a SHA-256 digest of upload bytes; a different image clears corrections and analysis state so classifications cannot leak between specimens. `last_selection` avoids a Streamlit rerun processing the same selection repeatedly. A user may need to deselect/reselect a point before cycling the exact same marker again because Plotly selection events are persistent.

### 4.6 UI flow

The sidebar exposes image upload, CLAHE clip limit, adaptive C, minimum area, grid rotation, **Generate Grid**, and **Analyze**. Processing runs immediately after upload or parameter changes (cache permitting). Main panels are always original, enhanced, binary mask, and selectable overlay. **Analyze** gates dashboard publication; it does not change the underlying pipeline. Once analyzed, clicking an overlay marker alters its override and triggers rerun, so displayed counts update immediately.

The active UI does not expose bilateral parameters, CLAHE tile size, grid size, translation, threshold method mode, morphology size, image metadata, an enhanced export button, a field list, report export, or test/calibration controls. Those omissions must be acknowledged in any demonstration.

---

## 5. Reusable Python modules (implemented but not active-wired)

### 5.1 `config.py`

Defines `APP_VERSION`, `DEFAULT_CONFIDENCE_LEVEL=0.95`, and `DEFAULT_GRID_SIZE=100`. It has no imports and no current callers. It exists as a central configuration intent; migrate UI literals to it only together with a documented configuration schema and tests.

### 5.2 `segmentation/threshold.py`

`lab_lightness(image)` expects BGR or BGRA (unlike active `app.py`, which uses RGB). It converts input to RGB then LAB and returns L. Passing an RGB array here would silently produce an incorrect conversion. `adaptive_threshold(lightness, block_size, c_value)` forces block size to odd and at least 3 then invokes Gaussian adaptive threshold. `otsu_threshold(lightness)` invokes global Otsu. `threshold_ferrite(image, block_size, c_value, mode)` selects forced Otsu, forced adaptive, or the same 0.5%/85% coverage fallback. Inputs must be nonempty 3/4-channel arrays and valid adaptive block dimensions.

### 5.3 `segmentation/morphology.py`

`kernel(size)` creates an elliptical structuring element. `opening`, `closing`, `erode`, and `dilate` wrap the respective OpenCV morphology calls. They return new mask arrays and do not mutate inputs. Caller must ensure positive sensible size; OpenCV may reject invalid values. In the active app, only opening and closing with size 3 are duplicated inline.

### 5.4 `segmentation/components.py`

`remove_small_components(mask, minimum_area)` runs 8-connected component labelling and emits a fresh binary mask retaining labels with area at least the threshold. This is equivalent to the final inline loop in `app.py`. It assumes white pixels are candidate ferrite; reverse polarity before calling if ferrite is black.

### 5.5 `astm/grid.py`

`GridPoint` is an immutable dataclass containing zero-based `index`, `x`, and `y` pixel coordinates. `_grid_shape(count)` creates a square when possible; otherwise it chooses `floor(sqrt(count))` rows and enough columns to fit count. `generate_grid(...)` supports counts such as 16 (4×4), 25 (5×5), 49 (7×7), and 100 (10×10), rotation, bounded translation, and margin. It returns empty for invalid count/dimensions and clamps requested offsets so every point stays within bounds. `rotate_grid(...)` rotates an existing collection about centre but drops outside points, so prefer `generate_grid` when a fixed count is mandatory. `translate_grid(...)` applies a shared clamped shift. `draw_grid(...)` copies BGR/BGRA input and renders coloured circles plus point numbers with anti-aliasing; its colour tuples are OpenCV BGR order.

### 5.6 `astm/boundary.py` and `astm/point_classifier.py`

`ferrite_ratio(mask,x,y,neighborhood=5)` returns white-pixel occupancy in an edge-clipped window. `classify_ratio(ratio)` maps it to lowercase `ferrite/boundary/matrix` and scores `1/.5/0` using the same 0.80/0.20 thresholds. `ClassifiedPoint` stores point geometry, class, score, and an `automatic` flag. `classify_point` composes local ratio with its decision; `classify_points` maps it across a grid. All callers must use lowercase strings with these modules, whereas the active app uses title case. Do not mix representations without an adapter.

### 5.7 `astm/counter.py` and `astm/statistics.py`

`FieldCount` holds full count totals plus per-field percentage. `count_field(points)` materializes the iterable, counts lowercase classifications, and applies half weighting.

`StatisticsResult` holds number of fields, mean percentage, sample standard deviation, half-width of a two-sided 95% CI, and relative accuracy. `summarize_fields(fields)` returns zeroes for no data, avoids pretending a single field has measurable variation, and otherwise uses `statistics.stdev` and `t × s / sqrt(n)`. `_T95` supplies Student-t critical values for degrees of freedom 1–30; 1.96 is used above that. This assumes independent representative fields. It does not test normality, magnification consistency, operator bias, or ASTM acceptance limits.

### 5.8 `ui/overlay.py` and `ui/manual_edit.py`

`grid_overlay(image, points)` maps lowercase classifications to BGR colours and delegates drawing to `astm.grid.draw_grid`; image data is copied before drawing. `confidence_heatmap(image, mask, enabled, alpha=.35)` computes a 15×15 blurred local mask occupancy, marks 0.2–0.8 as ambiguous, tints it orange, and alpha blends. It is visual-only and must never alter measurement input. `cycle_classification(point)` returns a new `ClassifiedPoint` with the next lowercase category and `automatic=False`; it does not mutate the original.

### 5.9 `reporting.py`

`create_pdf_report(output_path,image_name,image_size,grid_size,fields,summary)` imports ReportLab lazily, writes an A4 report with metadata, statistics, and per-field counts, then returns `Path(output_path)`. It does not create parent directories, embed source/mask/overlay images, preserve EXIF, include parameters, check that data is valid, or invoke UI download mechanics. It expects `FieldCount` and `StatisticsResult`; until a field collection exists in the app, it cannot produce a complete report.

---

## 6. Retained Electron prototype

`package.json` defines `npm start` (`electron .`) and a JavaScript syntax-only test script. It lists Electron, OpenCV.js, EXIF parser `exifr`, and TIFF decoder `utif`. `main.js` creates the desktop shell and supplies IPC handlers to open permitted image formats and save a requested PNG. `preload.js` safely exposes only those handlers through `contextBridge` while retaining context isolation.

`index.html` supplies the Phase 1 page, controls, canvases, OpenCV.js/UTIF/exifr scripts. `renderer.js` decodes input (including first-frame TIFF), renders metadata, runs the exact Phase 1 pipeline (RGBA→RGB→LAB→CLAHE on L→LAB merge→bilateral→restore alpha), and exports enhanced canvas as PNG. `styles.css` is its dark visual design. It is not called by Streamlit and does not perform Phase 2 counting. `README.md` combines claims from both lineages and says `py app.py`; that command executes Python but does not launch Streamlit's server reliably. Use the command in section 4.1.

Keep this prototype only if it is intentional reference/backup. Maintaining two UIs with duplicated algorithms raises drift risk. Do not delete it without owner approval.

---

## 7. Parameters, defaults, and rationale

| Parameter | Active default | Implemented range / alternate | Why it exists | Risk when increased |
|---|---:|---|---|---|
| CLAHE clip limit | 2.0 | UI 0.5–8.0 | Limits local contrast amplification | Noise/etch texture can become false ferrite |
| CLAHE tile size | 8×8 | Electron UI 2–32; Python active fixed | Local illumination adaptation | Too-small tiles amplify texture; too-large behaves more globally |
| Bilateral diameter | 5 | Electron UI 1–15 odd | Local smoothing footprint | Slower and may erase small phase detail |
| Sigma colour/space | 50/50 | Electron UI 1–150 | Edge-preserving denoise strength | Over-smoothing or loss of phase boundaries |
| Adaptive block | 35 | reusable module supports input | Local illumination neighborhood | Too small follows noise; too large ignores illumination drift |
| Adaptive C | 5 | UI −20–20 | Local threshold bias | Changes white-mask coverage / phase polarity sensitivity |
| Otsu fallback bounds | .005/.85 | fixed | Detect degenerate adaptive coverage | Not a metallurgical correctness test |
| Morphology kernel | ellipse 3×3 | reusable functions parameterize size | Remove specks / fill tiny holes | Removes or joins real islands |
| Minimum component area | 20 px | UI 1–2000 | Reject tiny connected noise | Eliminates true fine ferrite |
| Grid | 100 | module supports 16/25/49/100 | Fine systematic sampling, intuitive percent scale | More review effort |
| Grid margin | 8 px active; 4 px module | fixed/default | Keep points visibly in image | Excess margin reduces sampled span |
| Neighborhood | 5×5 | module parameter | Noise-robust local point decision | Broad boundary may be labelled mixed |
| Boundary thresholds | 20%, 80% | fixed | Detect mixed occupancy | Heuristic, needs calibration |
| Boundary score | 0.5 | fixed | Half-point approximation | Must remain visible/auditable |

Grid choices: 16 makes each full hit 6.25%, 25 makes it 4%, 49 approximately 2.04%, and 100 makes it 1%. 100 is the active default because it reduces quantization error and offers readable, audit-friendly point-level review. It is not automatically the statistically sufficient number of fields; field-to-field variation must be measured in Phase 3.

---

## 8. Known failure modes and mitigation

| Failure mode | Mechanism | Current mitigation | Required next step |
|---|---|---|---|
| Touching ferrite islands | Closing or thresholding merges nearby bright areas | Small 3×3 kernel, manual points | Validate morphology per sample; optional watershed only after validation |
| Noisy etching / polishing scratches | CLAHE and adaptive threshold can highlight texture | Clip/area controls, bilateral filtering | Add calibration presets and inspect mask |
| Illumination gradient | Global threshold fails over field | LAB CLAHE + adaptive threshold | Record acquisition conditions; expose block size if justified |
| Wrong polarity | Ferrite may be darker rather than lighter | No active inversion selector | Add explicit validated polarity option, never silently infer |
| Periodic structures | Grid can alias with regular microstructure | Rotation control | Add controlled translation/replicate fields |
| Too-small features | Component filter removes them | Minimum-area slider | Compare against manual labels, enforce documented minimum |
| Boundary ambiguity | Pixel mask differs from metallurgical boundary | 5×5 mixed class, manual override | Record reviewer audit trail and define boundary convention |
| EXIF/provenance loss | Streamlit decodes to pixels, no metadata model | None in active app | Capture original filename/hash/dimensions/parameters in result/report |
| Multi-page TIFF | Active decoder may choose a frame depending on OpenCV | None | Define/implement page selection |
| Repeated same click | Persistent Plotly selection has rerun guard | User may deselect/reselect | Improve event/state handling with a tested control |

---

## 9. Performance and resource model

For an H×W image with P=H×W pixels, decode, colour conversions, CLAHE, morphology, thresholding, connected components, and display preparation are O(P). Bilateral filtering is approximately O(P·d²) for diameter d; it is usually the heaviest vision step. Grid and classification are O(100·25), effectively constant at this grid size. Memory is O(P) but several H×W or H×W×3 intermediate arrays coexist; a 2048×1536 RGB array alone is about 9 MiB, and several arrays can drive working memory into tens of MiB.

Optimize only after profiling representative images. Preserve full-resolution analysis. Safe directions are cache keys that include all parameters, releasing unneeded intermediates, and avoiding duplicate copies; unsafe directions are silent downsampling or cropping.

---

## 10. Dataset, calibration, validation, and tests

There is no `samples/` hierarchy, ground truth, or automated test suite currently. `Total photos/` contains eight JPG/JPEG-named images but no labels or difficulty classification. Create—not merely document—the following data structure before asserting accuracy:

```text
samples/
  easy/          high contrast, isolated ferrite
  medium/        moderate illumination/etch variability
  hard/          touching islands and difficult boundaries
  noisy/         scratches, dust, uneven etch
  calibration/
    images/
    expert_counts.csv
    masks/       optional reviewed masks
```

Manual ASTM point counts by qualified reviewers should be the reference for a point-counting product. Store image hash, magnification, field identity, grid coordinates/rotation, reviewer class for every point, and parameter settings. Use that record to tune defaults without fitting to only one image.

Minimum test plan:

| Test | Pass criterion |
|---|---|
| Image preservation | Output arrays maintain uploaded W×H; labels/borders are present in rendered original; no crop operation occurs. |
| Enhancement | CLAHE changes L contrast but preserves dimensions and non-L LAB channels before filtering. |
| Segmentation | Synthetic masks and calibrated images confirm polarity, fallback boundary conditions, morphology, and area filtering. |
| Grid | 16/25/49/100 each return requested count; rotation/translation leave all points in bounds and equally spaced before rounding. |
| Classification | All-white, all-black, and known 5×5 occupancy windows map to expected 1/.5/0 classes. |
| Manual correction | Each click/cycle updates correct point only and total score correctly. |
| Statistics | Known field fractions reproduce mean, sample SD, t-interval, and zero/single-field behavior. |
| Report | Generated PDF contains exact provided values and opens successfully. |
| Regression | Manual expert count agreement is pre-defined and measured per difficulty class. |

---

## 11. Phase 3 implementation contract

Phase 3 must build a multi-field, auditable competition workflow—not another segmentation algorithm. Implement these features in order:

1. Refactor the active app to use `segmentation`, `astm`, and `ui` modules, resolving RGB/BGR and title/lowercase conventions with tests.
2. Add **Add Current Field** that snapshots a field immutably: original file hash/name, dimensions, exact segmentation settings, grid geometry, each automatic/manual classification, counts, and Pp(i).
3. Allow remove/review of captured fields without changing prior snapshots when current sliders move.
4. Call `summarize_fields` for mean, sample SD, two-sided 95% CI, and relative accuracy; clearly state that a single field has no estimated CI.
5. Add a traceable report export through `create_pdf_report`, expanded to include methods, parameters, source metadata, field table, reviewer changes, and image evidence.
6. Add dataset calibration and automated tests before changing defaults or claiming ASTM conformance.

Do not quietly: resize/crop images; replace reviewed point states after capture; count image-mask area as ASTM point counting; infer the wrong phase polarity; represent a single-field CI as measured; or call the heuristic 5×5 boundary logic definitive ASTM compliance.

---

## 12. Chronological architectural decisions

1. **Phase 1 Electron prototype:** selected desktop Electron + OpenCV.js to provide instant local image enhancement, TIFF support, metadata, side-by-side view, and lossless PNG export. It retained original dimensions and visible markings.
2. **Classical pipeline:** chose LAB L-channel CLAHE rather than RGB/global equalization to improve local contrast without independent RGB distortion. Bilateral filtering was chosen over Gaussian blur to retain phase/grain edges.
3. **Phase 2 primitives:** added Python modules for threshold/morphology/components, ASTM grid geometry, point classification, counting, manual edit semantics, and statistics/report scaffolding. These isolate responsibilities but were not integrated into a single UI.
4. **Streamlit MVP:** selected Streamlit for rapid competition-facing iteration. It embeds an inline duplication of the needed pipeline and uses Plotly selection to approximate clickable point correction.
5. **100-point default:** selected for finer quantization and intuitive per-point weighting. Lower counts remain supported in `astm/grid.py` for future controlled workflows.
6. **Manual override retained:** automatic segmentation is assistance, not authority. The operator has final control of all point classifications.

---

## 13. Instructions to the next coding AI

Start by reading this document, then `app.py`, then the reusable modules. Treat `app.py` as executable truth and `README.md` as historical intent. Run `py -m py_compile app.py` and `py -m streamlit run app.py` before refactoring. Create tests before extracting duplicated inline functions. Preserve function behavior during the first refactor, especially colour ordering, strings used in maps, 100-point geometry, and the half-boundary formula.

Debugging order when a result looks wrong:

```text
1. Confirm original dimensions and source visibility.
2. Inspect enhanced image: CLAHE/bilateral should improve local contrast without destructive blur.
3. Inspect binary mask: determine polarity, coverage, noise, and component removal.
4. Check grid count, positions, rotation, and in-bounds status.
5. Inspect each automatic point's 5×5 ratio and any override.
6. Recalculate F + 0.5B and compare dashboard/report values.
7. For multi-field work, verify immutable snapshots before statistics.
```

Coding style is compact, typed Python with docstrings and dataclasses for domain records. Keep OpenCV arrays explicit about BGR/RGB/BGRA. Separate pure computational functions from Streamlit state/UI code. Make destructive-looking operations return copies or new arrays. Keep all point classifications auditable. Never add an AI model merely because one is fashionable; any learned approach must be backed by representative annotations, calibration protocol, failure analysis, and a manual-review path.

---

## 14. Immediate handoff checklist

- [ ] Verify `py -m streamlit run app.py` on the target machine.
- [ ] Decide whether Electron files are retained reference or a supported second product.
- [ ] Correct `README.md` to match active runtime and actual Phase 3 integration state.
- [ ] Create an automated test suite covering sections 10 and 11.
- [ ] Establish expert-labelled calibration fields and acceptance criteria.
- [ ] Implement immutable field capture and statistics UI.
- [ ] Add provenance and report evidence before competition submission.
- [ ] Perform a qualified ASTM standards review; this code's interpretation is not a substitute for the standard.

