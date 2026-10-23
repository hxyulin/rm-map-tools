<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Hierarchical optimization and LOD design

Build optimized arena assets from the source-backed [optimizer IR](cad-optimizer-ir.md),
with a reusable hierarchy and independently selectable detail per component.
Store shared geometry once; retain each placement, appearance, motion owner,
source identity and gameplay binding. Generate meshes from source surfaces before
resorting to mesh decimation. The [road component](cad-vector-component.md) already
demonstrates that better meshing can remove 95.72% of its native triangles while
retaining all source faces. That result is component-specific, not an arena estimate.

This document defines the next pass contracts. `python/cad_lod_policy.py` implements
the **policy/planning foundation**: hierarchy inheritance, protected subtrees,
composed error allowances, scale-aware local requests, shared-interface limits,
mesh cache identities and perspective error calculation. It does not implement
the proposed geometry passes, serialize a new IR, generate an arena LOD package,
or switch runtime LOD. `python/plan_cad_lods.py` connects the reviewed stage-one
hierarchy to this planner, preserving repeated occurrences and pooling identical
quality requests. Existing geometry exporters do not consume it automatically.

## Two graphs, with stable connections

Keep the semantic/culling hierarchy separate from the content-addressed geometry
DAG. A shared bolt may appear in many equipment subtrees without copying its
geometry or forcing those subtrees to select the same visual detail.

```text
arena
  terrain
    centre-platform
      deck / ramps / walls / decoration
    red-road
      profile / caps / supports
  equipment
    red-base
      frame / shield / armor / lights / secondary-fixtures
    red-outpost
      fixed-frame / rotor / detectors / lights
    red-rune
      support / rotating-arms / modules / lights
```

These are target semantic categories, not claims about the current source tree.
Use reviewed component IDs from the stage-one hierarchy; add reviewed child
partitions referencing source body/face uses. Preserve source ancestry alongside
this view. Presentation-layer names are evidence, not authoritative membership.
Unknown or unclassified geometry remains present and uses conservative defaults.

Each mesh-bearing use needs a stable ID, parent, geometry prototype, placement,
effective appearance binding, motion and contact/scoring owners, roles, protected
features, bounds, and source correspondence. Partitioning faces requires complete,
disjoint source ownership or an explicit shared-interface relation. Grouping
nodes carry policy without becoming a new copy of geometry. Do not merge through
independent motion, scoring, material seams or useful spatial culling boundaries.

## Ordered passes

| Order / pass | Output and intended saving | Admission / validation |
| --- | --- | --- |
| 1. Compact source recipes | Intern geometry, styles, strings, layer lists and topology operand arrays; retain occurrence-specific bindings | Exact reconstruction of source-owned values and references; no rounding |
| 2. Prototype factoring | Repeated bodies, faces, curves and parametric templates plus transforms/scales; mesh once per effective variant | Candidate hashes followed by verified correspondence; trims, senses and seams retained; mirrors explicit |
| 3. Reviewed semantic partition | Smaller editable/cullable equipment and terrain pieces, with separate decoration and dynamic owners | Every source use accounted for; reviewed ownership; no geometric deletion |
| 4. Surface-aware retessellation | Minimal planar triangulations, ruled/extruded strips, adaptive analytic/spline surfaces | All holes, loops and caps retained; source-shared edge samples; error evidence and topology checks |
| 5. Source patch coalescing | Remove redundant coplanar subdivisions or continuous same-support patches before meshing | Same support, compatible orientation/material/UV/semantics; finite trimmed-domain union checked; face provenance map retained |
| 6. Bounded parametric fitting | Rectangles, lines, arcs, ellipses, periodic road profiles and analytic surface families | Whole connected boundary network updated; cumulative error budget, feature and trim checks; retain original fallback |
| 7. Constrained mesh reduction | Remaining irregular surfaces, with curvature-driven density and locked critical features | Lock silhouettes, holes, creases, material/UV seams and interfaces; bidirectional finite-surface checks; reject invalid topology |
| 8. Reviewed detail removal | Optional secondary/internal detail variants; decoration projected to separate visuals or atlas | Explicit role/visibility evidence and review; hidden from one camera is insufficient; no automatic collision removal |
| 9. Mesh packing | Full-attribute vertex indexing, identical mesh/material pooling, compatible primitive concatenation, bounded quantization | Preserve normals, UVs, tangents, winding and source ranges; quantization consumes its own error allowance |
| 10. Reachability and archive | Store only referenced definitions/variants, compact bindings, compress release with `.tar.zst` | Manifest closure and hash verification; immutable source/checkpoint retained separately |

