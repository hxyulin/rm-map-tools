# HANDOFF: RoboMaster field CAD tooling

Written 2026-09-10 at the end of a session in `~/dev/RM/rm-simulator`. This
directory is the start of a new sibling project for turning the DJI RMUC
STEP releases into a reusable, grouped, coloured, losslessly split field
package that the simulators (`rm-simulator`, `Vision/rm-vision-sim`,
`Embedded`) and a game can consume.

Read this whole file first. It records what was measured, what was decided,
what to build first, and the traps already hit.

## 1. Goal

1. **Convert first.** Find a lossless, low-memory way to get the 1 GB DJI STEP
   into per-part files that any CAD kernel can load in seconds.
2. **Then the tool.** A small Rust CLI (`index`, `inspect`, `split`, `match`,
   `report`) with its own streaming STEP Part 21 scanner, kept as a
   standalone crate so it can be contributed upstream.
3. **Package layout** grouped by field element (ground, base, outpost, rune,
   dart, tech-core, walls), with a human-readable colour table and group
   rules so future DJI releases (which will be Creo exports without arena
   colour) can be repainted and regrouped by editing one file.

## 2. Source files and what is known about them

All paths are on this Mac (18 GiB RAM, M3 Pro, ~119 GiB free disk).
Everything under `~/dev/RM/assets` is a checksummed archive: **never edit or
commit those files**; new derived files go elsewhere and get their own
checksums.

| File | Size | Exporter | Notes |
|---|---|---|---|
| `~/dev/RM/assets/rm2026-cad/UTF-8__RMUC2026_V2.0.0.stp` | 1.25 GB | Creo Parametric 2019 (AP203 + SHAPE_APPEARANCE_LAYERS_GROUPS) | 7,011,285 entities, 429 products, 446 occurrences, 803 bodies, 157,610 faces. Current simulator source. **Arena has no colour** (see §3). sha256 `8dfe9ebd…ae33` in `download-verification.json`. |
| `~/dev/RM/assets/rm2026-cad/UTF-8__RMUC2026_V1.2.0.step` | 993 MB | ST-Developer v20.1 from Autodesk Translation Framework (AP214), source `rmuc2026__0001_asm_1230_igs_stp`, 2025-12-30 | 1,047 products, 1,071 occurrences, 79,247 bodies (1,187 solids + 32 BREP_WITH_VOIDS + 78,028 single-face sheet bodies), 230,542 faces, 189,283 styled items, 55 named colours `Opaque(r,g,b)`. **Arena is fully coloured.** Archived 2026-09-10, sha256 `90daa72d…54a23` in `download-verification.json`. |
| `~/dev/RM/assets/rm2026-cad/UTF-8__RMUL2026.stp` | 1.7 MB | Creo, same author | League arena, one BREP_WITH_VOIDS: 749 dark-grey (0.2) floor faces over 12.6 × 8.6 m, 236 `'white'` markings, 44 `'green'`, red/blue accents. Proves the Creo exporter keeps floor colour when the model has it. |
| `~/dev/RM/assets/rm2026-cad/UTF-8__能量单元.stp` | 842 KB | Creo, same author | Rune unit, 0.42 grey with white faces. Archived 2026-09-10, sha256 `35d105a2…5de7`. |
| `~/dev/RM/assets/rm2026-cad/RMUC_full_xde/` | | OCCT XDE run on `home_m5_max` | `RMUC2026_full.glb` (455 mesh nodes, 37 materials, 1 mm / 0.35 rad deflection), `.xbf`, `_conversion.json`: read 25 s, transfer 2.2 h, glb write 6.8 h, **9 h total** for the whole V2.0.0 file. The user reports ~40 GB RAM for such whole-file imports. |
| `~/dev/RM/assets/rm2026-cad/RMUC_processing_models/` | | earlier attempt | 16 filtered STEP batches + `RMUC_solids_only.stp`, `RMUC_filtered_surfaces_ge_5mm.stp`. An earlier text-level split; look at `manifest.json` and `batch_001_validation.json` before designing the new one. |
| `~/dev/RM/assets/rm2026-cad/RMUC_assembly_structure.json` | | | V2.0.0 product tree: root `00_RMUC2026_FINALS_ASM`, 26 children; `DOCUMENT_A_ASM` holds the 420 anonymous arena bodies `BREP_N`. |
| `~/dev/RM/assets/rm2026-extracted/`, `rm2026-equipment-extracted/` | | | What `rm-simulator` loads today (manifests with sha256, glb visuals, `*-collision.glb` proxies). Extraction dropped the dart silo (飞镖发射井), resource zone (资源区) and HANDAO parts. |
| `~/dev/RM/assets/rm2026-cad/RMUC_GLTF_SCENE_RECOMMENDATIONS.md` | | | Earlier notes on a runtime-oriented glTF naming scheme used by `at_vision_simulator` (state variants as named nodes). Worth reusing for the LOD/glTF outputs. |

