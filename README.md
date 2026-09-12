# rm-map-tools

[English](README.md) · [简体中文](README.zh-CN.md)

[![CI](https://img.shields.io/github/actions/workflow/status/hxyulin/rm-map-tools/ci.yml?branch=main&label=CI)](https://github.com/hxyulin/rm-map-tools/actions/workflows/ci.yml)
[![Rust 1.88+](https://img.shields.io/badge/Rust-1.88%2B-DEA584?logo=rust&logoColor=black)](Cargo.toml)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20Apache--2.0-blue)](#license-and-source-data)

Split RoboMaster arena CAD into standalone STEP parts, then export field assets for viewers and simulators.

![RoboMaster field overview](docs/previews/field-elements-full-map-top.png)

The tool splits the STEP reference graph before loading geometry into a CAD kernel, so you can process individual parts without importing the whole arena. A recorded M3 Pro run split the 1.25 GB RMUC V2.0.0 source into 429 parts in 8.4 seconds. See [performance measurements](docs/performance.md) for indexing, meshing, memory use, and comparison limits.

## What you can do

- Inspect and split official STEP files while preserving source geometry entities.
- Build GLB packages with separate visual and collision meshes, placements, colors, and semantic metadata.
- Reduce mesh size with configurable tessellation, checked simplification, and texture artwork.
- Export static scenes as SDF, MJCF, or USD, and jointed equipment as SDF, URDF, or USD.
- Inspect models and move joints in the [interactive documentation viewer](docs/viewer.md).

Download prepared assets from the [latest release](https://github.com/hxyulin/rm-map-tools/releases/latest). See [Releases and downloads](docs/releases.md) to choose a format.

## Quick start

Clone the repository and run these commands from its root. You need Rust 1.88+ and Python 3 for the download helper. Indexing and splitting do not require a CAD kernel.

```sh
cargo build --release --locked
python3 source/download.py fetch RMUC2026_V2.0.0.stp
mkdir -p out

target/release/rm-map-tools index source/RMUC2026_V2.0.0.stp -o out/v20.p21idx
target/release/rm-map-tools inspect out/v20.p21idx --json out/v20-inspection.json
target/release/rm-map-tools split out/v20.p21idx -o out/v20
```

The download helper resumes interrupted transfers and verifies checksums. The split writes standalone files under `out/v20/parts/` and a `parts.json` manifest. Source CAD and generated model packages are not included in Git.

Continue with [Getting started](docs/getting-started.md) to validate the parts, or [Exporting](docs/exporting.md) to build a simulator package. CAD processing uses a separate Python environment with OCCT.

## Documentation

| Guide | What you will find |
| --- | --- |
| [Getting started](docs/getting-started.md) | Setup, source downloads, splitting, and validation |
| [Exporting](docs/exporting.md) | Supported formats, required inputs, and export commands |
| [Simplification](docs/simplification.md) | Reduction stages, their order, settings, and checks |
| [Architecture](docs/architecture.md) | STEP processing, asset generation, and code layout |
| [All documentation](docs/README.md) | Technical references, geometry audits, benchmark reports, and the interactive viewer |

The guides also build as a VitePress site with interactive model controls and an English / 简体中文 language toggle. Run `npm ci` and `npm run docs:dev`, or see [site setup and GitHub Pages deployment](docs/site.md).

## License and source data

Code and documentation are dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE). Official CAD and derived model geometry belong to DJI / RoboMaster and remain subject to their terms. This is an independent project. See [NOTICE.md](NOTICE.md).