Passes 1–3 primarily reduce stored definitions and work. Passes 4–7 reduce placed
triangles. Pass 9 may reduce draws/storage without reducing triangles. Instancing
reduces duplication but still renders each placed copy. Report these separately.

Retessellate each LOD from the same source/prototype, rather than decimating LOD1
into LOD2 and accumulating untracked error. A triangle target is a secondary goal;
if the quality ceiling cannot be met, keep more triangles or reject that variant.
Exact plane retriangulation can preserve the finite surface while changing
interpolated shading and face identities; call that geometry-preserving, not
bit-exact mesh packing. Coalescing must retain colored subdivisions where needed.

## LOD policies and protection

Resolve policy root → equipment/terrain group → component → individual use.
Overrides address stable reviewed IDs, not substring matches. The nearest
explicit setting wins for that channel/level; omitted slots inherit. Keep one
camera-independent collision policy, plus any number of named visual levels.

Initial **review settings**, in millimetres, for ordinary unprotected surfaces:

| Part role | Near / inspection | Medium | Far | Collision |
| --- | ---: | ---: | ---: | --- |
| Traversable terrain / road profiles | 0.1 | 0.5 | 2 | Fixed 0.1–0.5, pending contact checks |
| Equipment frame and shell | 0.25 | 1 | 4 | Separate, based on clearance/contact checks |
| Reviewed secondary fixtures | 0.5 | 2 | 8 | Preserve existing policy until separately reviewed |
| Scoring faces, armor edges, light outlines | Protected; source-defined outline and binding | Protected | Protected or explicit visual proxy | Source-derived detector authority |
| Decoration / artwork | Preserve colors and readable markings | Explicit visual representation | Atlas or reviewed simplified visual | No exclusion inferred from role alone |

These numbers are proposed ceilings, not certified exports or rules constants.
Always also cap error relative to the smallest protected feature/gap. Existing
[export policies](export-presets.md) remain effective until a new adapter is
validated. A maximum deviation of 4 mm does not authorize closing a 3 mm hole.
Protected nodes inherit protection through their descendants. The initial planner
rejects fitting/quantization allowances in protected subtrees; source-preserving
retessellation remains allowed and still needs feature-specific checks. Float
export roundoff is measured and charged even when explicit quantization is off.

For each level, split the total allowance across fitting, meshing and storage
quantization. Their sum must not exceed the end-to-end ceiling; reserve any
remainder for other measured conversion error. Do not give every pass the entire
ceiling. Source-model inconsistencies/endpoints also consume or constrain this
margin. Use conservative accumulated world-transform scale to convert world
quality to prototype-local quality, including nonuniform scale via its largest
singular value. Normal transformation and reflected winding are separate checks.

Use this planner without OCCT or another dependency:

```python
from cad_lod_policy import Node, Quality, plan, shared_boundary_limits

nodes = [Node('arena', None), Node('road', 'arena'),
         Node('profile', 'road', prototype='road-profile-v1'),
         Node('cap', 'road', prototype='road-cap-v1')]
settings = {
    ('visual', 'near'): Quality(.1, mesh_mm=.09, quantization_mm=.01),
    ('visual', 'far'): Quality(2, mesh_mm=1.9, quantization_mm=.1),
    ('collision', 'fixed'): Quality(.1, mesh_mm=.1),
}
requests = plan(nodes, settings, {
    'cap': {('visual', 'near'): Quality(.05, mesh_mm=.05)},
})
interfaces = shared_boundary_limits(requests, {'source-edge-42': ['profile', 'cap']})
# Both visual owners, at every level, request the same .05 world-mm boundary network.
```

`Node.max_world_scale` is an already accumulated singular-value bound. The planner
is not a source hierarchy importer and does not infer semantic classifications.
Policies are immutable values; unknown nodes/slots, cycles, invalid budgets and
multiple camera-dependent collision levels fail before geometry processing.

