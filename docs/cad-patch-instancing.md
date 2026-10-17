<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Finite patch instancing and compact storage

The next [optimizer IR](cad-optimizer-ir.md) layer turns eligible finite planar
faces into reusable unit-quad and unit-triangle geometry. Dimensions and placement
remain per-use affine parameters. Source face/vertex/edge identities, orientation,
component ownership, appearance targets and visual-only marking roles remain
separate. Shared geometry never makes two physical contacts or owners identical.

This is implemented as an **optional source-backed layer** and partial inspection
export, not a complete runtime field replacement. Unsupported or rejected faces
remain explicit references to the immutable source. The prototype error policy is
`1e-6 mm`; this is bounded normalization, not bit-exact source CAD re-encoding.

## Acceptance and correspondence

`python/cad_patch_instances.py` starts from the finite patch reader, requiring a
single closed outer loop of straight edges on a plane. It refuses holes, curved
boundaries, unresolved topology and large unsupported loops. Original decimal
rational arithmetic measures endpoint incidence against source lines and planes.
Projected self-intersections are rejected before a template can be accepted.

Near-collinear boundary chains may collapse only with monotone chord projections
and a bound over every original chain vertex. Surviving source-corner indices and
all original boundary identities remain in each use. The source graph is never
edited, so future shared-boundary meshing can still resolve the original network.

Three corners define a finite triangle instance. Quad origin/first edge stay
source-anchored; its second axis is made orthogonal and the two affected corner
displacements are measured. Genuine trapezoids, sheared quads or changes exceeding
the budget retain their source fallback. Tiny or nonconvex shapes are rejected.
Source plane/line incidence, boundary-chain error, corner reconstruction and a
floating guard all consume the same budget. Source face sense determines facing;
prototype winding is not silently reflected.

The bound describes the **source straight vertex-polyline boundary**, not a
native healed face or solid. Continuous native trimmed-domain equivalence,
shared-edge seam integration and closed collision validation remain promotion
gates. This layer must not independently replace faces in an installed collider.

## Per-use data and APIs

`AffinePatchUse` retains the template, origin/u/v in source millimetres, original
boundary identities, retained corner indices, all orientation flags, error terms,
source component ID, diffuse appearance target and collision role. Dimensions
are not rounded into an equality hash. An accepted use maps the full finite
unit template to its own bounded source geometry.

```python
import json
from pathlib import Path
from cad_document import CadDocument
from cad_collision_roles import CollisionRoles
from cad_patch_instances import build_patch_instances
from cad_patch_storage import write_layer, read_layer

hierarchy = Path('out/rmuc2027-hierarchy/hierarchy.json')
roles = CollisionRoles.read('rules/roles-rmuc2027-terrain.json', hierarchy)
with CadDocument.from_step('out/rmuc2027-hierarchy/field.step',
                           workers=1, intern_layers=True) as cad:
    layer = build_patch_instances(cad, json.loads(hierarchy.read_bytes()),
                                  roles=roles, budget_mm=1e-6)
    write_layer(layer, 'out/new-patch-layer')  # New destination required.
    loaded = read_layer('out/new-patch-layer',
                        expected_source_sha256=cad.source_sha256)
    assert loaded == layer
```

`OptimizerIR.affine_patch_instances()` exposes the same layer when its reviewed
hierarchy is already attached. The direct document API avoids building unrelated
recipe views merely to inspect patches.

## Compact tables and archive compression

`python/cad_patch_storage.py` serializes numeric tables in an **uncompressed NPZ**,
with dictionaries and source/budget metadata in `manifest.json`. It does not put
one large JSON object or transform matrix around every face. The consumer needs
the checksum-pinned source archive to resolve fallback geometry and full styles.
This is not a standalone replacement for the complete CAD document.

Tables retain face/component/template indices, original appearance targets,
marking flags, origin/u/v rows, separate error allowances, original boundary CSR
arrays, orientation flags, surviving corner indices and every fallback face ID.
NPZ loading forbids pickled objects; checksums, dictionary indices, numeric shapes,
source accounting, budgets and nonsingular frames are validated. Writes are
staged and published only after every use field round-trips exactly.

