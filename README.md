# rm-map-tools

Tooling that turns the DJI RoboMaster (RMUC) field STEP releases into a
losslessly split, per-part package that CAD kernels load in seconds instead
of hours, plus the validation and preview pipeline that proves it.

| Document | What it covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Crates, modules, data structures, the split algorithm, performance |
| [`docs/step-notes.md`](docs/step-notes.md) | What the DJI STEP files actually contain: exporters, ownership chain, colours, transforms, traps |
| [`docs/previews.md`](docs/previews.md) | The OCCT mesh bundle and the 3D / plan-view pages built from it |
| [`docs/split-proof.md`](docs/split-proof.md) | The measured proof that the split is lossless, with every number |
| [`HANDOFF.md`](HANDOFF.md) | Background, decisions, target package layout, open questions |

## Pipeline

```mermaid
flowchart LR
    A[(DJI STEP archive<br/>~/dev/RM/assets, read-only)] -->|index, 1 s/GB| B[.p21idx sidecar<br/>ids · types · byte ranges · refs]
    B -->|model| C[Model<br/>products · occurrences · bodies<br/>faces · colours · bboxes]
    C -->|inspect| D[summary / --json]
    C -->|split, 3-8 s| E[package<br/>parts/*.stp + parts.json]
    E -->|OCCT per part| F[validation.json<br/>faces · bbox · colours · 1 mm mesh]
    E -->|mesh_parts.py| G[mesh bundle<br/>.bin + .json]
    G -->|build_viewer.py| H[3D pages]
    E -.->|next: rules, match, report| I[grouped, coloured package<br/>for the simulators]
```

Everything left of the package is Rust and needs no CAD kernel. Everything
right of it runs OCCT on one part at a time, which is why it fits in a few GB
of RAM instead of the ~40 GB a whole-file import takes.

## Crates

| Crate | What |
|---|---|
| `crates/step21` | Library: streaming STEP Part 21 scanner (`scan`), columnar entity index with binary sidecar (`index`), product / assembly / body / style model (`model`), lossless per-product split (`split`), string and number helpers (`decode`). No typed entity graph; everything works on byte ranges. |
| `crates/rm-map-tools` | CLI: `index`, `inspect`, `split`. |

## Use

```sh
cargo build --release
B=target/release/rm-map-tools

# one streaming pass; writes <file>.p21idx next to the file
# (use -o to put it elsewhere: the archive directory must stay untouched)
$B index ~/dev/RM/assets/rm2026-cad/UTF-8__RMUC2026_V2.0.0.stp -o /tmp/v20.p21idx

# products, tree, bodies, faces, colours; numbers match HANDOFF §2
$B inspect /tmp/v20.p21idx            # or the .stp directly (indexes in memory)
$B inspect /tmp/v20.p21idx --json v20.json   # full dump

# one standalone STEP per product + parts.json manifest
$B split /tmp/v20.p21idx -o /tmp/pkg_v20
$B split /tmp/v20.p21idx -o /tmp/pkg_one --products 59853   # a single product id
```

`inspect` and `split` accept either the sidecar or the STEP file. A sidecar is
reused only if its recorded source path and size still match.

### Field package for the simulators

`prototype/export_field_package.py` (OCP venv, see `docs/previews.md`) turns a
split package's arena into the asset directory that `rm-simulator` and
`rm-vision-sim` load: `floor.glb`, `arena-static.glb`, their `*-collision.glb`
proxies, `manifest.json` (schema 1, SHA-256 per file, `floor_top_source_z_m`)
and `validation.json`. Every `BREP_*` solid becomes one glTF node named
`source_<product id>_<name>` in the CAD arena frame (Z up, metres), placed by
the STEP assembly transforms, with one primitive per effective face colour.
The rune, outpost and `equipment/` files are copied from an earlier
extraction, whose placements share the arena frame.

```sh
python3 prototype/p21index.py ~/dev/RM/assets/rm2026-cad/UTF-8__RMUC2026_V1.2.0.step v12.npz
$B split v12.npz -o rs_v12
ocpenv/bin/python prototype/export_field_package.py rs_v12 v12.npz \
  --equipment ~/dev/RM/assets/rm2026-extracted --out ~/dev/RM/assets/rm2026-field \
  --graft rs_v20:v20.npz:BREP_220,BREP_192
```

The V1.2.0 arena (353 solids, 382 placements, 33 k triangles at 2 mm) is the
one with face colours, and it shares the arena origin with V2.0.0: the V2.0.0
equipment placements land exactly on its plate tops. Its slab is flat at
z = −1641.3 mm, where V2.0.0's crowned slab is at −1530.4 mm on its pads.
Both releases put the same hex-marked truncated pyramid (17° ramps, 0.15 m
top) on the centre line, but where V2.0.0 models the 起伏路段 undulating road
near each side wall (`BREP_220` and `BREP_192`, one solid each: a 2.4 × 2.1 m
strip of 70 mm waves on the 0.2 m deck) the V1.2.0 STEP has a flat deck whose
marking skin has a cutout of that size, so `--graft` takes those two solids
from the V2.0.0 split package (`rs_v20`, `v20.npz`), removes the 2.6 % tilt of
the crowned slab under each, sets them on the V1.2.0 floor top and colours
them with V1.2.0's plate top and side colours (`--graft-colours`). They are
`graft_*` nodes with their own collision proxies, and the manifest records
them under the arena asset's `grafted` entry with the donor file's checksum.
The exporter checks that every part reads, that each node's mesh covers the
part's vertex box, and fails on any mismatch. The collision proxies are the
same solids at 10 mm / 0.7 rad, one closed node each, within 2.5 mm of the
visual; the manifest's `collision_solids: true` tells consumers they can use
those nodes as they are and need only drop the flat marking sheets. The
arena is every `BREP_*` product plus `--arena-products` (default `0010_1,00_1`,
the base pedestals and the steps behind them, which V1.2.0 keeps as top-level
products of their own);
the exporter prints and records in `validation.json` every other assembly
with solids it leaves out, so an omission is visible: the outposts, bases,
runes and the corner structures, which the copied equipment files cover or
which neither package carries.