### Colour findings (measured, not inferred)

- **V2.0.0**: every arena body (420 `BREP_N` under `DOCUMENT_A_ASM`) is the
  exporter cream `COLOUR_RGB('',1,1,0.949)` at solid, shell and face level;
  no overrides on arena products; layers carry no colour; 421 slate-grey
  `COLOUR_RGB` entities are unreferenced Creo defaults. 310 bodies carry
  non-cream colour and all belong to equipment; the widest is 2.95 m (rune).
  Cause: the arena was imported into Creo from the Autodesk model and the
  import dropped face colours. **No re-export of V2.0.0 can add colour.**
  Re-verified 2026-09-10 with OCCT on every split part and against the 9 h
  whole-file glb (all 424 arena nodes one material); the 725 unreferenced
  `COLOUR_RGB` entities include one blue-grey written right after each
  arena body's placement, consistent with Creo emitting the body's own
  appearance and then styling with the appearance in effect at export.
  Full analysis in `docs/step-notes.md` §4.
- **V1.2.0** arena (`BREP_N_1` products, 353): floor `BREP_1128_0001_1`
  29.05 × 16.05 × 0.2 m, only its top face styled `Opaque(51,51,51)`, other
  faces inherit the body default `Opaque(160,160,160)`; terrain plates
  (e.g. `BREP_215_1`, `BREP_225_1`, 11.1 × 5.1 × 0.6 m) have
  `Opaque(65,65,65)` tops and `Opaque(200,200,180)` sides; 24 red
  `Opaque(255,7,7)` and 24 blue `Opaque(17,1,151)` 1 mm marking sheets
  (largest 9.1 × 4.3 m); 228 white `Opaque(255,255,255)` marking/lettering
  sheets plus 28 small white solids. Equipment mostly `Opaque(51,51,51)`,
  `(63,63,63)`, `(107,107,107)` with red/blue/yellow/pink accents.
- Colour mechanism in both files: `STYLED_ITEM` / `OVER_RIDING_STYLED_ITEM`
  → `PRESENTATION_STYLE_ASSIGNMENT` → `SURFACE_STYLE_USAGE` →
  `SURFACE_SIDE_STYLE` → `SURFACE_STYLE_FILL_AREA` → `FILL_AREA_STYLE` →
  `FILL_AREA_STYLE_COLOUR` → `COLOUR_RGB` | `DRAUGHTING_PRE_DEFINED_COLOUR`.
  `CURVE_STYLE` entries are edge colours. Styles reference the geometry
  (face/shell/solid), never the reverse. In `OVER_RIDING_STYLED_ITEM` the
  target is the second-to-last reference. Face style beats shell beats
  solid.

### Hierarchy findings

- V2.0.0: flat. Root with 26 children; arena bodies anonymous.
- V1.2.0: real tree. Root → `rmuc2026__0001_asm_1230_igs` →
  `RMUC2026__0001_ASM_1_ASM` (13 children: `0006_1_ASM` 49 children,
  `0007_1_ASM` 159, `0009_1_ASM` ×2 42, `001_1_ASM` ×2 66, `0013_1_ASM` ×2
  190, `0008_1` ×2, `0010_1` ×2, `ID_V1_202509280001_ASM_1_ASM`) plus
  `0001_ASM` ×2 → `7000001_1_ASM` (152 children). Duplicated sub-assemblies
  are true instances (same product, two transforms), so geometry must be
  stored once and instanced.
