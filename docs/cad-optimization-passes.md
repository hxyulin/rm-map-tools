<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Source CAD optimization passes

Start with the original STEP model, before tessellation or mesh reduction.
`python/audit_cad_passes.py` runs registered discovery passes on a shared
in-memory document and writes a small findings JSON
report. It never writes CAD, meshes, installed packages, or an executable change
plan. The source STEP and any supplied index hashes are checked before and after the run.
Reports use source hash plus entity IDs, rather than selectors on an already
simplified triangle mesh.

## In-memory document and language boundary

`python/cad_document.py` provides `CadDocument`. It accepts original STEP
through `from_step()` and builds its parser index **in memory**. `from_index()`
accepts an optional existing `.npz` cache. A serialized intermediate catalog is
not required, and no metadata archive or field-package copy is produced.

The library defaults to serial indexing, which also works interactively. For
multiprocessing, use an importable script with the usual `__main__` guard; the
CLI handles that and defaults to four workers.

The document keeps three related views:

- **Exact source graph:** read-only mapped STEP bytes, entity IDs, reference
  arrays and decoded strings. `entity(id)` and `entities(type)` lazily expose any
  source family, including units, tolerances, layers, material/property values,
  front/back style records and information the typed model does not interpret.
  Huge layer membership lists are views into the index, not duplicated JSON.
- **Typed assembly/ownership model:** products, bodies, representations, styles
  and explicit source placements. Occurrence paths stay separate from shared
  definitions; names do not become identities. `subtree()` retains coincident
  instances and rejects missing placements or cycles.
- **Native mutable working model:** `working_model()` lazily imports original
  STEP into OCCT XCAF and retains the transfer reader. Geometry passes can use
  native B-reps and XCAF labels, assemblies, names, colors, layers and other
  supported metadata. Source-only discovery does not load this model. Import
  can heal/split faces, so OCCT ordinals are not assumed to be STEP face IDs.

The reader enables available Color, Name, Layer, Props, Mat, GDT, SHUO, View,
Meta and ProductMeta modes. Its capability record says which modes exist in
this OCCT build; it does not assert that every STEP entity transferred. Original
records remain available even when OCCT cannot represent their meaning. Source
units remain separate from any normalization performed by native CAD transfer.

Python currently owns pass orchestration and queries; OCCT performs native
geometry work. Existing Rust scanning, indexing, splitting and reference
validation remain useful. The direct Python loader is already available; a
future Rust-backed loader can implement the same document boundary. Move
measured parsing/fingerprinting bottlenecks to Rust when profiling justifies it,
without rewriting CAD algorithms or introducing a Rust CAD binding dependency.

```python
from cad_document import CadDocument
from audit_cad_passes import run_document
from export_elements import Package

with CadDocument.from_step('source/RMUC2027_V1.0.0.stp') as cad:
    findings = run_document(cad, ['assembly-reuse', 'exact-body-reuse'])
    # Existing geometry exporters can reuse the same source/assembly context.
    package = Package('out/rm2027/RMUC2027_V1.0.0/split', document=cad)
    # Only a pass needing geometry requests cad.working_model().
```

The production tessellation adapter still reads split STEP parts; it is not yet
an exporter of edited native working-model shapes. Discovery and native import
can already process STEP directly. This foundation does not claim a completed
mutable CAD-to-runtime pipeline or exact mesh-to-original-face correspondence.

## Run the initial passes

Use the existing CAD Python environment. Importing the placement reader loads
OCCT bindings, but this runner does not import shapes into OCCT, heal, mesh or
refit them.

```sh
ocpenv/bin/python python/audit_cad_passes.py --list-passes
ocpenv/bin/python python/audit_cad_passes.py \
  source/RMUC2027_V1.0.0.stp \
  --source-sha256 a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0 \
  --out out/cad-audit/rmuc2027.json
```

