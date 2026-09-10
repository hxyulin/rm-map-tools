# Corrected-geometry baseline, 11 September 2026

This replaces the earlier baseline for preset decisions. It captures simulator
commit `0a93409d23ea4f8a3f46b02a9069245c60d8d3d8` and the newly deployed field,
before this task's optional source-tessellated collider support. The scene has
**9,743,200 visual triangles** across **2,218 mesh entities** and
**8,425,384 static collider triangles** after Rapier cleanup.

The corrected geometry increases scene triangles by 53.0% relative to the
[previous baseline](../2026-09-10-simulator-baseline/README.md). The source/body
corrections and switch to visual geometry for collisions both changed the
baseline; this comparison does not isolate either change.

## Method and limits

Apple M3 Pro, 11 CPU cores, 18 GiB memory, macOS 26.6.2, Metal. Fresh
`cargo build --release -p rm-simulator-app`, then instrumented application linked
against those release libraries with Rust 1.98.1 and `opt-level=3`. Library and
binary hashes are in `raw/build-provenance.json`.

The deployed asset directory was copied to `/tmp/rm-baseline-v2/field` before
measurement. Its GLB hashes and input manifests are in `raw/`. This fixes inputs
while the parallel articulation task continues. Other desktop/parallel-task
activity was not controlled, so frame timings are observations rather than a
noise-free hardware benchmark.

1280×720, scale factor 1, AutoNoVsync, standard field lighting and postprocessing.
All 16 CAD instances must load; discard 180 warmup frames, then sample 600 frames.
Three default stationary pilot runs, one paused pilot run and one flying overview
at FLU `0,-18,18`, yaw 90°, pitch -45°. Run sequentially. Frame intervals use
`Instant` in `Last`; physics frame timing surrounds `Simulation::advance` and
excludes snapshot/scene synchronization. macOS compositor pacing may persist.

Counts are mesh inventory, not draw calls or GPU rasterized triangles. Bevy
ViewVisibility can include shadow views. GPU pass times, actual submitted
triangles, draw calls, and memory use were not measured. Pilot run 3 includes a
1.012-second frame stall; it remains in the statistics below.

## Render measurements

| Run | Mean ms | p50 ms | p95 ms | p99 ms | Max ms | FPS from mean | Physics ms/frame |
|---|---:|---:|---:|---:|---:|---:|---:|
| pilot-1 | 16.67 | 16.64 | 17.73 | 17.99 | 20.89 | 60.0 | 0.1584 |
| pilot-2 | 18.04 | 17.21 | 32.79 | 37.94 | 42.03 | 55.4 | 0.1990 |
| pilot-3 | 19.34 | 16.68 | 32.66 | 39.32 | 1012.25 | 51.7 | 0.1950 |
| paused | 16.70 | 16.66 | 17.47 | 17.80 | 67.25 | 59.9 | 0.0002 |
| overview | 16.67 | 16.66 | 17.57 | 17.85 | 19.45 | 60.0 | 0.0019 |

Pilot view-visible inventory at the final sample is 9,442,492 triangles across
1,808 entities. Procedural robot/overlay visuals add 25,756 triangles to the
placed CAD total of 9,717,444.

## Placed visual assets

| Asset | Instances | Triangles |
|---|---:|---:|
| resource-zone | 2 | 3,708,418 |
| base | 2 | 1,789,798 |
| dart-station | 2 | 1,782,644 |
| rune | 1 | 983,603 |
| outpost | 2 | 867,022 |
| tech-core | 2 | 432,876 |
| arena-static | 1 | 119,776 |
| centre-platform | 1 | 33,255 |
| outpost-footing | 2 | 40 |
| floor | 1 | 12 |

## Physics

The loader supplies 5,644,145 ground/scenery triangles, 561,401 fixed rune/outpost
triangles and 2,222,674 equipment triangles, totaling 8,428,220. Rapier removes
2,836 degenerate triangles; the final static geometry has 5,049,115 vertices.
Infinite catch plane and dynamic/kinematic cuboid colliders are excluded.

Collider construction across 12 field builds took 4.72–5.14 seconds. One manifest
verification and terrain decoding sample is recorded at the start of
`raw/physics.log`; filesystem cache state was not controlled.

Each isolated physics scenario settles for 2,000 ticks and samples 10,000 calls
to `Field::step(1)`, three repetitions, 1 ms simulation timestep. Driving uses
1 m/s forward and 0.25 rad/s yaw; each robot fires a 17 mm projectile at the rule
speed limit every 100 ticks. Fourteen robots alternate teams and start at 0.8 m
lateral offsets. Commands, shot creation and firing snapshots are outside the
timed step. No render benchmark runs concurrently. The referee is enabled but
the match is not started. The empty workload skips Rapier and is near timer
resolution, so it is excluded from this table.

| Workload | Mean ms/tick, CAD | Largest run p95 ms/tick | Mean ms/tick, flat floor |
|---|---:|---:|---:|
| one_idle | 0.00701 | 0.00862 | 0.00551 |
| one_drive_fire | 0.04797 | 0.06517 | 0.03961 |
| 14_drive_fire | 0.19266 | 0.25421 | 0.08030 |

The 14-robot workload uses about 19.3% of one core's 1 ms tick budget on average.
The flat-floor comparison changes contacts and trajectories; it does not predict
how a particular simplification will perform. Construction cost has grown much
more than the sampled per-tick cost.

## Reproduction

Use `git archive 0a93409d23ea4f8a3f46b02a9069245c60d8d3d8` from the simulator
repository to create a temporary checkout, then apply `harness/app.patch` with
`patch -p1`. Build the application in release mode. Put `harness/physics.rs` and
`harness/collider-count.rs` under the server crate's `examples/` directory to run
those with `cargo run --release -p rm-simulator-server --example NAME`.
The application accepts `--cad-assets`; standalone scripts contain an absolute
asset path that must be adjusted for another installation. Use the same hashed
asset snapshot for an exact input comparison. Geometry files are intentionally
not included in this repository.

Raw per-run summaries, input hashes, and `results.json` are retained. No result
from this baseline includes the new export presets or collision exclusions.