- `7000001_1_ASM` carries 38,001 single-face sheet bodies directly;
  `0013_1_ASM` 17,135; `001_1_ASM` 11,685. Per-product files for these will
  be large; support an optional per-body split.

## 3. Decisions taken

1. **Split at text level, no kernel.** Copy entity text byte for byte into
   per-part files. Zero fidelity loss by construction, bounded memory,
   original entity ids preserved for traceability.
2. **STEP stays the archive; the package is derived.** Never edit the DJI
   file. Package = scene JSON + rules + per-part STEP + report. XBF only as a
   private cache. Tessellated formats (glTF/USD) are LOD outputs, never the
   master.
3. **Groups are semantic, placement is in the tree.** `groups/base/` holds
   one geometry set; red and blue placements are instances in
   `assembly.json`.
4. **Colours keyed by role and geometric fingerprint, not by name.** Body
   names do not survive Creo re-export (`BREP_N` renumbered; 353 arena
   bodies in V1.2.0 vs 420 in V2.0.0). Fingerprint = rounded bounding box
   (from vertex points), centroid in arena frame, face count, surface-type
   histogram. Two layers: exact fingerprint entries harvested from V1.2.0,
   then class rules (floor top, plate top, thin sheet red/blue by field
   half, white otherwise). Human-editable `palette.toml` (role → RGB with
   provenance comment) and `groups.toml` (name/fingerprint → group with
   location comment); compiled into JSON for consumers.
5. **Rust CLI with its own streaming Part 21 scanner**, kept as a separate
   crate with a public API so it can be contributed (candidates:
   `ruststep`, which parses Part 21 with `nom` into typed AP203 structs and
   loads whole files; `truck`, a Rust kernel with partial STEP I/O). Verify
   the current state of both before claiming a gap.
6. **Tessellation/LOD/collision stay outside the Rust tool** for now: run
   OCCT (Python OCP or C++) per part file. Not installed on this Mac
   (`import OCP` fails, no FreeCAD). The `rm-simulator` repo already has
   collision simplification logic (`crates/rm-simulator-app/src/terrain.rs`)
   that should eventually move into the tool so all consumers share it.

## 4. Target package layout

```
rmuc2026-v2.0.0/
  package.json          version, source file + sha256, tool version, units (mm), frame
  assembly.json         instance tree: node -> group/part, 4x4 transform, children
  assembly.stp          structure-only STEP (tree + transforms, empty shapes)
  report.md             every body: group, part, role, colour, size, classification source
  groups/
    ground/  group.json  floor.stp  plates/*.stp  markings/{red,blue,white}-NN.stp
    base/  outpost/  rune/  dart/  tech-core/  walls/
    unassigned/         anything rules could not place; report.md says why
  rules/
    groups.toml         hand-curated name/fingerprint -> group/part, with comments
    palette.toml        role -> RGB, with provenance
```

Part file naming: sanitised product name + original entity id, e.g.
`BREP_9-14249.stp`. Frame: DJI STEP is mm, Z-up arena frame; simulators
convert to metres FLU themselves.

## 5. CLI design

| Command | Does |
|---|---|
| `index <step>` | one streaming pass; sidecar index of (id, type, byte range, refs) — done, `<file>.p21idx`, ~1 s/GB |
| `inspect <step>` | tree, products, colour summary, body table (must reproduce §2 numbers) — done, `--json` dumps everything |
| `split <step> --rules rules/ --out pkg/` | closure per part + its styles, writes the layout — per-product split and `parts.json` done; rules/layout not yet |
| `match <pkg-a> <pkg-b>` | fingerprint matching across releases; colour/group transplant candidates |
| `report <pkg>` | regenerates `report.md` |