A STEP input builds no on-disk index; `--workers` defaults to four. An optional
index must refer to the original source file. Report paths must be new;
existing paths are refused. `--passes assembly-reuse` or
`--passes exact-body-reuse` selects a subset. The registry records each pass's
version, effect and description; this runner admits only `read-only` effects.
Producer hashes identify the Python implementations used.

| Pass | Evidence | What remains unresolved |
| --- | --- | --- |
| `semantic-evidence` | Exact assembly ownership, occurrence labels, layer membership/overlap, appearance families and motion-type records | Body motion and physical/decoration roles stay unknown; names are review hints |
| `assembly-reuse` | Existing product identity, complete occurrence paths and source world matrices | Whether downstream exports already share those definitions; face/occurrence style and semantic handling |
| `exact-body-reuse` | Identical ordered STEP geometry graph after substituting reference hashes and ignoring entity display names/comments/whitespace | Appearance, semantic ownership and export sharing; equivalent shapes encoded differently are deliberately missed |

The graph pass reuses `GeometryFingerprints` from
`audit_geometry_duplicates.py`. Coordinates, numeric spellings, curve/surface
parameters, trims, topology ordering and orientation must agree. No coordinate
rounding, frame fitting or mirror equivalence enters its acceptance rule.
Existing `audit_body_symmetry.py` is a separate **candidate discovery** tool:
its normalized/quantized hashes are not exact-geometry certificates.

Repeated assembly counts include parents and children. Do not sum them as
independent savings. Missing explicit placement data, reflections and non-rigid
transforms are reported instead of becoming invented identity placements;
assembly cycles fail. Unvisited representation-owning products are listed.
Body graph failures are listed as skipped, not silently counted as inspected.

## RMUC 2027 initial evidence

For the source hash above:

- 49 product definitions visited, 85 placed product occurrences.
- 18 repeated products, with 36 additional product occurrences. The largest
  repeated definitions are product **4056216**, placed 12 times, and
  **2717102**, placed 10 times. Existing exporter instancing may already account
  for this reuse.
- 426 body definitions successfully hashed, 424 distinct geometry fingerprints,
  two exact duplicate pairs, no skipped bodies.
- Body **24444** (product **24844**) matches **3786822** (product **3797438**).
  Body **24644** (product **24844**) matches **3808637** (product **3813260**).
  These are geometry identities; this audit has not proved appearance or
  collision-ownership equivalence and does not remove either occurrence.
- No missing/non-rigid occurrence placements in this run. Source and index
  bytes were unchanged.

These numbers measure source definitions, not mesh triangles, GPU draws or
unique physical contacts. Sharing a definition can reduce source/export size,
tessellation work and mesh upload/storage. It does **not** reduce placed
triangle count or permit dropping repeated collision shapes.

## Applied lossless representation passes

`python/cad_passes.py` adds two passes over `CadScene`, a derived in-memory
reference graph owned by an open `CadDocument`. These are distinct from the
read-only audit registry above. They change sharing in a new scene, while the
input scene, original STEP, native XCAF model and runtime assets remain intact.
They do not consume edits made separately to the native XCAF working model.

- **`share-exact-geometry`:** identical ordered B-rep graphs share one geometry
  definition. Source names/IDs, product ownership, all body occurrences and
  their exact placements remain separate. Every shared body needs a bijective
  original-STEP face correspondence. Face maps are scoped by source body, so a
  face used by several bodies cannot accidentally inherit another body's map.
  Appearance remains attached to original source entities.
- **`share-exact-appearance`:** identical presentation-assignment graphs share
  one definition. Unlike the geometric matcher, this pass preserves **all
  literal strings**, including color/style names. Numeric spellings, front/back
  usage, topology/reference order and other parameters must agree. Original
  style records, targets, overrides and binding order remain separate.

