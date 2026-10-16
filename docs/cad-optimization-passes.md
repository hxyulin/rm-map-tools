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
