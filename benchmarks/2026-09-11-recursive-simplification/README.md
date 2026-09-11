# Repeated simplification trials, 2026-09-11

Trials compare three more 4 mm passes against restarting from source at 6 mm or
8 mm. The base and resource-zone visuals are tested; collision meshes, textures,
semantic frames and standalone energy-unit assets stay unchanged. These outputs
are review GLBs, not an installed package or a new exporter default.

Each repeated pass must preserve connected mesh components. The guarded variant
also checks each node/material group against the original unsimplified source,
accepting a smaller result only if it meets the source deviation limit. A rejected
group retains its previous geometry. Shared meshes require all instances to pass.
The limit is measured using 4,096 sampled triangles per direction for each group,
with vertex, centroid and edge-midpoint samples. It is not a certified geometric
bound. All candidates reference source geometry with text and units already
removed appropriately.

| Variant | Resource triangles | Resource max source deviation | Base triangles | Base max source deviation |
|---|---:|---:|---:|---:|
| Current | 112,591 | 11.93 mm | 60,434 | 11.80 mm |
| Three unguarded repeats | 86,272 | 21.21 mm | 52,397 | 20.31 mm |
| Three repeats, 12 mm source guard | 106,232 | 11.93 mm | 53,300 | 11.96 mm |
| Three repeats, 18 mm source guard | 86,282 | 17.47 mm | 52,413 | 16.94 mm |
| Direct 6 mm, 18 mm sampled limit | 102,308 | 17.41 mm | 56,978 | 13.83 mm |
| Direct 8 mm, 24 mm sampled limit | 94,195 | 23.96 mm | 53,059 | 19.83 mm |

Repeated local error checks alone allow cumulative drift. The source guard catches
this. In this dataset, guarded repeats also outperform merely increasing the
single-pass error setting.

## Recommended review candidate

Use the 18 mm guarded resource zone and the 12 mm guarded base. The resource
zone loses another 23.37% of its visual triangles. The base loses another 11.80%.
Across two instances of each, the field loses 66,886 visual triangles, going from
781,913 to 715,027, an 8.55% reduction. A 12 mm guard for both assets instead saves
26,986 triangles, or 3.45%, without raising the sampled source limit.

The 18 mm base opens a visible seam near its upper shield. It saves only 887 more
triangles than the 12 mm base, so the 12 mm version is preferable. The 18 mm
resource-zone exterior shows little change in the fixed comparison view. These
views do not establish invisibility of every changed surface.

All 2,888 resource-zone and 2,110 base connected components survive in both guarded
variants. No new vertex positions or cross-component triangles are introduced.
All four guarded GLBs pass glTF validation with zero errors and warnings.
`components.json` and `results.json` record the checks, source hashes, timings,
per-pass counts and source deviations.

## Reproduction and artifacts

Run from the repository root with the source files and baseline installed package
available. `compare.py` requires a new output directory for each asset.

```sh
ocpenv/bin/python benchmarks/2026-09-11-recursive-simplification/compare.py resource-zone
ocpenv/bin/python benchmarks/2026-09-11-recursive-simplification/compare.py base
ocpenv/bin/python benchmarks/2026-09-11-recursive-simplification/guarded.py resource-zone 12
ocpenv/bin/python benchmarks/2026-09-11-recursive-simplification/guarded.py base 12
ocpenv/bin/python benchmarks/2026-09-11-recursive-simplification/guarded.py resource-zone 18
ocpenv/bin/python benchmarks/2026-09-11-recursive-simplification/guarded.py base 18
```

Local outputs remain outside Git:

- `out/recursive-simplification/resource-zone/guarded-18mm-3.glb`
- `out/recursive-simplification/base/guarded-3.glb`
- `out/recursive-simplification/resource-zone/comparison.png`
- `out/recursive-simplification/base/comparison.png`

To integrate this into the exporter later, preserve a source reference throughout
all passes and report the source limit separately from the per-pass limit. The
experimental composer removes ordinary single-pass metadata from its GLBs because
those measurements no longer describe the composed result. Do not repin these
files into an installed package while retaining its old simplification metadata.
