# Simulation preset validation

The candidate exported successfully from the corrected V1.2.0 source package
plus its V2.0.0 road graft. The runtime package is at
`out/simulation-runtime`; the installed field was not replaced. Settings and
usage are in [export presets](../../docs/export-presets.md).

| Metric | Refreshed baseline | Simulation candidate | Reduction |
|---|---:|---:|---:|
| Runtime scene triangles, default pilot | 9,743,200 | 7,334,576 | 24.7% |
| Static collider triangles after Rapier cleanup | 8,425,384 | 4,927,403 | 41.5% |
| Static collider vertices | 5,049,115 | 2,866,671 | 43.2% |

The loaded scene has 2,218 mesh entities in both cases. These counts measure
scene geometry, not GPU submissions or draw calls. The simulation preset
preserves terrain density. Deployment retains the existing animation-ready
rune/outpost, so their new element-export LODs do not contribute to these runtime
savings yet. The reference input was the snapshot used for the
[refreshed baseline](../2026-09-11-simulator-baseline/README.md).

## Complete element exports

| Asset | Visual triangles per instance | Collider triangles per instance |
|---|---:|---:|
| Base | 652,669 | 504,544 |
| Outpost | 547,358 | 387,314 |
| Rune | 1,367,202 | 967,937 |
| Dart station | 621,220 | 504,181 |
| Resource zone | 1,234,252 | 994,092 |
| Centre platform | 33,255 | 32,962 |
| Fortress | 272 | 272 |
| Tech core | 144,415 | 104,958 |
| Undulating road | 40,588 | 40,588 |
| Outpost footing | 20 | 20 |

The full-map element export contains 7,920,113 visual and 6,110,905 collision
triangles. It uses newly exported rune/outpost and is distinct from the runtime
package above, which carries their older animation-ready geometry. Do not
compare the full-map count directly to runtime scene counts.

The exporter accounted for all 79,247 assigned source bodies, reported zero
read failures, zero bounding-box mismatches and zero placement warnings. The
explicit `centre-logo-sheets` exclusion removed 293 collider triangles and kept
all visual triangles. Named collision anchors remain for excluded parts.

One resource-zone part, `7000001_1_1`, failed to mesh a 53.51 mm² conical face at
the requested collision settings. The complete finer visual mesh was used for
that entire collider part. `export-results.json` records the failed attempt,
`fallback_to_visual` and effective 4 mm / 0.5 rad tolerance. No incomplete mesh
was exported. The first attempt was correctly rejected before this fallback was
implemented; its incomplete output remains under `out/simulation-elements-incomplete`.

## Runtime and timing checks

The candidate loaded all 16 CAD instances and completed 600 pilot frames after
180 warmup frames. Mean frame interval was 16.86 ms. A paused overview screenshot
was inspected: field structures, painted markings and text remain visible.
The screenshot is at `out/tessellation-benchmark/candidate-overview.png`.

Three 14-robot driving/firing trials used the same workload definition as the
refreshed baseline. They averaged 0.2067, 0.2601 and 0.2067 ms per tick; p95 values
were 0.2997, 0.4905 and 0.2904 ms. Collider construction took 4.35, 3.38 and 3.40
seconds. These samples do **not** establish a physics tick speedup. They are
slower than the refreshed baseline's roughly 0.193 ms mean, and one trial has a
26.5 ms maximum tick. Desktop/parallel-task activity, rebuilt dependencies and
changed contact geometry were not controlled. No FPS or tick-speed improvement
is claimed from these samples. Triangle reduction is verified independently.

The candidate render smoke check used the archived baseline application source
with newly built dependencies, including source-collider selection. It avoids
changing the active simulator source while other work continues. The exact
baseline is separately pinned in its report. Candidate timing is exploratory,
not a controlled before/after performance study.

## Checks and artifacts

- Full arena and element exports passed their source coverage and geometric
  validation. `field-export.log` and `elements-export-v2.log` retain summaries.
- All 36 Python tests passed, including semantic integration tests available at
  the time of the check, policy validation, independent OCCT meshing, collision
  fallback, text exclusion and deployment preservation.
- Simulator server tests passed, 31 including its binary test. Application tests
  passed, 22 including terrain-driving checks. Server Clippy passed with warnings
  denied. Temporary compile errors from concurrent application edits were absent
  in the successful application test run; no unrelated code was changed to fix them.
- `samples.json` contains isolated part comparisons across legacy, simulation and
  preview settings. `sample_tessellation.py` reproduces them from the repository
  root with the OCP interpreter. They are triangle comparisons, not export-time
  performance benchmarks.
- `export-results.json` contains source coverage, runtime results, per-asset
  settings/count summaries and the collider fallback record.

Presets change mesh hashes. Semantic input pins must be regenerated and checked
for the chosen LOD before applying checksum-pinned articulation rules. This
candidate does not replace the parallel task's semantic/reference assets.