## Mixed LOD without cracks

A numeric tolerance alone does not guarantee matching vertices. Give every
physical interface a stable source-edge/interface ID, a common coordinate frame, a canonical orientation
and an actual shared sample-network digest. The initial strategy keeps interface
samples at the finest requested level across adjacent owners and all visual
levels; simplify interiors independently. Caps and curved strips consume those
same samples, as in the component backend. Collision has a separate network.
The planner compares limits in world units across scaled owners; the mesher
converts the common limit into the interface frame before sampling. Artificial
face-partition seams require newly reviewed interface bindings.

This may constrain savings on heavily interleaved pieces. Later, nested boundary
samples plus explicit transition meshes can allow coarser interfaces. Independent
LOD switches require compatible transitions; a group-level LOD switch can avoid
transition meshes. Skirts can hide terrain gaps but change surfaces and must not
silently enter collision meshes. Do not weld unrelated coincident geometry.

## Payload and cache layout

Keep a source/checkpoint archive separate from the optimized runtime archive:

```text
manifest                 source, policy, producer and validation hashes
nodes                    hierarchy, transforms, owners, bounds, role bindings
uses                     node → geometry/appearance/LOD binding
prototypes/<digest>      canonical surface/curve/trim recipes when requested
meshes/<digest>          packed indexed geometry + attribute/source-face maps
appearances/<digest>     materials, artwork and optional atlases
validation/<digest>      achieved error, topology/coverage and contact evidence
```

This is a proposed logical layout, not a new implemented file format. Packed
arrays and integer indices should replace per-face repeated JSON; intern source
ID sets and material/attribute profiles. Runtime downloads normally need only
requested mesh variants and compact correspondence, not a copy of `source.step`
for every component. Keep recoverable provenance and a link to the immutable
source archive. Do not drop unknown source metadata from the archival checkpoint.
Raw byte count, compressed byte count and working-memory peak are separate goals.

Cache keys include source digest, complete geometry/trim recipe, effective local
quality and pass settings, boundary sample-network digest, attribute/seam contract
and producer version. `mesh_key()` provides this identity for the initial mesher
contract. Future fit/decimation options must be included through versioned settings
and geometry digests; never reuse a key across different algorithms. Cache
geometry separately from per-use appearance where the seam/attribute contract
allows it. Same effective meshes can alias across LOD labels/channels; preserve
independent use metadata. After generation, identical actual payload hashes may
alias even when requested quality differed. Do not store four copies of a simple
quad simply because four visual LODs were requested. Failed candidates never
replace valid cached payloads.

## Runtime selection and hierarchical LOD

Use measured achieved error transformed to world space. For a perspective camera,
approximate screen error is:

```text
error_px = error_mm × viewport_height_px / (2 × nearest_depth_mm × tan(vertical_fov / 2))
```

Use conservative nearest camera-space depth of bounds, not distance to their
centre. Near-plane intersections choose finest detail. Orthographic cameras need
a separate pixels-per-world-unit formula. `projected_error_px()` implements the
perspective calculation, not a selector. Suggested initial selector: refine above
1 pixel; coarsen below 0.7 pixels, with hysteresis and availability fallback.
Bounds, displacement limits and evidence coverage must be conservative; sampled
support distance alone is insufficient to certify screen error.

Keep equipment as useful culling/streaming units, independent moving links below
them, and terrain split along meaningful plate/ramp/interface regions. Optional
HLOD cluster proxies are a later pass: preserve leaf identities, aggregate bounds
and semantic anchors, and never render parent proxy and covered children together.
Do not bake reusable bolts into every cluster or merge the entire arena into one
draw at the cost of culling. Collision meshes and detector logic do not switch
with camera distance.

## Validation and implementation sequence

Each pass declares input stage, protected boundaries, deterministic configuration,
preconditions, proposed changes, effect class and rejection/fallback reasons.
Pin the source/hierarchy and producer hashes. Apply to a new derived revision,
validate, then publish references atomically. Keep source/last approved output.

