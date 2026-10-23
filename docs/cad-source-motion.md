<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
# Source motion preparation

The default RMUC 2027 source pipeline now runs **reviewed motion ownership before
hierarchy grouping**:

```text
Original STEP → source motion ownership → corrected work partitions → hierarchical STEP
```

[`cad_motion.py`](../python/cad_motion.py) reads
[`source-motion-rmuc2027.json`](../rules/source-motion-rmuc2027.json), pinned to the
original STEP SHA-256. Selections name original bodies, surface shells, or complete
original faces. They do not depend on simplified meshes, native import ordinals,
local `out/` files, or a previously generated hierarchy at build time.

The reviewed pass has 24 selection groups and eight mechanism definitions.
It records moving geometry, stationary logo/rail groups, source-local axes,
rulebook limits, and separately labelled inspection motion. It rejects duplicate
ownership, foreign bodies/faces, invalid groups, wrong-product joint ownership
and changed source hashes. Everything not explicitly reassigned stays in its
existing work group, except the Base's reviewed fixed source remainder.

## Corrected grouping

- **Outpost:** `outpost/rotor` contains all three armor modules and `carrier`.
  The fixed upper dart target and its small top pieces remain outside the rotor.
- **Rune:** each `rune/banks/bank-{a,b}` contains five arms and its rotating `hub`.
  Central R-logo/shaft-end bodies are in `rune/fixed/bank-{a,b}/logo`. Both rotors
  share the same oriented-axis angle; they look opposite from opposing sides.
- **Base:** `base/dart-target/carriage` holds the complete reviewed target/light
  selection; `base/dart-target/rail` is separate. `base/covers/cover-{0,1,2}` are
  independently owned. The remainder is retained under `base/fixed/source-remainder`.
- **Dart station:** the accepted `dart-station/door-candidate` becomes
  `dart-station/door`; guides, frame and deck stay separate.

Group ownership and joint definitions appear in `hierarchy.json` as
`source_motion`, with each component's `motion_owners`. STEP itself remains in
its original rest pose. This does not install a simulator controller or create
standardized STEP mechanical joint constraints. Original product-local axes must
be transformed through the retained source occurrence matrices by a consumer.

## Outpost face-patch exception

The original Outpost body #2101579 contains both carrier and fixed upper geometry.
The accepted carrier's 90,164 native triangles correspond exactly to **2,901 whole
original STEP faces**, with no partially selected face. Qualification is
reproducible with
`benchmarks/2026-10-24-source-motion/qualify_face_partition.py`; the resulting
source IDs are explicit in the committed policy, so qualification meshes are
not inputs to routine hierarchy builds.

The hierarchy separates this body into disjoint **open surface parts**, rewriting
only the solid/shell wrappers. All original faces, trims, curves, edges and their
shared geometry records remain byte-identical. No face is clipped, simplified,
filled or duplicated; the complete field surface remains present exactly once
per original occurrence. The original solid remains the authority for volumetric
semantics; the new patches are not individually closed solids suitable for mass
or inside/outside calculations. Other original solids remain solids.

The report lists `face_patch_body_ids` and `private_patch_wrapper_ids`. The shared
geometry digest excludes those intentionally rewritten wrappers; compare faces
and placement invariants rather than expecting the previous package's wrapper
or component digests to remain identical. Native read-back checks the complete
placed face count and one root assembly. A colored repeated-instance regression
checks private face wrappers and inherited appearance.

## Run

Optional standalone ownership audit, without writing STEP:

```sh
ocpenv/bin/python python/cad_motion.py source/RMUC2027_V1.0.0.stp \
  --policy rules/source-motion-rmuc2027.json --out out/source-motion-report.json
```

The normal hierarchy entry point automatically runs the pass when its policy
contains `source_motion`:

```sh
ocpenv/bin/python python/cad_hierarchy.py source/RMUC2027_V1.0.0.stp \
  --policy rules/hierarchy-rmuc2027.json \
  --out out/rmuc2027-hierarchy-motion-reviewed --validate-native
```

Use fresh output paths. The previous `out/rmuc2027-hierarchy` package is retained
unchanged as historical evidence. Existing policies without `source_motion`
retain their prior grouping behavior. Source preparation performs no tessellation;
GLB generation remains a later, explicitly approximate stage.

The release builder records the enabled source preparation pass and face-patch
body IDs. Its optional `--baseline` must refer to the newly reviewed hierarchy,
not the earlier hierarchy with different groups and solid wrappers. Release
building still requires committed producer files and a clean source checkout.

The Dart door's approximately 1.158 m preview stroke is inferred from the platform
height and source open pose. Base shield opening remains an illustrative
inspection displacement. Neither is upgraded to a measured mechanical limit.

Validation:

```sh
PYTHONPATH=python ocpenv/bin/python -m unittest -q \
  test_cad_motion test_cad_partition test_cad_hierarchy test_hierarchy_release \
  test_plan_cad_lods test_extract_entities
```

## Verified full-field successor

The completed local build at `out/rmuc2027-hierarchy-motion-reviewed/` contains
**124 component definitions / 185 placed component uses**, with all **110,586
original face definitions / 214,794 placed faces** retained. Native read-back
confirms one root assembly and identical full-field bounds. The native solid
count is 627 instead of 629 because the one fused Outpost solid, placed twice,
is now represented by its two original-face surface parts.

All 44 focused motion/partition/hierarchy/release/planner/extraction tests pass.
The generated package passes checksum and native-coverage verification.
`out/rmuc2027-source-motion/hierarchy-verification.json` pins producer and output
hashes, native evidence and the report-only metadata wording refresh. Original
STEP, earlier hierarchy and installed simulator assets remain unchanged.