### Field elements and the full map

`prototype/export_elements.py` (OCP venv) builds on a field package and adds
one placed asset per field element, driven by `rules/elements-v1.2.0.json`,
which pins each element to product names (the IGES round trip stripped the
Chinese names from V1.2.0; they were recovered by placing every sub-assembly
in the arena frame and matching it against the named occurrences of
V2.0.0). Each element is exported once in a local frame (arena axes, origin
at the reference instance's footprint centre and lowest vertex) as
`<name>.glb` plus `<name>-collision.glb`, and the manifest lists every
instance as a rigid placement (translation, xyzw quaternion, 4×4 matrix):
exact from the STEP occurrence transforms for instanced sub-assemblies, or
the best quarter turn about Z for elements whose instances are distinct
products, with the residual recorded. `full-map.glb` composes the floor, the
arena and every placed element. Assemblies that carry tens of thousands of
single-face sheets next to their solids are split solids-only first
(`Splitter.write(..., solids_only=True)` into `<pkg>/solids/`).

| Asset | 名称 | V1.2.0 products | Instances |
|---|---|---|---|
| `base` | 基地 | `001_1_ASM` | 2, exact |
| `outpost` | 前哨站 | `0009_1_ASM` + footing `0008_1` | 2, exact (one footing sits 3.6° off, reported) |
| `rune` | 能量机关 | `0007_1_ASM` | 1 |
| `dart-station` | 飞镖发射井 | `0013_1_ASM` | 2, exact |
| `resource-zone` | 资源区 | `7000001_1_ASM` | 2, exact |
| `fortress` | 堡垒 | `0006_1_ASM` minus the tech cores | 1 |
| `tech-core` | 国赛科技核心 | `0006_1_24..36`, `0006_1_37..49` | 2, matched half turn |
| `undulating-road` | 起伏路段 | V2.0.0 `BREP_220`, `BREP_192` (graft) | 2, matched half turn |

```sh
ocpenv/bin/python prototype/export_elements.py out/v12 v12.npz \
  --rules rules/elements-v1.2.0.json --field ~/dev/RM/assets/rm2026-field \
  --out ~/dev/RM/assets/rm2026-field-elements --graft out/v20:v20.npz
```

## Status

| Step | State |
|---|---|
| Archive V1.2.0 and the rune file with checksums | done |
| Lossless per-product split, Python proof | done, `docs/split-proof.md` |
| OCCT validation of every part, per-part meshes vs the 9 h whole-file glb | done |
| Rust `index`, `inspect`, `split` | done, byte-identical to the validated Python output |
| 3D previews of V2.0.0 and V1.2.0 from the split parts | done, `docs/previews.md` |
| Simulator field package (V1.2.0 arena in colour + carried-over equipment) | done, `prototype/export_field_package.py`, installed as `~/dev/RM/assets/rm2026-field` |
| Field elements (base, outpost, rune, dart station, resource zone, fortress, tech core, 起伏路段) as placed assets plus `full-map.glb` | done, `prototype/export_elements.py`, installed as `~/dev/RM/assets/rm2026-field-elements` |
| Per-body split for the flat V2.0.0 equipment products | not started |
| `assembly.stp`, package layout, `rules/`, `match`, `report` | not started, see `HANDOFF.md` §4–§6 |

## Repository layout

```
crates/step21/            library crate (scan, index, decode, model, split)
crates/rm-map-tools/      CLI
prototype/                Python originals and OCCT validators (see docs/architecture.md)
prototype/preview/        mesh bundle -> 3D page builder and template
docs/                     architecture, STEP notes, previews, proof report
out/{v20,v12,rmul}/       manifests and validation reports of the last runs
```

The Python scripts in `prototype/` need the `cadquery-ocp` venv described in
`docs/previews.md`; the Rust crates need only a stable toolchain (Rust 1.88
or newer, edition 2024). Part files, sidecars and mesh bundles are
regenerable and are not stored in the repository; `out/v12/parts.json` is
kept gzipped because it describes 79,247 bodies.

## Source data, ownership and licence

The field models this tool processes are the official RoboMaster
University Championship / League arena CAD releases by **DJI / RoboMaster**
(https://www.robomaster.com). They are DJI's intellectual property,
released to competition teams under DJI's terms, and **no CAD file or mesh
derived from them is committed to this repository**; `out/` holds only
derived metadata for checking the proof. See [`NOTICE.md`](NOTICE.md) for
the full statement and the third-party software list. This project is not
affiliated with or endorsed by DJI or RoboMaster.

The code and documentation are dual-licensed under the MIT License
(`LICENSE-MIT`) or the Apache License 2.0 (`LICENSE-APACHE`), at your
option. CI (`.github/workflows/ci.yml`) runs fmt, clippy, tests, rustdoc
and a smoke test on Linux and macOS; tagging `v*` builds release binaries
for Linux and macOS (`release.yml`).
