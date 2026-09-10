# Simulator baseline, 10 September 2026

The default pilot scene contains **6,366,457 visual triangles** and **2,167,610 static collider triangles** after Rapier cleanup. On this Apple M3 Pro, the stationary pilot benchmark averaged **13.92–16.67 ms per frame**, approximately **60–72 FPS**. Physics advancement accounted for **0.147–0.183 ms per frame**. Rendering is the first place to investigate for this workload; these measurements do not isolate GPU execution from CPU rendering, presentation, or scheduling.

I did not modify the simulator repository or field assets. New external edits appeared in the simulator during measurement, including a collider-policy rewrite. These results describe the captured pre-edit code and cached libraries, not that newer working tree. Benchmark instrumentation ran in `/tmp/rm-baseline`. This directory contains the report, captured logs, asset hashes, structured results, and instrumentation needed to repeat the experiment.

## Conditions

- Simulator commit `ad3e9f50f26e75bd3fb9c14acf5297ed1268b263`, clean working tree at measurement time.
- Apple M3 Pro, 11 CPU cores, 18 GiB memory, macOS 26.6.2, Metal backend.
- Instrumented application compiled with Rust 1.98.1, edition 2024, `opt-level=3`, linked against existing release dependencies. Exact library and binary hashes are in `raw/build-provenance.json`. This was not a fresh Cargo release rebuild.
- Default `~/dev/RM/assets/rm2026-field` package, V1.2.0 arena with the package's grafted terrain. GLBs counted directly from their scene trees and accessors; hashes are in `raw/assets.json`. The simulator also verifies manifest checksums when loading.
- Package arena tessellation settings: visual linear deflection 2 mm, angular deflection 0.35 rad; collision 10 mm and 0.7 rad. Equipment is a separately exported package.
- Window explicitly set to 1280×720 with scale factor 1.0, `AutoNoVsync`. macOS presentation/compositor pacing can still affect results. Standard field lighting, shadows and postprocessing retained.
- Each render run waits for all 16 CAD instances, discards 180 warmup frames, then measures 600 consecutive frames. Runs were sequential; no simulator input was supplied.
- Pilot runs use the default red spawn. Overview uses `--fly --spawn 0,-18,18 --spawn-yaw-deg 90 --spawn-pitch-deg -45`. Paused uses the default pilot with `--start-paused`.

## Visual geometry

Counts include manifest placements, so the two copies of a base count twice. They are scene inventory counts, not GPU primitive or draw-call counters.

| Asset | Instances | Visual triangles | Raw proxy triangles |
|---|---:|---:|---:|
| Resource zone | 2 | 1,545,112 | 763,952 |
| Base | 2 | 1,359,294 | 649,610 |
| Dart station | 2 | 1,234,144 | 605,238 |
| Rune | 1 | 983,603 | 10,152 |
| Outpost | 2 | 867,022 | 33,942 |
| Tech core | 2 | 180,296 | 77,224 |
| Arena static | 1 | 119,776 | 36,804 |
| Centre platform | 1 | 51,402 | 26,570 |
| Outpost footing | 2 | 40 | 40 |
| Floor | 1 | 12 | 12 |
| **Placed CAD total** | **16** | **6,340,701** | **2,203,544** |

The pilot scene adds 25,756 triangles for procedural visuals, producing 6,366,457 triangles across 2,181 triangle-mesh entities. The overview without a chassis contains 6,353,789 triangles across 2,100 entities.

At the end of the pilot runs, Bevy marked 1,771 mesh entities containing 6,065,749 triangles as view-visible. `ViewVisibility` can include multiple views and shadow visibility. It does not establish how many triangles the main camera rasterizes. Mesh entities also do not equal draw calls because batching and instancing can combine submissions, while shadows and other passes can repeat work.

## Collider geometry

| Stage or group | Triangles |
|---|---:|
| Raw placed collision assets | 2,203,544 |
| Loaded ground and static scenery | 1,412,814 |
| Loaded fixed rune frame and outpost towers | 28,996 |
| Loaded bases and tech cores | 726,834 |
| **Total supplied to Rapier** | **2,168,644** |
| **Static triangles returned by Rapier** | **2,167,610** |

The final meshes have 1,067,870 vertices. Counts exclude the infinite catch plane and dynamic/kinematic cuboid colliders such as robot bodies and armor, which are not triangle meshes.

The default package declares `collision_solids`. The simulator keeps 62 arena solids and drops 325 marking parts, reducing that asset from 36,804 to 17,002 triangles. It does not apply the legacy panel boxing or extrusion policy to this package. Only static nodes of the rune and outpost proxies enter these terrain meshes. Rapier merges duplicate vertices and removes 1,034 degenerate triangles across the resulting meshes.

One measured startup loaded and verified manifests/assets in 789 ms and decoded/assembled terrain in 86 ms. Across 12 field constructions, installing the terrain colliders took 1,037–1,127 ms. These are wall times with uncontrolled filesystem cache state, not cold-start benchmarks. Collider installation includes mesh cloning and Rapier construction.

## Frame performance

| Run | Mean frame ms | p50 ms | p95 ms | p99 ms | FPS from mean | Mean physics advance ms/frame |
|---|---:|---:|---:|---:|---:|---:|
| Pilot 1 | 15.70 | 16.35 | 28.93 | 31.40 | 63.7 | 0.165 |
| Pilot 2 | 16.67 | 16.66 | 17.56 | 17.93 | 60.0 | 0.183 |
| Pilot 3 | 13.92 | 13.47 | 23.90 | 25.79 | 71.8 | 0.147 |
| Paused pilot | 14.08 | 13.40 | 28.07 | 34.38 | 71.0 | 0.00014 |
| Overview, no chassis | 13.26 | 12.55 | 24.88 | 29.63 | 75.4 | 0.00175 |

