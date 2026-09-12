# Split proof: per-product text-level split of the DJI RMUC STEP files

Date: 2026-09-10. Machine: this Mac (M3 Pro, 18 GiB). Tools: `python/*.py`
(Python 3.12 via `uv`, numpy, `cadquery-ocp` 8.0.1 for OCCT).

Result: the per-product text split preserves the source geometry. Both 1 GB files split into standalone
per-product STEP files in seconds to minutes, every geometry entity ends up in
exactly one part file byte for byte, OCCT reads each part in milliseconds to
seconds, and the per-part tessellation matches the 9 h whole-file glb.

This checks the split, not downstream export filters. The later
[geometry audit](geometry-audit.md) found and corrected omissions in the
element exporter.

## Contents

- [1. Pipeline](#1-pipeline)
- [2. Numbers](#2-numbers)
- [3. Facts learned about the files](#3-facts-learned-about-the-files)
- [4. Where things are](#4-where-things-are)
- [5. Rust implementation](#5-rust-implementation-same-day)
- [6. Next steps](#6-next-steps)

## 1. Pipeline

| Stage | Script | What it does |
|---|---|---|
| index | `p21index.py` | one parallel streaming pass; per entity: id, type, byte range, refs (numpy sidecar `.npz`) |
| model | `p21model.py` | products, PDM chain, assembly tree, representations, bodies, faces, styles (front side wins), vertex bbox |
| split | `p21split.py` | per product: forward closure of its shape definition + reverse-pulled styles and PDM boilerplate with filtered lists; writes byte ranges; `parts.json` manifest |
| validate | `validate_parts.py` | OCCT re-read of every part: face count, vertex bbox, effective face colours vs manifest; time and RSS; optional 1 mm / 0.35 rad mesh |
| glb | `compare_glb.py` | per-part triangle count and bbox vs `RMUC_full_xde/RMUC2026_full.glb` |
| coverage | scratch `coverage.py` | union of all part closures vs the source entity set |

## 2. Numbers

### Index (one pass, 11 cores)

| File | Entities | Refs | Types | Parse | Peak RSS |
|---|---|---|---|---|---|
| V2.0.0 (1.25 GB) | 7,011,285 | 96,452,865 | 86 | 5.0 s | 1.34 GB |
| V1.2.0 (0.99 GB) | 13,268,374 | 15,031,656 | 61 | 3.8 s | 1.21 GB |

`inspect` numbers reproduced exactly from the original handoff notes: V2.0.0 429 products,
446 occurrences, 803 bodies (773 solid, 23 with voids, 7 sheet), 157,610
faces, 278,482 styled items; V1.2.0 1,047 products, 1,071 occurrences,
79,247 bodies (1,187 + 32 + 78,028 sheet), 230,542 faces, 189,283 styled
items, 55 colours. RMUL: 749 grey-0.2 / 236 white / 44 green faces.

### Split (Python prototype, single process)

| File | Parts | Entities written | Output | Time | Peak RSS |
|---|---|---|---|---|---|
| V2.0.0 | 429 | 7,026,516 (1.00× source) | 1,256 MB | 214 s | 5.3 GB |
| V1.2.0 | 1,047 | 13,288,885 (1.00× source) | 995 MB | 33 s | 2.4 GB |

V2.0.0 time is dominated by re-filtering the 278 k-item presentation
representation and 3,848 layer lists per product; a Rust implementation
with a precomputed owner index removes that.

### Coverage (text-level losslessness)

| File | In exactly one part | In several parts (shared boilerplate) | In no part |
|---|---|---|---|
| V2.0.0 | 7,007,630 | 269 | 3,386 = 446 × 5 assembly links + 725 unreferenced `COLOUR_RGB` + 429 unreferenced `DIMENSIONAL_EXPONENTS` + 2 unreferenced predefined colours |
| V1.2.0 | 13,262,748 | 264 | 5,362 = 1,071 × 5 assembly links + 7 entities of one unreferenced colour chain |

The "assembly links" are `NEXT_ASSEMBLY_USAGE_OCCURRENCE`,
`CONTEXT_DEPENDENT_SHAPE_REPRESENTATION`, `ITEM_DEFINED_TRANSFORMATION`,
the transformation `REPRESENTATION_RELATIONSHIP` complex instance and the
occurrence's `PRODUCT_DEFINITION_SHAPE`; they belong in `assembly.stp`, not
in a part. Everything geometric is in exactly one part, verbatim. Only the
list-carrying boilerplate is re-emitted (V2.0.0: 8,137 rewritten entities
of 7 M; V1.2.0: product categories and the presentation representation).

### OCCT re-read of every part (STEPCAFControl_Reader, colours on)

| File | Parts | Read time, all parts | Median per part | Largest part | Peak RSS |
|---|---|---|---|---|---|
| V2.0.0 | 429 | 205 s | 3 ms | `26062900` 674 MB, 130 s, 4.5 GB | 4.5 GB |
| V1.2.0 | 1,047 | 117 s | 3 ms | `7000001_1_ASM` 334 MB, 28 s, 3.2 GB | 3.2 GB |

Against the whole-file run recorded in `RMUC2026_full_conversion.json`
(read 25 s, transfer 2.2 h, glb 6.8 h, 9 h total, ~40 GB RAM): every part
of V2.0.0 is imported and meshed in under 4 minutes total on this laptop.

Checks per part (see `validation.json` in each package):

- face count, vertex bounding box (exact points) and effective face colour
  histogram (face style, else shell style, else body style, front side of
  two-sided styles) equal the text-scan manifest for **1,045 of 1,047**
  V1.2.0 parts and **428 of 429** V2.0.0 parts;
- the remaining parts differ only on the OCCT side:
  - `001_1_ASM` (+6 faces), `7000001_1_ASM` (+1), `26062900` (+6): OCCT's
    shape healing splits a planar sheet face with many bounds into several
    faces; the new faces carry no colour (uncoloured count = extra faces + 1),
    the file itself has no multi-outer-bound faces and the closure holds all
    faces (`faces in closure == faces reached by bodies` was checked);
  - `26062900` (53,712 faces): 5,480 faces that get their dark grey
    `0.2471` through an `OPEN_SHELL` style inside a multi-shell
    `SHELL_BASED_SURFACE_MODEL` come back uncoloured from OCCT (the reader
    drops shell-level colours inside such bodies); the STEP text carries the
    colour and viewers that honour shell styles show it.

### Tessellation vs the 9 h glb (V2.0.0, 1 mm / 0.35 rad)

421 arena parts matched by name (`BREP_N`); the 8 equipment products are
named differently in the glb (`=>[0:1:1:426]` label names, Chinese names).

- triangle count ratio part/glb: median 1.000, 418/421 within ±10 %
  (glb was written by OCCT 7.8, parts meshed with 8.0.1; the three outliers
  are parts with 110–340 triangles);
- bounding boxes agree once the glb is read as metres, Z-up kept:
  399/421 within 1 mm, max 70 mm, where the mesh bbox on curved faces
  legitimately exceeds the vertex bbox.

## 3. Facts learned about the files

- Both files are CRLF (V2.0.0) / LF (V1.2.0); entity ids are not sorted in
  file order in V2.0.0 (`#324` first, PDM entities at the end).
- V2.0.0 uses two-sided face styles: one `STYLED_ITEM` with a `.POSITIVE.`
  and a `.NEGATIVE.` `SURFACE_STYLE_USAGE`; viewers show the positive side.
- V2.0.0 has 2,255 styles on `OPEN_SHELL` (sheet bodies of equipment) and
  795 `OVER_RIDING_STYLED_ITEM`s; V1.2.0 styles only faces and bodies and
  shares 55 `PRESENTATION_STYLE_ASSIGNMENT` chains between all 189 k items.
- V1.2.0 carries per-product material properties
  (`PROPERTY_DEFINITION` → `PROPERTY_DEFINITION_REPRESENTATION` →
  `REPRESENTATION('material name', …)`, density 7850 etc.).
- The reverse-referenced entity families that make a part file stand alone:
  styled items (key = target), `PROPERTY_DEFINITION[_REPRESENTATION]`,
  `APPLICATION_PROTOCOL_DEFINITION`, `PRODUCT_CATEGORY_RELATIONSHIP`,
  `APPROVAL_DATE_TIME`, `APPROVAL_PERSON_ORGANIZATION` (key-based), and the
  list carriers `PRODUCT_RELATED_PRODUCT_CATEGORY`,
  `PRESENTATION_LAYER_ASSIGNMENT`,
  `MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION`, `CC_DESIGN_*`
  (list filtered to the closure; dropped when empty).
- Trap hit: when re-closing a rewritten entity's references, skip its own
  `#id=` prefix, otherwise the closure re-expands through the original
  unfiltered list and pulls the whole file.
- Trap hit: reverse lookups must be per-owner slices of a flat reference
  array; scanning the flat array per hit owner made the first product take
  minutes.
- V2.0.0 equipment is flat: `26062900` (674 MB, 67 bodies), `0003`
  (137 MB, 160 bodies), `0006`, `000` ×2 are direct children of the root with
  no sub-assemblies. A per-body split is needed for these.
- Exporters differ: V2.0.0 and RMUL are Creo Parametric 2019164 exports
  (`CONFIG_CONTROL_DESIGN` + `SHAPE_APPEARANCE_LAYERS_GROUPS`, AP203 with
  the AP214 presentation entities); V1.2.0 is an Autodesk Translation
  Framework conversion from IGES written by ST-Developer (AP214).
- Colours (checked against OCCT XCAF on per-part reads and, for V2.0.0, the
  9 h whole-file glb): the effective colour is face > shell > body. V1.2.0
  puts a grey `Opaque(160,160,160)` style on every arena solid and a
  face-level style on every face (white, beige, red, navy, dark grey), so
  `body_colour` alone makes the arena look uniformly grey; use
  `face_colours`. V2.0.0 styles every arena face, body and edge curve with
  one shared cream `COLOUR_RGB('',1.,1.,0.949)` (`#320`); the arena has no
  other colour in the file. 725 of its 756 `COLOUR_RGB` entities are never
  referenced, including one blue-grey (0.438,0.503,0.6) written right
  after each arena body's placement, which looks like Creo emitting the
  body's own appearance and then styling with the appearance in effect at
  export. V2.0.0 has no per-instance styling (no styled `MAPPED_ITEM`,
  no `CONTEXT_DEPENDENT_OVER_RIDING_STYLED_ITEM`, no styled
  `SHAPE_REPRESENTATION`); V1.2.0 has no layers, overrides, mapped items
  or curve styles at all. Arena colour for a V2.0.0 package therefore has
  to come from V1.2.0 by matching, or from a palette file.
- V2.0.0 layers (`PRESENTATION_LAYER_ASSIGNMENT`, 3,848, 88 M refs) are the
  Creo component names (`0003_1_2`, `HOU_HANBAN_1`, …) and cover only
  equipment bodies; no arena body is on a layer.
- OCCT builds a `BREP_WITH_VOIDS` whose void shells are not enclosed as a
  compound of solids and puts the body colour on the compound.

### Previews

`python/mesh_parts.py <pkg> <index.npz> out.bin out.json [--lin 4 --ang 0.5
--min-face 0 --only a,b --arena-only]` (run in the OCP venv) tessellates every
part file with OCCT, resolves colour face > shell > body, places instances by
the assembly transforms (world = P(axis2) · P(axis1)⁻¹ from
`ITEM_DEFINED_TRANSFORMATION`), and writes a compact quantised bundle. The 3D
pages embed that bundle deflated: V2.0.0 683 k triangles / 7.0 MB page
(heavy equipment re-meshed at `--lin 8 --min-face 12`), V1.2.0 813 k
triangles / 8.6 MB page (equipment at `--lin 10 --min-face 15`, arena at 4 mm).
The page builder and template live in `python/preview/`; see `previews.md`.

## 4. Where things are

- Part files (2.2 GB, regenerable in 4 minutes) stay in the session
  scratch dir `pkg_v20/`, `pkg_v12/`, `pkg_rmul/`; the manifests and
  reports (`parts.json`, `validation.json`, `glb_compare.json`,
  `coverage.json`) land in `out/{v20,v12,rmul}/`, which is gitignored.
- Regenerate: `python3 python/p21index.py <stp> <out.npz>`,
  `python3 python/p21split.py <npz> <pkg_dir>` (source path is stored in the npz),
  `ocpenv/bin/python python/validate_parts.py <pkg_dir> [--mesh]`,
  `python3 python/compare_glb.py <pkg_dir> <glb>`,
  `python3 python/coverage.py <npz> <coverage.json>`.
- Index caches: `v20.npz` (568 MB), `v12.npz` (405 MB) in the scratch dir;
  5 s to rebuild.
- OCCT: `uv venv --python 3.12 ocpenv && uv pip install cadquery-ocp`
  (8.0.1.0.0) works on this Mac; OCP 8 renames: `TDF_LabelSequence` →
  `OCP.collections.Sequence_TDF_Label`, `TopTools_IndexedMapOfShape` →
  `OCP.collections.IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher`,
  `TopoDS.Face_s` → `TopoDS.Face`, shape-tool getters are `_s` statics.

## 5. Rust implementation (same day)

`crates/step21` + `crates/rm-map-tools` port the three Python stages.
`inspect` reproduces every number of the Python model on all three files
(entities, refs, types, products, occurrences, bodies by type, faces,
vertices, bbox, styled items by target type, distinct colours and names,
effective face-colour histogram; checked field by field against the JSON
dumps), and `split` writes part files that are **byte-identical** to the
validated Python output for all 1 + 1,047 + 429 parts (`cmp`), with the
same `parts.json` body statistics.

| Step | V2.0.0 (1.25 GB) | V1.2.0 (0.99 GB) |
|---|---|---|
| `index` (scan + sidecar write) | 1.3 s, 3.0 GB RSS | 1.1 s, 2.2 GB RSS |
| `inspect` from sidecar | 0.5 s, 1.4 GB | 0.7 s, 1.1 GB |
| `split` from sidecar, 11 threads | 8.4 s (reverse tables 2.5 s, parts 5 s), 3.6 GB | 2.7 s, 1.9 GB |

RSS includes the memory-mapped source pages. The V2.0.0 reverse table is
large because its 3,848 `PRESENTATION_LAYER_ASSIGNMENT`s reference 88 M
entities (91 % of all references in the file); it is built by counting
into CSR form rather than sorting pairs.

## 6. Next steps

1. Rust `split`: per-body split option for the flat V2.0.0 equipment
   products, `assembly.stp` from the "in no part" entities plus empty shape
   representations, package layout (`groups/`, `package.json`).
2. Package layout and rules (`groups.toml`, `palette.toml`) on top of the
   manifest: fingerprints are already in `parts.json` (bbox, face count,
   colours per body).
3. `match` V1.2.0 ↔ V2.0.0 arena bodies by fingerprint to transplant colours.
