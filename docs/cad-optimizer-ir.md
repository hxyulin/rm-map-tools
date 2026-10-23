<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Source-backed optimizer representation

`python/cad_optimizer.py` builds an immutable, **in-memory optimizer IR** over an
open `CadDocument`. This is a working representation for optimization before
meshing. It does not emit a new standalone CAD format, change the published
release, or replace the runtime exporter. Source identity and metadata remain
available from the original read-only STEP and its reviewed hierarchy catalog.

The stage-one assembly is a hierarchy of occurrences referencing shared model
definitions. It does not deduplicate every face, curve or parameter. This IR
adds finer sharing without making geometry definitions into robot, motion,
material or contact identities.

## Representation

| View | Shared data | What each source use retains |
| --- | --- | --- |
| Geometry recipe DAG | Ordered construction records and child recipes | Original entity IDs, child IDs, topology incidence, labels and owner |
| Appearance recipe DAG | Complete presentation-assignment graphs, including literal names | Original paint binding, target, ordering, override and inherited context |
| Analytic prototypes | Primitive kind, dimension and exact intrinsic parameters | Original frame, parameterization, parent trims and topology |
| Unit analytic prototypes | Unit circle/ellipse, cylinder and sphere shapes | Exact local scale and original frame/parameters |
| Body uses | A shared construction recipe | Original product, occurrence path and source-world matrix |
| Metadata authority | Read-only source and pinned hierarchy bytes | All layers, unsupported records, source namespaces and original provenance |

Recipes use a packed byte arena, offsets and type arrays. Row-to-recipe arrays
separate source identity from sharing. Definition IDs are local to an IR. Optional structural views add stable
cross-document hashes and typed operands without treating these local IDs as
persistent identity. The recipe token encoding is deliberately **not STEP**.

Sharing a topology recipe does not weld vertices, edges or faces. For example,
two different vertices at the same position can share their construction recipe
while retaining different IDs and different edge incidence. A backend must use
`source_children(id)` and the source binding, not infer topology identity from a
recipe ID. Source face IDs remain the authority for armor/LED/material ownership.
An equal root recipe alone is not a topology-equivalence certificate: different
coincident-vertex incidence patterns can have equal construction recipes. A
body/mesh sharing pass must also prove incidence and a bijective face map, using
the retained source bindings (as the existing exact body pass does).

## Explicit topology and typed parameters

`ir.structural_views()` builds the opt-in views in `python/cad_ir_structure.py`.
The default lightweight construction does not allocate them automatically.

- **Topology uses** have original source IDs, kind IDs, shared recipe IDs,
  ordered child-reference spans and explicit final orientation/sense flags.
  `views.topology.use(source_id).roles()` exposes vertex points, edge start/end
  vertices and curves, oriented edges, loop edge uses, face bounds and surfaces.
  A loop may reference the same oriented edge repeatedly; distinct coincident
  vertices remain distinct. Unsupported forms expose ordered references.
- **Typed operands** use read-only CSR offsets, one-byte tags and 32-bit values.
  References address recipes; integers, reals, strings, binary strings, enums,
  omitted/derived values and normalized exact numbers address interned lexemes.
  Numeric values retain exact lexical bytes, without binary float conversion.
  A packed syntax arena retains grouping and unknown syntax. Every recipe must
  reconstruct byte for byte, including nested lists and quoted reference-like
  strings. These arrays supplement the recipe arena for now; they do not yet
  replace it or reduce process memory automatically.
- **Trim authority** stays in the original curve/surface construction graph,
  reachable through topology uses and typed recipes. This includes pcurves and
  surface-curve graphs where supplied. The IR does not invent UV polygons or
  claim that source-backed trimming is a normalized finite-patch representation.

Keep the `CadDocument` open for source lookups and validation. These views still
omit a standalone unknown-metadata ledger and source reconstruction encoder.

## Stable identities and pass contracts