Planning and applying are separate operations. A frozen `PassPlan` pins the
source hash and scene revision and holds exact graph/face evidence. Application
rechecks each redirect and returns a new `CadScene` only after validation;
wrong-source, stale or inconsistent plans fail without partially changing the
input. Applying the same pass again discovers no additional redirects.
Unresolved/cyclic graphs and non-bijective geometry candidates are retained and
reported as skipped, rather than treated as matches.

```python
from cad_document import CadDocument
from cad_passes import CadScene, plan_pass, apply_plan, validate_equivalence

with CadDocument.from_step('source/RMUC2027_V1.0.0.stp') as cad:
    original = scene = CadScene(cad)
    for name in ('share-exact-geometry', 'share-exact-appearance'):
        plan = plan_pass(scene, name)
        scene = apply_plan(scene, plan)
    checked = validate_equivalence(original, scene)
    # scene.occurrences() exposes shared geometry plus original body identities.
    # scene.style_bindings() resolves shared assignments, retaining source targets.
```

The CLI plans by default. `--apply` changes **only the derived scene in memory**;
`--out` writes a small findings/validation report with at most twenty examples
per pass, not a serialized scene or another field package:

```sh
ocpenv/bin/python python/cad_passes.py source/RMUC2027_V1.0.0.stp \
  --source-sha256 a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0 \
  --apply --out out/cad-audit/rmuc2027-sharing.json
```

An existing `.npz` parser index is also accepted. The RMUC run produced:

- Geometry definitions **426 → 424**, with twelve original face correspondences.
- Presentation assignment definitions **178,874 → 103**. This does not claim
  the whole internal style graph has been garbage-collected or compressed.
- **644 placed body occurrences** retained with exact source identities and
  matrices; **178,874 style bindings** retained with the same targets and exact
  referenced appearance graphs. Both passes had zero skipped candidates.
- Original source bytes unchanged. The local evidence report is
  `local-assets/cad-audit/rmuc2027-sharing-final.json` in the simulator checkout.

`validate_equivalence()` checks every placed body and style binding across the
composed passes, plus changed geometry/appearance graph references and source
face mappings. This is a validation of the derived source-reference scene, not
a claim that a newly exported STEP or mesh was validated. No triangles, contacts
or silhouettes are removed. Tessellating/exporting canonical body definitions
with per-occurrence source appearance remains the next adapter step; existing
runtime packages do not yet benefit from this sharing.

## RMUC 2027 presentation layers and pass ordering

A follow-up read-only inventory of the same source hash found **3,674**
`PRESENTATION_LAYER_ASSIGNMENT` records, each with a distinct name and an empty
description. Names include 109 `COLOR<number>` variants and 3,565 other names,
mostly component-style identifiers. Examples include `BJDOOR-3`,
`ARMOR_LIGHT_GUIDE_STRIP-V1_1`, `LED_4-1P6X1P6-0P7` and
`LIGHT_ARMOR_BACK_SHELL`. Names are source hints, not reviewed semantic roles.

The assignments contain **38,868,002 references**, including 38,480,666 face
references. They cover 105,522 of 110,586 source faces; 102,370 faces appear in
multiple layers. Among covered faces, the median layer count is 210 and the
maximum is 1,409. These are overlapping presentation assignments, not a partition
into physical parts, paint and equipment. All nine shell-based surface bodies
have no direct layer membership; absence from a layer does not mean removable.

There are only **259 distinct membership lists**, even preserving reference
order and multiplicity. Hash candidates were checked with exact array equality:
3,415 duplicate lists match, and the canonical lists contain 1,523,117 references
instead of processing all 38,868,002 for each derived membership operation. One list is reused by 1,408 differently named layers.
For example, the two layers `ARMOR_LIGHT_GUIDE_STRIP-V1_1` and
`LED_4-1P6X1P6-0P7` each target the same 17,754 entities, including 17,660 faces.
That layer name cannot safely identify just an armor light or LED.