Frame intervals are measured between `Last` schedule samples using `Instant`. Physics timing surrounds `Simulation::advance`, including its pacing bookkeeping, but excludes snapshot creation and scene synchronization. The three active pilot runs average 10.48–10.98 microseconds per physics tick while rendering concurrently.

Paused and overview each have only one run. Their differences should not be interpreted as controlled speedups given the pilot run-to-run spread. These are stationary scene baselines, not driving/firing render benchmarks. GPU pass timing, actual submitted triangle counts, draw calls and memory use remain unmeasured. Bevy 0.19.1's render diagnostics document CPU-only measurements on Metal for this backend.

## Isolated physics performance

Each scenario constructs a fresh field, settles it for 2,000 ticks, then measures 10,000 calls to `Field::step(1)` with a 1 ms simulation timestep. Three repetitions per scenario. Rendering is not running. Means below average the three repetition means; p95 shows the range of per-run p95 values.

| Workload | CAD collision mean ms/tick | CAD collision p95 ms/tick | Flat-floor mean ms/tick |
|---|---:|---:|---:|
| One stationary chassis | 0.00674 | 0.00796–0.00838 | 0.00558 |
| One driving chassis, 10 shots/s | 0.04658 | 0.06125–0.06246 | 0.04001 |
| 14 driving chassis, 10 shots/s each | 0.18281 | 0.22983–0.24354 | 0.07972 |

The 14-chassis test consumes about 18.3% of one core's 1 ms tick budget on average. All reported p95 values remain below that budget. Full per-run p99 and maximum values are in `results.json`.

The synthetic driving command is 1 m/s forward and 0.25 rad/s yaw. Robots alternate teams and start at 0.8 m lateral offsets. Firing uses a muzzle 0.5 m above each chassis pose and the 17 mm speed limit, producing 100 shots per robot over the measured interval. Command submission, spawning shots, and collecting firing snapshots occur outside the timed step. Thus these numbers measure world stepping, not the entire server loop. Terrain changes trajectories and contacts, so the flat-floor comparison is not a prediction of a mesh simplification speedup.

The empty scenario is present in raw results but is not a physics throughput measurement: the world skips its Rapier step when no chassis or projectiles require it, and the timings approach timer resolution. The referee remains enabled but no match-start command is issued in these scenarios.

## What to optimize next

Resource zones, bases, dart stations and the rune account for 80.8% of placed visual triangles. Start visual LOD/tessellation experiments there. The arena-static asset accounts for only 1.9%, so optimizing it alone has a low upper bound on total triangle savings.

Resource zones, bases and dart stations also dominate static collider geometry. Collider presets could reduce asset size and roughly one second of construction work, even though the measured tick workloads already fit the budget. Preserve the geometry needed for terrain traversal and projectile contact when comparing candidates.

Treat mesh merging and tessellation reduction as separate experiments. Merging coplanar surfaces can remove triangles only if it retriangulates them; batching meshes alone primarily changes submission overhead and culling granularity. This baseline has not measured the savings from either approach. Compare each candidate using these same scenes and workloads, plus collision/visual fidelity checks, before selecting presets.

## Repeat the experiment

The instrumentation is intentionally outside the production application. From `rm-map-tools`, create a temporary copy and build it with Cargo:

```sh
bench_dir="$PWD/benchmarks/2026-09-10-simulator-baseline"
work_dir="$(mktemp -d /tmp/rm-baseline-repeat.XXXXXX)"
git -C ../rm-simulator archive ad3e9f50f26e75bd3fb9c14acf5297ed1268b263 | tar -x -C "$work_dir"
patch -d "$work_dir" -p1 < "$bench_dir/harness/app.patch"
mkdir -p "$work_dir/crates/rm-simulator-server/examples"
cp "$bench_dir/harness/physics.rs" "$work_dir/crates/rm-simulator-server/examples/baseline_physics.rs"
cp "$bench_dir/harness/collider-count.rs" "$work_dir/crates/rm-simulator-server/examples/baseline_count.rs"
cargo build --release --manifest-path "$work_dir/Cargo.toml" -p rm-simulator-app
"$work_dir/target/release/rm-simulator" > pilot.log 2>&1
"$work_dir/target/release/rm-simulator" --start-paused > paused.log 2>&1
"$work_dir/target/release/rm-simulator" --fly --spawn 0,-18,18 --spawn-yaw-deg 90 --spawn-pitch-deg -45 > overview.log 2>&1
cargo run --release --manifest-path "$work_dir/Cargo.toml" -p rm-simulator-server --example baseline_physics > physics.log
cargo run --release --manifest-path "$work_dir/Cargo.toml" -p rm-simulator-server --example baseline_count > collider-count.log
python3 "$bench_dir/harness/count.py" > assets.json
```

Repeat the pilot command three times with distinct output names. Build before timing and run workloads sequentially. The standalone inventory/physics scripts currently name this machine's absolute asset directory; edit that path for another installation. The application accepts `--cad-assets`. The future Cargo rebuild above may differ from the cached release libraries used for these measurements, so record its provenance as a new baseline. GUI launches require a graphical session.