Two versioned SHA-256 key families serve different purposes:

1. `stable_recipe_hashes` recursively substitutes child digests, independent of
   source numbering, local recipe numbering and root discovery order. Equal
   recipes can still have different original alias patterns.
2. `incidence_hash` traverses each ordered rooted source graph and emits
   first-visit node ordinals plus explicit backreferences. A self-connected edge
   differs from an edge between two distinct coincident vertices, even if their
   recipes match. Graph keys are conservative: different reference ordering,
   sharing of underlying construction nodes or parameter spellings can prevent
   a match between otherwise geometrically equivalent bodies.

Both key families include normalization policy and a context digest covering
complete geometric representation contexts, including unit and source uncertainty
subgraphs. Source context IDs are excluded. Changing tolerance invalidates the
key. Hash matches are candidate equality evidence; body/mesh reuse still requires
structural verification and a bijective face correspondence. Placements,
semantic/motion ownership, effective appearance, tessellation settings and error
budgets are separate dimensions and must be included by a future mesh-cache pass.
These hashes do not certify geometric congruence or authorize geometry edits.

`PASS_CONTRACTS` records prerequisites, preserved properties, correspondence and
measurement semantics for recipe interning and these three structural passes.
It is a reviewable contract inventory, not a general pass scheduler or a claim
that arbitrary third-party passes have been validated. `StructuralViews.validate`
reconstructs every typed record, rebuilds and compares the entire topology table,
rechecks context/recipe/body hashes, checks complete body-root coverage and verifies
the original source checksum. Corrupt orientation tables and omitted roots are
regression-tested, alongside renumbering, root reordering and tolerance changes.

## Exact normalization

The input must have one explicit, matching geometry-context unit profile. All
assigned units are checked, including angle units. Source radii remain in source
length units and cone angles in source angle units. Nothing is silently converted
to metres or radians. A supplied hierarchy catalog must checksum the input STEP;
its original-source identities remain distinct from the exported STEP namespace.

The default conversion interns ordered records after reference substitution,
removing whitespace/comments and known geometric display labels from the recipe
key. Original bytes and labels remain in the source bindings. Unknown entity
families keep their literal strings and ordered graph representation.

Two optional normalizations are available:

- `normalize_decimals=True` canonicalizes finite decimal literals by exact
  coefficient/exponent arithmetic. There is no binary float conversion or decimal
  context rounding. Generic INTEGER/REAL tokens and signed real zero stay distinct.
  Known analytic REAL parameter slots can unify radius `5` with `5.0` safely.
- `normalize_directions=True` reduces direction ratios to proportional integer
  tuples with a positive greatest common divisor. `(2,0,0)` and `(1,0,0)` share;
  `(-1,0,0)` remains opposite. Source ratios and vector magnitudes are retained.
  Unsupported syntax/pathological exponent spans keep the ordinary recipe;
  zero directions, unresolved refs and cycles fail.

Neither optional pass found additional definitions to share in this particular
CAD. Decimal keys grew by 10,106,189 bytes and proportional-direction keys by
599,580 bytes. Both options therefore default **off**, rather than claiming
normalization is automatically an optimization. They remain useful for other
exports and consistent geometric comparison.

## Affine primitive instances

For supported analytic shapes, the local maps preserve the source parameterization:

| Source primitive | Unit shape | Exact local scale |
| --- | --- | --- |
| Circle | Unit circle | `(r,r,1)` in 3D, `(r,r)` in 2D |
| Ellipse | Unit circle | `(a,b,1)` in 3D, `(a,b)` in 2D |
| Cylinder surface | Unit cylinder surface | `(r,r,1)` |
| Sphere surface | Unit sphere surface | `(r,r,r)` |

Cylinder z scale must remain 1: uniformly scaling it would change the axial
surface parameter. The source frame remains separate; no inverse matrix fitting,
rounding or baked pose enters matching. `LINE` uses retain the original point and
VECTOR reference, including vector magnitude and direction ratios. Planes retain
their original axis frame. Cones and tori currently keep dimensioned rigid
prototypes; no new parameter remapping is invented for them.