**Next lossless source pass:** intern identical membership lists, preserving all
3,674 layer records, their names, descriptions, IDs and original memberships.
This can reduce derived metadata duplication without treating layers as
visibility, material, motion or collision instructions. It is a measured
opportunity, not an implemented pass. The simulator checkout holds the compact
inventories `local-assets/cad-audit/layers-probe.json` and `layer-coverage.json`;
no large membership catalog or geometry package was generated.

Keep pass stages explicit:

1. **Import and inventory.** Pin source, units, ownership, assembly occurrences,
   source metadata and transfer limitations. Preserve unrecognized entities.
2. **Source representation sharing.** Exact geometry and presentation sharing,
   then exact layer-membership sharing. Keep original identities and contexts.
3. **Export canonical definitions.** Tessellate shared B-reps once per effective
   settings/appearance variant; retain source-face correspondence. Geometry
   instancing and per-occurrence styles must survive this boundary.
4. **Mesh representation packing.** Deduplicate only complete identical vertex
   records; share buffers and fully identical materials; concatenate compatible
   primitives without changing expanded triangle attributes or winding.
5. **Optional geometry/topology changes.** Retriangulation, CAD face coalescing,
   Boolean union, internal-face removal, primitive fitting and coarser
   tessellation need separate invariants and validation. A shape-exact change
   can still alter face identity, normal/UV interpolation or physical contacts.
6. **Validate and export.** Check the invariants of each pass and then the
   composed result, including source IDs, occurrences, styles and colliders.

Each pass should declare its input stage, preconditions, effect, protected
boundaries and validation, and return an inspectable source/revision-bound plan.
Keep the input scene available; apply atomically to a new derived scene. Report
stored-definition/vertex/buffer counts separately from placed triangles and draw
primitives so a storage optimization is not mislabeled a geometry reduction.

### Exact mesh combining

Concatenating existing triangle buffers can preserve geometry exactly. Start
with meshes in the **same coordinate frame**, with identical full material and
render state, compatible attribute layouts and the same rigid-motion owner.
Keep source triangle ranges as provenance. Validate expanded position, normal,
UV, tangent and other vertex attributes and winding exactly, not just bounds.
Triangle count remains the same; the possible gain is fewer primitives/draws.

Keep independently moving parts, runtime-controlled surfaces, collision/scoring
owners and useful culling regions separate. Source layers alone do not establish
these boundaries. Prefer instancing for repeated geometry; baking its copies
into one merged mesh duplicates vertices and can undo the earlier sharing.
Transform baking also introduces floating-point conversions, so it should not
be included in the first bit-exact concatenation pass.

Full-record vertex indexing and identical mesh sharing already exist in parts of
the GLB writer. Measure what the complete export path preserves before adding a
second implementation. Deduplicating positions alone can erase hard normals or
UV seams; merging by RGB alone can erase alpha, texture or sidedness differences.
CAD Boolean fusion is a different operation from mesh-buffer concatenation and
should not be assumed lossless because its inputs touch or look coplanar.

## Next infrastructure stages

1. **Trace reuse through each boundary.** Compare source definition/occurrence
   counts, exported mesh/accessor sharing, runtime mesh handles and placed
   geometry. Attribute lost sharing to a specific conversion rather than
   assuming every repeated CAD product is a new optimization.
2. **Build a source-owned sharing plan.** Reference canonical B-reps plus exact
   placements and separate appearance/semantic variants. Keep all source IDs,
   per-face colors, independently moving links, detector bindings and collider
   ownership. Use an intermediate CAD scene graph; rewriting STEP as
   `MAPPED_ITEM` requires reader/exporter support that is not yet established.
3. **Validate before applying representation changes.** Exact graph matches can
   share geometry while preserving those separate attributes. Differently
   encoded or rigidly moved bodies need candidate correspondence followed by
   CAD-level equivalence checks. Bounding boxes, volume equality, sampled
   meshes and rounded hashes alone are insufficient, especially for sheets,
   cavities and scoring surfaces.