Default storage uses direct float64 frames. `write_layer(..., frame_encoding='auto')`
can instead pool byte-identical edge-vector triples when that saves **raw array
bytes**. Matching uses complete floating byte records, preserving signed zero;
no quantized key authorizes equality. The RMUC run pools 68,146 edge-vector uses
into 47,150 definitions. This saves 231,320 raw bytes but compresses worse, so
archives use the direct default. Optimizing raw working memory and optimizing
compressed delivery are different decisions.

The audit adds source ownership notice and input/producer provenance, then uses
the existing archive writer at Zstandard level 22. Complete frame/member read-back
checks apply. Source CAD and fallback geometry are not copied into this small
optional-layer archive.

## Inspection GLB and material-independent sharing

`GlbWriter.add_indexed_instance()` shares complete position/normal/index byte
payloads independently of material variants. Repeated material bindings reuse a
mesh, while differing materials can reference the same accessors. Node metadata,
placements, component groups and marking flags remain independent. It accepts
caller-owned indexed geometry; it does not strip UVs from an existing mesh or
assume that RGB equality means complete source-material equality.

Quad instances use rotation/scale-compatible transforms. Arbitrary triangle
instances can need shear, which cannot be represented by ordinary glTF/Bevy TRS
poses. Their shear is baked into small local triangle geometry and they use a
proper rigid node pose. The writer rejects sheared matrices. This keeps the
inspection export interoperable without discarding the richer affine IR.

The GLB contains **accepted source definition faces only**, grouped by component.
It omits unsupported geometry from this diagnostic view, while the compact layer
retains every fallback reference. It is not the fully placed arena or a new
runtime collision package. Diffuse colors are resolved at face/shell/body targets;
9,931 accepted uses remain unresolved at that level and visibly use tagged
fallback material. Their source-face/context references remain available for full
appearance resolution. Do not treat the diagnostic fallback color as CAD paint.

## Measured RMUC 2027 result

The [evidence](../benchmarks/2026-10-17-patch-instances/README.md) pins source,
producer and output hashes and checks all 110,586 source faces:

| Measurement | Result |
| --- | ---: |
| Accepted finite source faces | 34,073 |
| Quad / triangle uses | 33,612 / 461 |
| Parametric template definitions | 2 |
| Original-source fallback faces | 76,513 |
| Original accepted polygon position bytes | 3,390,264 |
| Direct affine frame + template position bytes | 2,453,424 (27.6% less) |
| Unshared normalized mesh buffer budget | 3,666,054 bytes |
| Stored inspection mesh buffers | 28,506 bytes (99.22% less) |
| Geometry payloads / material mesh variants | 356 / 398 |
| Maximum finite boundary bound | 0.000000999334 mm |
| Maximum GLB vertex read-back roundoff | 0.000019813 mm |

The conceptual two-template IR and the 356 GLB geometry payloads describe different
boundaries: most non-right triangles need local shear baked for glTF. Independent
appearance variants account for additional mesh records without copying accessors.
The inspection GLB is still about 15.6 MB because its node/transform JSON dominates.
The numeric instance layer avoids this overhead and includes stronger source and
proof metadata than that diagnostic GLB.

With identical non-geometry tables, direct-frame storage compresses to 2,544,170
bytes at Zstandard level 22, versus 3,000,455 bytes for expanded finite corners:
15.21% less. Neither archive includes the fallback source geometry.

Instancing reduces stored definitions/buffers and repeated geometry work; it does
not remove placed copies or imply fewer GPU draws. In addition, collapsing proven
collinear source chains reduces the accepted polygons' simple triangulation
budget from 73,115 to 67,685. That separate 7.4% change is not an arena-wide native
triangle saving. GPU batching, whole-body reuse, native promotion and runtime
performance remain separate stages.

## Reproduce

```sh
ocpenv/bin/python python/audit_patch_instances.py \
  out/rmuc2027-hierarchy/field.step \
  --hierarchy out/rmuc2027-hierarchy/hierarchy.json \
  --roles rules/roles-rmuc2027-terrain.json \
  --out out/new-patch-instances

ocpenv/bin/python -m unittest discover -s python -p test_cad_patch_instances.py -v
```

The complete Python suite also covers existing instancing, artwork, collision,
source partitioning and protocol consumers. No original source or installed
package is modified by this pass.