Scales are exact source scalar tokens in a separate shared scale table. Near-equal
radii can use the same unit shape while retaining different scales: CAD export
noise is preserved rather than rounded away. This does not make two differently
sized circles the same rigid shape. It makes their common analytic construction
explicit. A future transformed-mesh backend must also handle normals correctly
under nonuniform scaling.

## API and reproduction

```python
from cad_document import CadDocument
from cad_optimizer import build_optimizer_ir

with CadDocument.from_step('out/rmuc2027-hierarchy/field.step',
                           intern_layers=True) as cad:
    ir = build_optimizer_ir(cad, hierarchy='out/rmuc2027-hierarchy/hierarchy.json')
    for body, recipe in ir.body_uses():
        # body keeps product/path/source identity and its original world matrix.
        source_children = ir.geometry.source_children(body.source_body_id)
    report = ir.validate()
    views = ir.structural_views()
    structural_proof = views.validate(ir)
    # views.topology.use(source_face_id).roles() gives bounds and surface.
    # views.geometry.reconstruct(recipe) equals ir.geometry.record(recipe).
    # ir.affine.use(source_circle_id) exposes prototype, scale and frame refs.
```

```sh
ocpenv/bin/python python/audit_optimizer_ir.py \
  out/rmuc2027-hierarchy/field.step \
  --hierarchy out/rmuc2027-hierarchy/hierarchy.json \
  --out out/optimizer-ir-report.json
```

Use the pinned CAD Python environment. The audit compares the default conversion
with the two optional exact normalizations, independently rechecks every record
against source, re-derives analytic/affine uses, and verifies source hashes. It
creates no meshes, native CAD imports, persistent indexes or geometry exports.
A colored nested-instance regression covers source paint targets, hierarchy
metadata and placed body uses. Independent OCCT point evaluations check unit
circle, ellipse, cylinder and sphere maps, including cylinder axial parameters.

## RMUC 2027 measurements

Evidence and producer hashes
use the reviewed stage-one STEP SHA-256
`f561429d829e463fae5dd06d2b4eedbd9a7bbb87a0c9507ac6524fb47a021e73`.

- 3,982,578 reachable geometric records become **3,423,475 ordered recipes**.
  Most of the 559,103 aliases are point/direction/vector reuse; sharing the
  remaining construction graph contributes another **29,720 aliases** beyond
  those value families. Whole body roots still save only two definitions.
- 607,100 visited appearance records become **404 appearance recipes**, with
  **178,874 original paint bindings** retained.
- **398,486 analytic uses → 30,648 exact intrinsic shapes → 2,222 unit/rigid
  shape definitions**, with **16,449 exact scale profiles**.
- **674 placed work-body uses** retain their original paths and matrices. This
  count includes split surface-model wrappers; it differs from the hierarchy
  manifest's 644 original source-body placements. No occurrence is dropped.

| Primitive | Source uses | Intrinsic shapes, frame removed | Unit/rigid definitions |
| --- | ---: | ---: | ---: |
| Lines | 194,978 | 1 | 1 |
| Planes | 57,943 | 1 | 1 |
| Circles | 96,603 | 14,871 | 1 |
| Cylindrical surfaces | 44,534 | 13,533 | 1 |
| Spherical surfaces | 291 | 25 | 1 |
| Conical surfaces | 3,144 | 1,735 | 1,735 |
| Toroidal surfaces | 993 | 482 | 482 |
| Total | 398,486 | 30,648 | 2,222 |

That is about **179 analytic uses per shape definition**, not a 179× reduction
in meshes or triangles. The per-use frames, scales, edge loops and face trims
still exist. A unit cylinder's surface is reusable even when two cylindrical
faces have different holes or boundaries; their finished meshes are not
interchangeable merely because the surface prototype matches.

