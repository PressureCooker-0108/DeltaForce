# Sample dataset

Calibration and demonstration micrographs for the ASTM E562 delta-ferrite workflow.
Nothing here is required for the application to run; the **Dataset** source in the
sidebar indexes whatever image files it finds under `samples/` and `Total photos/`.

## Layout

```
samples/
  calibration/     fields with a known manual ASTM point count
    manual_counts.csv
  easy/            high contrast, isolated ferrite islands
  medium/          moderate illumination or etch variability
  hard/            touching islands, difficult boundaries
  noisy/           scratches, dust, uneven etch
```

## Reference counts

`samples/calibration/manual_counts.csv` drives the **Calibration mode** panel. The
loader accepts the file names `manual_counts.csv`, `expert_counts.csv` or
`reference_counts.csv` anywhere under the data roots, and matches column names
loosely, so all of these work:

| image | manual_ferrite_percent |
|---|---|
| `8265-27.jpg.jpeg` | `17.5` |

```csv
file,reference
9852 (5).jpg.jpeg,46.0
```

```csv
sample,count
8265-29.jpg.jpeg,16.5
```

Rows whose image name starts with `#` are ignored, so the file can carry inline
comments.

**Important:** the reference column must hold a manual ASTM E562 point count recorded
by a qualified operator, not a value produced by this software. Feeding software
output back in as the reference makes the reported error meaningless. No reference
values are shipped with this repository, so Calibration mode currently lists the
measured images without an error column.

Duplicate images are skipped automatically: byte-identical files would otherwise
appear as repeated measurements and bias the error statistics.
