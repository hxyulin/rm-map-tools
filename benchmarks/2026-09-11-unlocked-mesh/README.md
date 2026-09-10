# Unlocked mesh export

The default now simplifies open boundaries in both visual and collider meshes.
Visual and collision settings remain independent. This reduces face-seam and
curved-surface subdivisions that survived the locked-border exporter.

The simulator fidelity policy permits openings smaller than its 17 mm projectile
to disappear. This pass does not classify holes by diameter or guarantee removal
of every small opening. It preserves whole disconnected components that would
otherwise disappear, semantic bindings, identified artwork and protected optical
roles. The terrain is unchanged.

## Settings and source

`default.json` records the final export. Both meshes use a 4 mm simplifier metric,
with separate 12 mm visual and 8 mm collision sampled limits. Every changed
primitive is checked in both directions using up to 4,096 triangles per direction,
with three points per triangle. These measurements are not certified maximum
errors against STEP.

The base visual uses a 0.5 mm metric and 2 mm sampled limit. At the coarse default,
its backing panel partly covered the preserved wordmark. Close-up renders verified
that the tighter base setting fixes this. The base collider keeps the default.
Exact visual selections preserve base, dart-gate and rune artwork, plus the
resource-zone logo housing. The other curved parts remain visibly coarser up close.

The source snapshot is retained locally at `../assets/rm2026-simulation-source`.
It contains archived unsimplified semantic equipment and the deployed terrain.
The resource zone and tech core were recovered from denser archived exports after
an intermediate output directory was removed. Their bounds match the deployed
assets within 0.086 mm. See the adjacent
[recovery record](../2026-09-11-aggressive-mesh/recovered-inputs.json) and
[source record](../2026-09-11-aggressive-mesh/source-record.json).
The parallel semantic-reference work is not part of this export.

The exporter tries six successively halved tolerances and keeps the smallest
accepted result. This matters because an overly coarse collapse can delete a
component, causing its original geometry to be restored. A lower tolerance can
retain the component with fewer triangles. `aggressive.json` and `extreme.json`
record initial experiments using the earlier first-accepted search; they are not
the deployed preset.

## Results

See `counts.json` for placed scene triangles and the simulator's actual static
collider count. Counts include the selected scene and instance placements, not
GPU draws after culling. Referenced GLB bytes include both visual and collider
files, counted once per asset.

| Measure | Previous default | Unlocked default | Reduction |
| --- | ---: | ---: | ---: |
| Placed visual triangles | 3,018,741 | 1,183,564 | 60.8% |
| Static collider triangles | 2,169,201 | 938,536 | 56.7% |
| Referenced GLB bytes | 259,669,320 | 113,885,912 | 56.1% |
| Median scene-ready seconds | 6.11 | 2.80 | 54.1% |
| Median collider parse seconds | 2.01 | 0.92 | 54.5% |


`startup.json` contains three alternating before/after runs with the same debug
executable, built from simulator main `b4428aa` plus the collider-contract change.
OS caches were not cleared. Scene-ready measures CPU scene instantiation, not
first-frame presentation. These are startup measurements, not FPS or physics
step-time benchmarks. Background desktop activity can affect the timings.

The Python suite passed all 68 tests. The simulator workspace passed all 164
Rust tests, formatting, Clippy with warnings denied, and the module-boundary
check. Regression tests cover unlocked-border declarations, dense sampling,
component retention, refinement selection, explicit artwork preservation and
semantic metadata retention. `validation.json` records unchanged terrain files,
unchanged articulation data apart from refreshed hashes, exact selected artwork
geometry and sampled deviations. The real simulator loader verifies package
hashes and contracts in `after-inspect.log`.

## Reproduce

From rm-map-tools, build an unused output directory:

```sh
ocpenv/bin/python python/simplify_package.py rules/simplify-simulation.example.json
```

The archived benchmark config writes to `out/unlocked-default`. With that output
and the previous default still installed, reproduce measurements with:

```sh
ocpenv/bin/python benchmarks/2026-09-11-unlocked-mesh/counts.py
ocpenv/bin/python benchmarks/2026-09-11-unlocked-mesh/validate.py
ocpenv/bin/python benchmarks/2026-09-11-mesh-simplification/benchmark_startup.py \
  ../rm-simulator-unlocked ../rm-simulator/local-assets/field \
  out/unlocked-default out/unlocked-startup --runs 3
```

After deployment the old package is retained locally at
`../assets/rm2026-before-unlocked-20260911`. Use that path for the before package
when repeating the startup command. Adjust the `before` path in the count script
if recounting both snapshots.

Local review images are in `out/unlocked-validation`, including
`base-medium.png`, `dart-final.png` and `resource-final.png`. The full simulator
screenshots are in `out/unlocked-startup`. CAD files and rendered CAD images stay
outside Git.