Record per prototype and per hierarchy node: unique stored bytes, compressed
bytes, vertices, material primitives, placed triangles at each level, cache reuse,
achieved errors, source coverage, preserved material/UV/normal seams, finite trim
coverage, watertightness when required, and bounds. Validate outline/feature
retention and relevant contacts/clearances in addition to sampled supports and
volume. Show matched near views and mixed-LOD seam views. Never label a sampled
one-sided support check a bidirectional/continuous certificate.

Implement next in this order:

1. **Hierarchy adapter and inventory:** the initial adapter now connects reviewed
   component uses and checks complete face/placement accounting. Next identify
   interfaces, roles and protected features, including unknowns, and add measured
   per-subtree mesh baselines before reduction.
2. **Source tessellation variants:** extend complete road meshing to remaining
   eligible components; produce near/medium/far variants with shared interface
   samples. Measure storage and triangle curves against quality.
3. **Exact packing/prototype storage:** canonical mesh cache, full-attribute
   indexing and content-addressed manifest with aliases; remove duplicate stored
   buffers, not occurrence identities. Validate complete export round trips.
4. **Planar/analytic patch passes:** coalesce eligible source patches, then apply
   bounded shape fits coherently. Preserve original fallbacks and reviewed paint.
5. **Residual reduction and runtime adapter:** constrained irregular-surface
   reduction, then screen-error selection and optional cluster HLOD. Review
   secondary detail removal separately using its own role/visibility evidence.

Run the planning tests with:

```sh
python3 -m unittest discover -s python -p test_cad_lod_policy.py -v
```

## Real hierarchy plan and selective overrides

`python/plan_cad_lods.py` traverses actual assembly edges from the stage-one root,
retaining every child occurrence, source component identity and accumulated world
placement. Occurrence IDs include child slots so two uses of the same definition
under one parent remain distinct. It checks unique/disjoint source face coverage,
placed face counts, reachability, invertible affine matrices and the input source
checksum. It does not infer motion or collision roles from assembly labels.

```sh
python3 python/plan_cad_lods.py \
  out/rmuc2027-hierarchy/hierarchy.json \
  --source out/rmuc2027-hierarchy/field.step \
  --out out/rmuc2027-lod-plan/plan.json
```

An optional `--overrides policy.json` applies exact component-ID quality overrides
to all uses of that component. For example, this retains finer road detail at the
far visual level without changing its near or collision requests:

```json
{
  "red-road-surface/body-3789460": {
    "visual": {
      "far": {"total_mm": 0.5, "mesh_mm": 0.45}
    }
  }
}
```

The lower-level `plan()` API also supports ancestor and individual occurrence
overrides. The CLI currently exposes definition-wide overrides only. All imported
uses stay protected until semantic review; fit and quantization overrides are
rejected. The remaining budget margin reserves source/export numerical error.

The planning evidence accounts for
**116 component definitions, 171 placed component uses, 260 expanded hierarchy
nodes, 110,586 unique source faces and 214,794 placed source faces**. The initial
three visual levels plus fixed collision yield 684 request bindings and 484
pooled request profiles. Profiles retain channel distinctions and are not mesh
payloads. No triangle or storage reduction is claimed from these counts.

The biggest definition by source faces is still `base/source-model` (16,811
faces, used twice), followed by the Dart deck/hardware and frame components. The
base needs finer reviewed subparts before independently preserving armor/light
detail while simplifying its frame. Source face counts guide inspection; actual
triangle and byte inventories determine optimization priorities.

Motion/contact/scoring/light bindings and cross-component interface networks
remain explicit unresolved work. The complete generated plan is a small derived
JSON in ignored `out/`, not another copy of CAD or a published runtime package.

Run adapter regressions with:

```sh
python3 -m unittest discover -s python -p test_plan_cad_lods.py -v
```

## Visual-only terrain markings

The [source marking catalog](../rules/roles-rmuc2027-terrain.json) now binds known
terrain artwork using reviewed component/face IDs. Pass `--roles` to the hierarchy
planner to omit whole-marking collision LOD requests. Integrated markings remain
visual-only while separately owned unpainted backing retains terrain coverage.
The road LOD measurements document
current subdivision, coarser previews, native-baseline exclusion accounting and
the zero-collision border export. Runtime switching and backing-domain merging
remain separate stages; source markings are not inferred from colors at export.
