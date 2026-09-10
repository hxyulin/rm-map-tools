# Bound-mesh simplification and startup

2026-09-11, Apple M3 Pro, same optimized-development simulator executable for
both packages. The previous default is retained locally at
`out/semantic-detail-source`; the new default is `../rm-simulator/local-assets/field`.

| Metric | Previous default | Simplified default | Reduction |
|---|---:|---:|---:|
| Placed visual triangles | 7,527,046 | 3,018,741 | 59.9% |
| Static collider triangles, loader count | 5,968,039 | 2,169,201 | 63.7% |
| Referenced visual + collision GLBs, bytes | 587,168,572 | 259,669,320 | 55.8% |
| Base visual triangles per instance | 894,899 | 316,623 | 64.6% |
| Median scene-ready seconds | 15.497 | 5.734 | 63.0% |
| Median terrain parsing seconds | 5.413 | 2.130 | 60.6% |
| Median package verification seconds | 2.359 | 1.080 | 54.2% |

Three alternating before/after runs used the same camera, paused scene and
binary. OS caches were not cleared. Scene-ready is the last CAD instance-ready
log relative to the first app log, not the first presented frame. The app
continued to a screenshot and exited normally in each run. Raw timing records
are in `startup.json`; logs and screenshots are in `out/simplified-startup`.
These samples show a local startup improvement, not a cold-start guarantee or
an FPS/physics-tick measurement.

## What changed

The meshoptimizer pass collapses edges within existing material and semantic
primitive boundaries. It welds identical positions, locks open borders, restores
any disconnected component that would disappear, and removes orphan mesh/accessor
data. It preserves node indices, transforms, joint frames and surface indices.
Text remains geometry. There is no distance-based LOD, culling, convex hull,
voxel replacement or automatic small-part deletion.

The pipeline requests 0.5 mm visual and 1 mm collider simplifier metrics. That
metric alone was insufficient: the first test had sampled outliers above 10 mm.
The final pipeline checks bidirectional point-to-triangle samples per changed
primitive, retries difficult primitives at tighter settings, then retains their
original geometry if needed. Final sample limits are 2 mm visual and 3 mm
collision. `deviation.json` records a separate traversal of the resulting files.
The checks are sampled rather than a Hausdorff proof; original STEP tessellation
error is additional. Degenerate triangles do not contribute distance samples.

The existing semantic classification protects optical roles and markings/lights
layers. Unclassified surfaces still receive ordinary simplification and deviation
checks. Base and field overview images were inspected, as was an active default
simulator scene with rune and outpost motion. No semantic selectors were reapplied
to changed triangle indices; the pass updates hashes around unchanged bindings.

Terrain, centre platform and outpost footings keep their previous geometry.
The new collision contract is `meshopt-simplification-v1`; the simulator requires
valid producer metadata and file checksums rather than treating the output as
unchanged source tessellation.

## Why linear tolerance was not enough

The largest resource-zone part at 0.9 rad gave these counts:

| Linear tolerance | Triangles |
|---|---:|
| 4 mm | 474,598 |
| 8 mm | 440,221 |
| 16 mm | 424,991 |
| 32 mm | 417,924 |
| 16 mm with 1.5 rad angle | 385,712 |

The improvement flattened out because source trim boundaries and small detail
still constrained the tessellation. The final deployment uses the mesh pass,
without increasing these STEP tolerances further. See `linear-sweep.json`.

## Reproduce

```sh
uv pip install --python ocpenv/bin/python -r python/requirements-simplification.txt
ocpenv/bin/python python/simplify_package.py rules/simplify-simulation.example.json
ocpenv/bin/python benchmarks/2026-09-11-mesh-simplification/benchmark_startup.py \
  ../rm-simulator out/semantic-detail-source out/simplified-semantic-field \
  out/simplified-startup-new
```

Outputs must be new. The example source snapshot remains unsimplified so another
run cannot accumulate simplification error. `counts.json`, `startup.json`,
`deviation.json`, `linear-sweep.json` and `export.log` record this run. Full
primitive reports remain in the ignored CAD package's `mesh-simplification.json`.