The default packed geometry records occupy 179,223,069 bytes. Offsets/types add
34,234,758 bytes and the source binding array adds 19,203,244 bytes. These figures
exclude the source document, appearance pool, analytic tables, scale strings,
metadata and Python/temporary overhead. This is an additional optimizer view,
not evidence for a smaller standalone archive or faster native tessellation.
Single-run build/validation timings are recorded in the report; they are not a
runtime performance benchmark. Source CAD, released assets and runtime packages
are unchanged by this work.

Structural validation can be reproduced separately:

```sh
ocpenv/bin/python python/audit_ir_structure.py \
  out/rmuc2027-hierarchy/field.step \
  --hierarchy out/rmuc2027-hierarchy/hierarchy.json \
  --out out/ir-structure/summary.json
```

The structural audit evidence
checks the same reviewed source:

| Check | Full-field result |
| --- | ---: |
| Recipes reconstructed byte for byte | 3,423,475 |
| Typed operands / reference operands | 14,924,319 / 4,614,603 |
| Explicit topology entities / ordered reference uses | 1,493,576 / 2,820,822 |
| Explicit orientations/senses retained | 1,151,092 |
| Body roots / distinct ordered incidence graphs | 447 / 445 |

Typed arrays, interned lexemes and syntax occupy 358,834,694 bytes; topology
arrays occupy 56,918,832 bytes and recipe hashes 109,551,200 bytes. Together these
optional views add **525,304,726 bytes** before Python containers/temporary data.
They currently coexist with the original recipe arena and source document. This
is preparation for typed passes and trustworthy caches, **not a storage saving**.
A replacement encoding can later remove duplicate representations, use narrower
offsets where safe, and choose hash retention granularity based on pass needs.
The single run took 51.28 seconds including source load/build and 28.36 seconds
for validation. No geometric congruence or mesh-reuse claim follows from the
445 ordered graph keys. Original source and package assets remain unchanged.

## Finite patches and primitive discovery

The first [finite patch and primitive-fit passes](cad-patch-fitting.md) now cover
straight-boundary, single-loop planar faces and measured approximation candidates.
Curved/holed finite patches and automatic edits remain outside this subset.

The [automatic vector layer](cad-vector-ir.md) now admits feature-limited,
continuously checked curve fits and pinned-corner polygon boundary templates.
Portable selections retain source spline parameters for tighter later exports;
they do not replace the complete source-backed CAD/metadata authority.

## Next passes

1. Extend finite matching to **curved/holed trimmed face patches**, carrying UV domains,
   loop winding, edge/vertex correspondence and original use identity. Prove
   congruence before calling them shared mesh definitions.
2. Group repeated patch/edge networks into shell/body prototypes, with explicit
   instance transforms and appearance maps. Keep motion ownership separate from
   geometry sharing. Quantized matching is candidate discovery, not acceptance.
3. Add canonical tessellation caches keyed by geometry, incidence-aware topology,
   trims, units, source context tolerances, sampling settings and effective
   appearance/face mapping. A scale-dependent error budget
   must be included when reusing sampled unit primitives.
4. Define a standalone encoding only after its source-binding/unknown-metadata
   ledger and exact reconstruction checks exist. The present IR intentionally
   depends on an open source document; serializing recipes alone is incomplete.
5. Introduce approximate CAD edits after those identities/maps are stable, with
   explicit per-pass deviation and topology/clearance checks. No such edit is
   established as safe or faithful by a successful template-sharing comparison.

## Finite affine patch layer

`OptimizerIR.affine_patch_instances()` now builds [bounded finite quad/triangle
instances](cad-patch-instancing.md) against its reviewed hierarchy. Source aliases,
component ownership, appearance targets, marking roles and all unsupported source
faces remain explicit. Compact tables and an inspection GLB demonstrate shared
payloads without merging those uses or installing a new runtime package.