### Scanner requirements (all hit in practice)

- Entities wrap across lines; `#id=` may start a line and `;` end it many
  lines later. Buffer until `;` outside a string.
- Complex instances `#id=(A(...)B(...)C(...));` have no single type name.
- Strings contain `\X2\…\X0\` escapes (Chinese product names in V2.0.0),
  and may contain `;`, `(`, `#`. Tokenise strings properly; do not regex
  `#\d+` inside strings.
- `/* … */` comments appear in the V1.2.0 header.
- Entity ids are not contiguous; V1.2.0 ids reach 13,268,383.
- Ownership of a body: `SHAPE_DEFINITION_REPRESENTATION` →
  `PRODUCT_DEFINITION_SHAPE` → `PRODUCT_DEFINITION` →
  `PRODUCT_DEFINITION_FORMATION[_WITH_SPECIFIED_SOURCE]` → `PRODUCT`; and
  `SHAPE_REPRESENTATION_RELATIONSHIP` links extra representations
  (`MANIFOLD_SURFACE_SHAPE_REPRESENTATION` for sheet bodies) to the same
  product. Representation types to treat as body containers:
  `ADVANCED_BREP_SHAPE_REPRESENTATION`, `MANIFOLD_SURFACE_SHAPE_REPRESENTATION`,
  `SHAPE_REPRESENTATION`, and complex instances.
- Traversal from `ADVANCED_FACE`: drop only the last reference (the
  surface); the bug of dropping two lost the outer bound on single-bound
  faces and made every planar body look tiny.
- Per-part closure must also pull the unit/context entities
  (`GEOMETRIC_REPRESENTATION_CONTEXT` complex instance, units,
  `APPLICATION_CONTEXT`, `PRODUCT_CONTEXT`, category, PDM boilerplate) so
  the file stands alone, plus a fresh
  `MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION` listing only
  that part's styled items, and filtered `PRESENTATION_LAYER_ASSIGNMENT`.

## 6. First task: prove the conversion

**Status 2026-09-10: steps 1–4 done, see `docs/split-proof.md`.** V1.2.0
and the rune file are archived with checksums; `prototype/p21index.py`,
`p21model.py`, `p21split.py` split both files by product (V2.0.0: 429
parts in 214 s / 5.3 GB RSS; V1.2.0: 1,047 parts in 33 s / 2.4 GB); every
geometry entity lands in exactly one part verbatim (coverage check); OCCT
8.0.1 (`cadquery-ocp` in a uv venv, runs on this Mac) re-reads all parts
in 205 s / 117 s with face count, bbox and effective face colours equal to
the text scan except three OCCT-side healing splits and dropped
`OPEN_SHELL` colours in `26062900`; per-part 1 mm meshes match the 9 h glb
(median triangle ratio 1.000). Reports in `out/`. Step 5 is started: the
Rust workspace (`crates/step21`, `crates/rm-map-tools`) has `index`,
`inspect` (reproduces the §2 numbers on all files) and `split` (byte-identical
to the validated Python parts; 3 s for V1.2.0, 8 s for V2.0.0). Both files
have been meshed from their split parts with OCCT and published as 3D
pages (`docs/previews.md`), which also settled the colour question: the
V2.0.0 arena is cream in the data itself, V1.2.0 colours live on faces
(`docs/step-notes.md` §4). Documentation set: `README.md`,
`docs/architecture.md`, `docs/step-notes.md`, `docs/previews.md`,
`docs/split-proof.md`. Missing: per-body split, `assembly.stp`, package
layout, `match`, `report`.

1. Move V1.2.0 into the assets archive with a checksum.
2. Prototype the split (Python is fine for the proof; `prototype/` holds
   the scanners used so far). Split V2.0.0 and V1.2.0 by product.
3. Validate losslessness per part with any OCCT (on the RTX machine or a
   container if not installed here): face count, bounding box and colour
   set of each part equal the text-scan numbers, and for V2.0.0 the
   per-part tessellations at 1 mm / 0.35 rad match the existing
   `RMUC2026_full.glb` node meshes (vertex-count and bbox within tolerance).
4. Time and RSS of per-part import vs the 9 h / ~40 GB whole-file run.
5. Only then start the Rust crate; `inspect` must reproduce the numbers in
   §2 on both files before `split` is written.

## 7. Memory budget

| Step | Expected peak | Fits 18 GiB Mac? |
|---|---|---|
| Python text scan holding ~3.8 M non-geometry entities + 667 k points (as done) | a few GB | yes, ran here |
| Rust streaming index (13 M entities, ~40 M refs, mmap) | 0.5–1 GB | yes |
| Text split (closure bitset + copying byte ranges) | < 1 GB above index | yes |
| Per-part OCCT import + tessellation | hundreds of MB, seconds | yes, once OCCT is installed |
| Whole-file OCCT import of V2.0.0 or V1.2.0 | ~40 GB, hours | **no**; not needed after the split, only for a one-time cross-check, and that cross-check already exists for V2.0.0 as `RMUC2026_full.glb` |

## 8. Prototype scripts in `prototype/`

- `p21index.py <stp> <npz>`: parallel streaming Part 21 index (ids, types,
  byte ranges, refs) as a numpy sidecar; 5 s per 1 GB file.
- `p21model.py`: product/PDM/assembly/body/style model over the index;
  reproduces the §2 numbers (`Model(Index(npz))`).
- `p21split.py <npz> <pkg_dir>`: per-product split with reverse-pulled
  styles and filtered boilerplate lists; writes `parts/*.stp` and
  `parts.json` (per-body faces, colours, bbox fingerprints).
- `validate_parts.py <pkg_dir> [--mesh]` (needs the OCP venv),
  `compare_glb.py <pkg_dir> <glb>`, `coverage.py <npz> <json>`: the
  losslessness checks described in `docs/split-proof.md`.
- `mesh_parts.py <pkg> <npz> out.bin out.json [--lin --ang --min-face
  --only --arena-only]` (OCP venv): tessellates every part, resolves
  colour face > shell > body, places instances by the assembly transforms
  and writes a compact mesh bundle; `preview/build_viewer.py <cfg.json>
  <bundle>[:arena] …` turns bundles into the self-contained 3D page from
  `preview/viewer_tpl.html`. See `docs/previews.md`.

- `stepscan.py <file>`: per-solid colour table for small Creo files (RMUL,
  rune). Note its face traversal predates the fix in §5 and is only used for
  colour counting.
- `v12scan.py`: the full V1.2.0 scan (two passes, skips pure-geometry
  entity types, loads only vertex points, writes `v12_bodies.json` with
  per-body product, body colour, face-colour histogram and bbox in
  part-local mm). Output of the last run: `v12_scan_output.txt`. Adapting
  the `path` variable runs it on V2.0.0 too.

## 9. Constraints carried over

- Never modify or commit anything under `~/dev/RM/assets`.
- Do not ssh to `home_rtx5090` (100.100.176.102) unless the user asks; it
  timed out and the user said to stop.
- `rm-simulator` rules that this tool will feed: metres FLU, playing floor
  top at height zero, floor slab crowned (about 0.11 m below reference on
  the centre line, 0.32 m at the side walls), markings are flush thin
  solids, collision proxies simplified per part. See its `AGENTS.md`.
- Commit attribution for this user's sessions ends with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## 10. Open questions

- Where does the whole-field `assembly.stp` get its transforms for V2.0.0's
  flat arena: keep them flat under a synthetic `ground` node, or place each
  body under its zone node? (Proposal: zone nodes, identity transforms.)
- Per-body vs per-product split threshold for the sheet-heavy V1.2.0
  sub-assemblies, and for V2.0.0's flat equipment products (`26062900` is
  a single 674 MB / 67-body product that takes OCCT 130 s and 4.5 GB).
- Whether V1.2.0 or V2.0.0 is the geometry master for the simulator once
  colours can be transplanted either way (needs a geometry diff between the
  two; expect small arena edits).