4. **Keep lossy passes separate.** Defeaturing, filling holes, changing outlines,
   fitting approximate primitives, artwork rasterization and coarser
   tessellation require their own policies and evidence. They are not part of
   this initial runner. Even healing can change a shape and is excluded.

The document supplies a native working model and the two derived-scene sharing
passes above. Native geometric edits and export of the shared scene remain
unimplemented. Keep those stages separate from source discovery;
keep the original CAD immutable. Store small, content-addressed reports keyed
by source/index, pass versions/configuration and producer hashes. Reuse canonical
CAD and tessellation caches instead of copying whole field packages for every
experiment. Preserve a runtime baseline until the replacement pipeline is
validated.


## Semantic evidence pass (RMUC 2027)

`--passes semantic-evidence` inventories the source without importing native
shapes. It retains all product/occurrence strings (important: useful Chinese
labels live on assembly occurrences, while product identifiers are abbreviated),
source body ownership, layer names/descriptions, exact membership groups and
body/face coverage. Exact ordered lists are verified after hash grouping; each
unique list is analyzed once. Unresolved references are counted. Source type
counts and explicit motion-family records include complex STEP entities.
Geometrical surfaces of revolution and mechanical product contexts are not
motion records. Curves, shells and styled-item ownership are not guessed into
body coverage.

On source `a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0`:

- 49 product definitions, 84 assembly occurrence edges, 426 body definitions.
  These are CAD entities; occurrence edges are not the recursively expanded
  placed-body count and do not establish gameplay entities by themselves.
- No explicit motion-family records found. This does **not** establish that
  every body is fixed. All motion assignments remain unknown.
- 3,674 layers, 259 distinct ordered membership lists, no descriptions.
  102,370 of 110,586 source faces belong to multiple layers. There are 109
  colour-named layers, 30 lighting name hints and three equipment name hints;
  categories may overlap. No motion, fixed-structure, terrain or decoration
  name hints were found on layers with the current documented keyword rules.
- Lighting-named layers share a 17,754-target membership containing 42 bodies
  owned by outpost product #2603236. These are not individual light-strip masks.
  `LIGHT_ARMOR_BACK_SHELL` refers to 733 faces plus one styled item within
  base product #4774244; its name does not justify suppressing collisions.
- The source has colour/style metadata, including 59,685 styled face targets,
  but no material, texture or transparency entity types and no layer whose
  targets consist entirely of appearance records.
- Occurrence labels identify the floor, central highland, rune, outpost,
  dart stations, fans, resource areas, fortresses and base. For example,
  occurrence #24852 labels product #24844 `战场大地面_带丝印`; #1782087
  labels product #1782082 `中央高地_地面带丝印`. These are combined structural
  and screen-printed assemblies, not separately identified paint geometry.

The report separates exact assembly membership, name hints, appearance metadata
and unknown runtime roles. An appearance-only target list means that its
references are style/colour/material records; it never means a geometric body
can be removed. Colour styles alone do not distinguish paint from structural
surfaces. Do not use layer names, missing kinematics or sheet topology to assign
static geometry, animation owners, collision exclusions or texture baking.

Next, bind reviewed roles using source SHA, occurrence path and body/face IDs.
The simulator already has reviewed base-shield/outpost body bindings; those are
an independent source of runtime knowledge, not information supplied by these
layers. Keep moving equipment and independently controlled lights/armor as
separate owners before any mesh batching. Review surfaces carrying artwork
before proposing an explicit geometric-decoration-to-material conversion.

The follow-up [layer qualification review](rmuc2027-layer-review.md) compares
actual source face/body coverage against a pinned profile of the simulator's
reviewed motion owners. `python/review_cad_layers.py` remains analysis-only;
its component-selector candidates are not runtime roles or export policies.

Use the [source component catalog](cad-components.md) to work on smaller source
selections: it retains every original body and occurrence, supports manual
whole-body groups and exports isolated, geometry/style-verified STEP work items
on demand. Component organization remains separate from geometry optimization.
