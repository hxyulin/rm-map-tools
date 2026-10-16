<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Complete Rune and Outpost CAD partitions

`python/cad_partition.py` builds complete source-owned work exports from the
[component catalog](cad-components.md). It separates whole original solid bodies
and whole shells inside `SHELL_BASED_SURFACE_MODEL` containers. No face is cut,
shape approximated, Boolean operation performed or runtime asset installed.

The policy [rules/partition-rmuc2027.json](../rules/partition-rmuc2027.json) is
pinned to source SHA
`a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0`.
The [earlier region audit](non-base-components-rmuc2027.md) discovers candidates;
this explicit follow-up policy chooses disjoint work ownership, including a
remainder for uncertain source shells. Work ownership does not establish how a
component should move, light up, score or collide in the simulator.

## Complete partitions

| Product | Groups | Original solid bodies | Original surface shells | Source faces |
| --- | ---: | ---: | ---: | ---: |
| Outpost #2603236 | 6 | 42 | 14 | 21,626 |
| Rune #1354629 | 13 | 159 | 1,063 | 29,640 |

The Outpost's groups are the lower cluster, column, upper cluster and three rotor
modules. The lower cluster includes six original surface shells; the upper
cluster includes five. Each rotor module includes its five mechanical bodies
and the nearby 688-face shell, for 3,795 faces per module. These surface
attachments are explicit work groupings, not a change to the existing fixed
surface-model runtime binding.

The Rune has ten arm groups, two hub groups and `rune/support-and-shared`.
Each arm contains ten solid bodies and **95 source shells**, totaling **2,065
faces**. Its 999 surface faces include a 453-face cover shell that extended
20–48 mm beyond the earlier mechanical-only discovery box. The next arm box was
at least about 480 mm away in that comparison. The policy expands each arm's
box to include its cover with 1 mm padding.

The expanded boxes include the same repeated shell face-count signature on all
ten arms: 75 shells of two faces, 14 of three, two of 82, two of 78, one of 453
and one of 34. Incidental one-face matches remain outside arm groups. Original
geometry is retained even where its curved surface extends outside a vertex
box; selection never clips it.

The 80 arm/hub overlaps from discovery resolve by an explicit priority: specific
arm regions precede the broader hub boxes. No shell overlaps two arm regions at
the chosen priority. Each hub retains ten shells plus its original 19 or 20
solid bodies. The remaining 93 shells and 20 solid bodies are fully exported in
`support-and-shared` (3,094 faces). This remainder retains support geometry and
unresolved pieces; its functional subdivision is still open. Equal-priority
conflicts would also remain in the remainder rather than duplicate geometry.

## Exactness boundary

The compiler enumerates every original face of each product and requires its
assignment exactly once. Surface shells and solid bodies are indivisible units;
source units sharing a face or lacking faces are rejected. The ten Rune arm
body/shell/face signatures are explicit policy assertions.

For a shell subset, `p21split.Splitter.closure_products()` blocks unselected
shells and narrows only the source surface-model wrapper's reference list.
Original shell, face, edge, curve, coordinate and style records retain their
source IDs and byte-identical text. Parent-level styles continue to target the
same wrapper ID. Representation/layer lists are filtered consistently, and all
output references must resolve. Different component files may carry the same
wrapper ID with different, disjoint shell lists; the wrapper ID alone is not a
unique partition component identity.

`cad_components.export_selection()` reparses each export. It checks the exact
selected body/face set and source geometry/style record preservation. The source
wrapper is compared against its deliberately filtered text. Exported metadata
records `selected_source_shell_ids` and `rewritten_surface_model_body_ids`.
Original STEP and runtime field packages remain untouched.

Each component is then imported into OCCT. Native face counts must match its
source partition, solid counts must match its original solid bodies, and mesh
extraction must report no unmeshed nonzero-area faces. Native zero-area faces
remain in STEP; each requires a recorded finite area below 1e-8 mm² and a
matching degeneracy count before it can contribute no triangles. The sum of
native component face counts must match the entire original product. Full
assembly GLBs reuse these same component meshes and poses, avoiding a separate
full-model tessellation or shape import with different healing decisions.

GLB is an RGB, tessellated inspection derivative with float32 geometry. The
packed STEP remains authority for exact source geometry and full CAD style
records. Mesh triangles are not mapped to original STEP face IDs; per-component
face sets are recorded separately. Nothing here claims lossless GLB materials
or an animation-ready articulation hierarchy.

## Run

From `rm-map-tools`:

```sh
ocpenv/bin/python python/cad_partition.py source/RMUC2027_V1.0.0.stp \
  --policy rules/partition-rmuc2027.json \
  --components rules/components-rmuc2027.json \
  --motion-profile rules/reviewed-motion-rmuc2027.json \
  --export --out out/cad-components/rmuc2027/full-separation-v1
```

An original-source `.npz` parser cache may replace the STEP path. Without
`--export`, `--out` receives a partition JSON report only. Outputs must be new.
The component policy's region pin is verified. The report captures the source,
policy/profile inputs and producer hashes. The export bundle is staged and only
published locally after all products pass validation.

The bundle contains:

