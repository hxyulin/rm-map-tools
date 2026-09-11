# rm-map-tools

[English](README.md) · [简体中文](README.zh-CN.md)

[![Rust 1.88+](https://img.shields.io/badge/Rust-1.88%2B-DEA584?logo=rust&logoColor=black)](Cargo.toml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](docs/previews.md)
[![OCCT 8.0.1](https://img.shields.io/badge/OCCT-8.0.1-336699)](docs/split-proof.md)
[![glTF 2.0](https://img.shields.io/badge/glTF-2.0-87C540?logo=gltf&logoColor=white)](docs/semantic-export.md)
[![CI](https://img.shields.io/github/actions/workflow/status/hxyulin/rm-map-tools/ci.yml?branch=main&label=CI)](https://github.com/hxyulin/rm-map-tools/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20Apache--2.0-blue)](#license-and-source-data)

Turn RoboMaster arena CAD into manageable parts, checked simulator assets, and animated mechanism previews.

**A 1.25 GB STEP becomes 429 standalone parts in 8.4 seconds. Importing, validating, and meshing those parts takes 4 minutes 17 seconds with 4.7 GB peak RAM on an M3 Pro.**

[Performance & RAM](docs/performance.md) · [Architecture diagrams](docs/architecture-overview.md) · [Demo gallery](docs/demos.md) · [Export settings](docs/export-presets.md)

![RoboMaster field overview](docs/previews/field-elements-full-map-top.png)

## Why this project exists

The official field releases contain millions of STEP entities, deeply shared presentation data, sheet geometry, and mixed assemblies. Loading the entire file into a CAD application makes even a small change expensive. A simulator also needs more than one giant mesh: separate colliders, sensible origins, identifiable armor and lights, and joints that move the correct parts.

`rm-map-tools` splits the STEP reference graph before invoking a CAD kernel. Rust indexes and copies the relevant source entities; OCCT then imports individual parts. Python assembles the field, preserves source ownership and colors, adds semantic metadata, and checks the resulting geometry. You can work on one mechanism without repeating a whole-field import.

## Performance and RAM

The practical difference is **hours for the recorded whole-file workflows versus seconds to split and minutes to validate and mesh the parts**.

| Workflow | Machine | Elapsed time | Peak RAM | What the time covers |
| --- | --- | ---: | ---: | --- |
| Whole-file OCCT conversion | M5 Max Mac¹ | **8 h 57 min** | **~40 GB** | STEP read, XCAF transfer, meshing, and one GLB write |
| SolidWorks 2024 | Ryzen 9 9950X3D² | **15 h** | **~25 GB** | User-reported full-file run; exact stage unrecorded |
| Rust split, RMUC V2.0.0 | M3 Pro, 18 GiB | **8.4 s** | **3.6 GB** | Write all 429 standalone STEP parts |
| OCCT per-part validation and meshing | M3 Pro, 18 GiB | **4 min 17 s** | **4.7 GB** | Import, validate, and mesh the split V2.0.0 parts |

Indexing the V2.0.0 file takes another **1.3 s**. The 993 MB V1.2.0 release splits into **1,047 parts in 2.7 s**, with **1.9 GB** peak split RAM.

¹ The conversion log records 32,229 seconds. The M5 Max machine attribution comes from the project owner; the approximate RAM figure comes from the recorded project notes. ² The SolidWorks result is supplied by the project owner. These are different machines and workloads: the 4 min 17 s measurement does **not** include an equivalent whole-field GLB serialization, so this table is not an end-to-end speedup ratio. Peak RAM is observed usage, not a guaranteed minimum system requirement.

[Timing breakdown, provenance, and limitations →](docs/performance.md)

The optional mesh simplification pass also reduced measured simulator scene setup from **15.50 s to 5.73 s** and referenced GLB size from **587 MB to 260 MB**. This was a local warm-cache comparison, not a frame-rate or cold-start claim. [Benchmark →](benchmarks/2026-09-11-mesh-simplification/README.md)

## What it produces

| Output | Purpose |
| --- | --- |
| `parts/*.stp` + `parts.json` | Standalone source parts, ownership, bounds, face counts, and colors |
| Visual and collision GLBs + `manifest.json` | Placed field elements with file hashes and explicit collision contracts |
| glTF metadata + `articulation.json` | Readable part names, joints, armor size/family, LEDs, team color, and layers |
| Semantic reference package | Reviewable mechanisms and explicitly labeled reconstructions, separate from the simulator installation |
| GIF / MP4 / PNG + JSON reports | Clean camera orbits, joint inspections, and source-versus-demo audits |
| SDF / URDF / USD | [Articulated equipment](docs/articulated-formats.md) with existing joint bindings; [static scene export](docs/getting-started.md) also supports MJCF |

The STEP split preserves geometry entities verbatim. Tessellation approximates surfaces, and optional mesh simplification is lossy with sampled deviation checks. These are separate stages with separate evidence. See the [split proof](docs/split-proof.md), [geometry audit](docs/geometry-audit.md), and [simplification contract](docs/mesh-simplification.md).

## See it move

The [collapsible demo gallery](docs/demos.md) contains every saved mechanism GIF and MP4, field overview images, and source audits.

| Mechanism | Preview | What moves |
| --- | --- | --- |
| Base | [Orbit MP4](docs/previews/clean/base-joints-orbit.mp4) | Shields and rail-mounted dart target; reconstructed inner wall and armor stay fixed |
| Technology Core | [Pose-tour MP4](docs/previews/clean/tech-core-demo-orbit.mp4) | Six-axis demo with restored tool panels and a 100 mm translation segment |
| Power Rune | [Orbit MP4](docs/previews/clean/rune-joints-orbit.mp4) | Arms and surrounding hubs; central logos and shafts stay fixed |
| Outpost | [Orbit MP4](docs/previews/clean/outpost-joints-orbit.mp4) | Rotor and attached hardware |
| Dart station | [Orbit MP4](docs/previews/clean/dart-station-joints-orbit.mp4) | Window slides along its inclined guides |

Shield travel and reconstructed dimensions are illustrative. The Core's exported joints are frames only; its mesh animation uses a separate preview rig with schematic bearings. Demo timing is not a match controller. Each gallery section links to the relevant evidence and limitations.

## Quick start

Rust 1.88 or later is enough to index, inspect, and split. No CAD kernel is needed for these commands.

```sh
cargo build --release --locked
python3 source/download.py fetch RMUC2026_V2.0.0.stp
mkdir -p out

target/release/rm-map-tools index source/RMUC2026_V2.0.0.stp -o out/v20.p21idx
target/release/rm-map-tools inspect out/v20.p21idx --json out/v20-inspection.json
target/release/rm-map-tools split out/v20.p21idx -o out/v20
```

The download is large. It resumes interrupted transfers and verifies the recorded checksum. An existing verified copy is reused.

For OCCT validation, simulator export, and video rendering, follow [Getting started](docs/getting-started.md). Export jobs are configured through [JSON files](docs/detail-optimization.md); paths in those files are relative to the job file. `out/` is disposable staging. Keep original sources and final packages separately.

## Architecture and documentation

[Architecture overview](docs/architecture-overview.md) has separate diagrams for STEP processing, simulator export, and semantic motion. The [implementation reference](docs/architecture.md) covers Rust modules and the split algorithm.

| Guide | Focus |
| --- | --- |
| [Performance](docs/performance.md) | Elapsed time, memory, machine attribution, and benchmark scope |
| [Getting started](docs/getting-started.md) | Installation, splitting, validation, export, and preview commands |
| [Demo gallery](docs/demos.md) | Collapsible animations and visual comparisons |
| [STEP notes](docs/step-notes.md) / [split proof](docs/split-proof.md) | Source structure and preservation checks |
| [Export presets](docs/export-presets.md) / [detail optimization](docs/detail-optimization.md) | Tessellation, collision policy, and export jobs |
| [Semantic export](docs/semantic-export.md) / [reference assets](docs/reference-assets.md) | Joint, armor, LED, color, and layer contracts |
| [Geometry audit](docs/geometry-audit.md) / [mesh simplification](docs/mesh-simplification.md) | Ownership, omissions, and controlled mesh reduction |

## License and source data

Code and documentation are dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE). Official CAD and derived model geometry belong to DJI / RoboMaster and remain subject to their terms. Model files are not committed; the repository includes rendered previews and derived reports. This is an independent project. See [NOTICE.md](NOTICE.md).

### Grafted road wordmarks

`python/compose_road_markings.py SOURCE OUTPUT` composes the V1.2.0 field with
its grafted V2 bumpy roads by omitting two reviewed duplicate ROBOMASTER
wordmarks beneath the roads. It retains the other wordmarks and all terrain.
The same 30 exact source nodes are omitted from the visual and collision
scenes, with updated checksums and a `road-marking-composition.json` report.
The source is retained and the output directory must not exist. This is a
composition decision based on RMUC 2026 V2.1.0 Figure 4-36, not a change to the
source CAD or an automatic removal of thin/coloured geometry.

```sh
ocpenv/bin/python python/compose_road_markings.py SOURCE OUTPUT
PYTHONPATH=python ocpenv/bin/python -m unittest test_compose_road_markings
```

### Wall and elevated decorations

Wall-mounted and elevated lettering can be classified with the reviewed V1.2.0
rules. This keeps the original visual primitives, tags them with
`extras.rm.layer = "decoration"` and `kind = "text"`, `"logo"` or `"symbol"`, and removes
their matching collider primitives. The centre deck repair also separates the
symbol sidewalls and restores flat collision backing at the original deck
height, removing the symbol outlines from its triangulation. The layer is
visible by default and listed in `decoration-layer.json`. It does not depend on elevation, orientation
or material colour alone. The simulator reads the resulting collision files;
this export does not add an in-app visibility control.

```sh
PYTHONPATH=python ocpenv/bin/python python/classify_decorations.py SOURCE OUTPUT --rules rules/decorations-v1.2.0.json
PYTHONPATH=python ocpenv/bin/python -m unittest test_classify_decorations test_collision_artwork
```

The rules cover both centre-platform wall wordmarks and circle-and-slash deck
markings, the dart gate logos and the rune face logos. They retain walls, platforms and logo backing disks.
Output must be a new directory; source packages remain intact.