```text
manifest.json                  # checksums and native import/mesh checks
partition.json                 # complete source body/shell/face ownership
outpost/
  full/source.step.gz          # complete original product geometry and styles
  full/selection.json          # original occurrence paths, matrices, units
  full/visual.glb              # assembled from all six component meshes
  components/fixed/.../       # column, lower, upper work items
  components/rotor/module-0/   # body + shell work candidate
rune/
  full/source.step.gz
  full/selection.json
  full/visual.glb              # assembled from all thirteen component meshes
  components/banks/bank-a/arm-0/
  components/banks/bank-a/hub-cluster/
  components/support-and-shared/
```

Every component directory contains `source.step.gz`, `selection.json` and
`visual.glb`. STEP is packed after validation, using deterministic gzip, to
avoid keeping hundreds of megabytes of repeated source layer lists. To edit one
work item, run `gzip -dk source.step.gz` in its directory, then open the resulting
`source.step`. Its uncompressed and compressed SHA-256 values are recorded in
the sidecar. No original CAD file is linked or modified.

STEP coordinates stay in original product-local millimetres. GLB vertices use
product-local metres with a common node rotation from the first source
occurrence into Y-up inspection axes; no coordinates are baked or recentered.
Original source-world placements for all copies remain in selection sidecars.
The Outpost GLB represents one equipment definition; its two team placements
are not duplicated into this work asset.

## Review next

Inspect the assembled models, one Rune arm, an Outpost module and the Rune
remainder. In particular, review whether the three Outpost 688-face shells
should actually follow rotor motion. This export does not install that change.
Remaining work is finer functional labeling of the Rune's support/remainder,
reviewed moving-owner/light/collider bindings, and exporter integration with an
approved runtime package. Complete geometry coverage is already required;
functional classification is a separate review.

## Visual review findings (2026-10-16)

The initial review image used average-triangle depth sorting. That is not a
correct visibility algorithm: intersecting triangles produced jagged edges and
thin light details disappeared after integer pixel rounding. Use per-pixel
depth testing with subpixel triangle coverage and supersampling for subsequent
inspection images. A preview artifact alone is not evidence of broken CAD or
z-fighting in the exported GLB. RGB inspection materials do not establish which
surfaces are emissive LEDs.

The Outpost's isolated module also has a real ownership limitation. Source body
**#2101579** (`BREP_WITH_VOIDS`, 4,422 faces) spans the upper housing and the
module front covers. Its main 4,416-face shell is connected by shared source
edges; whole-body and whole-shell grouping cannot separate those covers.
Module 0's cover can be identified as a connected **468-face patch** within a
5 mm-expanded module-shell vertex envelope. A broad envelope alone selects 617
faces, including partial mounts; it is not a sufficient functional boundary.
The other two covers still require matching and review. The existing bundle
retains all these faces in `fixed/upper-cluster`; its isolated modules must not
be described as complete functional modules.

For this follow-up, `cad_components.export_selection(...,
face_ids_by_body={body_id: original_face_ids})` supports explicit source face
patches. It changes the source body wrapper to `SHELL_BASED_SURFACE_MODEL` and
selected shell wrappers to `OPEN_SHELL`. Original selected face, bound, edge,
surface, coordinate and style records remain byte-identical. No face is cropped
and no cap is invented. Sidecars record the selected original face IDs and
explicitly identify the output as open surfaces. This is an inspection aid;
the original fused solid remains authority for solid topology and collision.
The whole-body/shell partition compiler does not yet assign these patches or
install them into runtime motion bindings.

### Reproduce the reviewed module-0 cover candidate

The [reviewed face selection](../rules/outpost-module-0-cover-rmuc2027.json)
records the 468 original cover-face IDs and its source SHA. Visual approval
covers this candidate's appearance; it does not establish a runtime joint or
closed solid. Given the original source `document` and its component `catalog`:

```python
import json
from pathlib import Path
from cad_components import export_selection, select_components

policy = json.loads(Path('rules/outpost-module-0-cover-rmuc2027.json').read_text())
assert document.source_sha256 == policy['source_sha256']
selection = select_components(catalog, policy['selector'])
extra = set(policy['additional_body_ids'])
components = [c for c in catalog['components']
              if c['product_id'] == 2603236 and c['body_id'] in extra]
selection['components'].extend(components)
ids = {c['id'] for c in components}
selection['occurrences'].extend(o for o in catalog['occurrences']
                                if o['component_id'] in ids)
export_selection(document, selection, Path('out/module-0-cover'),
                 shell_ids_by_body={int(b): ids for b, ids in policy['shell_ids_by_body'].items()},
                 face_ids_by_body={int(b): ids for b, ids in policy['face_ids_by_body'].items()})
```

This creates a standalone source STEP plus selection metadata. Import it and
use the same tessellation and common inspection rotation as `export_bundle()`
when generating a GLB. Expected native counts are five solids and 4,263 faces;
the cover itself is an open surface patch. The original bundle still retains
the cover in its upper cluster, so do not overlay this candidate onto that
bundle without removing the corresponding faces there.

The [remaining-equipment policy](remaining-equipment-rmuc2027.md) applies the same
exporter to the Tech Core, resource area, Dart station and Energy Unit.

For exhaustive original solid/surface-shell selection, see the
[terrain and secondary-equipment source-unit policy](terrain-equipment-rmuc2027.md).
