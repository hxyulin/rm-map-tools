<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 Base visual and collision LOD

The [approved native detail passes](cad-detail-passes.md) leave 476,924 triangles
per Base. Eight source units—the three tall covers, four module backing shells
and module frame—still contain 242,505 triangles. This experiment gives visual
relief and collision separate policies. Original STEP, the approved model,
mechanism bindings and installed runtime assets remain unchanged.

## Measurements

| Output | Triangles / definition | Two placed Bases | Reduction from approved |
| --- | ---: | ---: | ---: |
| Approved visual reference | 476,924 | 953,848 | — |
| Visual LOD candidate | 275,172 | 550,344 | 42.3% |
| Independent collision candidate | 20,095 | 40,190 | 95.8% |

The visual candidate is 61.2% smaller than the original 709,354-triangle native
mesh. The collision comparison uses the approved **visual** mesh as its input;
it is not a measurement of an installed runtime collider. Stage one already
instances one shared Base definition twice. These passes reduce its definition
and placed triangles; they do not introduce additional instance sharing.

The inspection GLBs are 37,501,060 bytes for the approved reference, 20,834,356
bytes for the new visual and 1,541,816 bytes for collision. This measures this
benchmark's GLB writer, not a compressed release or final packed runtime format.

## Appearance-protected visual reduction

[`cad_surface_lods.material_lod`](../python/cad_surface_lods.py) operates on
explicitly selected tessellated source units. It partitions by source material,
locks each material region's open borders, and leaves caller-protected material
triangles unchanged. The existing component-retaining meshoptimizer backend
keeps small disconnected components. Each region is rebased around a local
origin before conversion to float32; protected triangles remain float64.

This trial requests a 0.25 mm meshoptimizer metric and separately measures
bidirectional point-to-triangle distances at up to 2,048 deterministic triangle
selections per material. Its sampled guard is 1 mm. Regions exceeding the guard
retry at half the metric, up to four refinements; the guard is never relaxed by
that loop. The third tall cover needs one refinement. The initial exploratory
0.5 mm sampled guard rejected all eight units; the reviewed candidate explicitly
uses 1 mm rather than describing the metric as a surface error bound.

The largest accepted sampled visual distance is 0.9664 mm. These are samples on
the native **tessellated mesh**, not an exact B-rep support calculation, continuous
Hausdorff bound or trim-domain proof. Material borders remain locked in the
simplifier's float32 frame; only protected triangles claim exact source positions.

The written outputs independently preserve all 16,806 red/green light triangles,
including their source face ids and diffuse values, and all 332 unselected units
byte for byte at array level. New triangles retain source ownership at the
selected-unit/material-region level; their single source-face id is zero rather
than a guessed association. Module fronts stay unselected. Eighteen matched
1200² source-pose views measure at most 0.055% changed RGB pixels above 10/255,
and 0.00889% changed foreground pixels. Moving poses need separate review.

## Collision profiles and coarse source meshes

`profile_prism()` reconstructs a valid native solid from an explicitly pinned
source planar face's **unchanged outer wire**, a signed thickness along its
native plane normal, and selected retained inner wires. Small inner loops are
intentionally capped by area. Native profile validity, single-solid output and
area × thickness volume accounting must pass. The result is a replacement
plate, not an additive union or conservative enclosure of the source member.

Four module backing shells accept 1.5 mm thick source-outline plates. Holes
larger than 100 mm² remain open; smaller holes are capped. Molded recesses,
mounting posts and ribs disappear from these collision shapes. Their measured
bidirectional sampled distances are 10.80–13.20 mm against a 15 mm profile guard.

Three-profile cover replacements and a flat module-frame replacement were also
built and tested. All four are **rejected**: covers lose deep structural returns
by up to 135 mm; the frame loses 49.90 mm. The ledger retains these failed
attempts. Their fallback is a coarse source mesh, not a hull or filled box.
These meshes request a 3 mm metric with a separate 6 mm sampled guard and the
same automatic refinement. Cover validation samples reach 4.57–5.32 mm, and the
frame reaches 5.96 mm. Larger apertures and returns therefore remain geometry.

The remaining non-light units of maximum span ≤20 mm are explicitly omitted
from this collision experiment (292 units). Other members use coarse source
meshes, falling back to the approved mesh on a failed check. The four profile
replacements are individually valid closed solids; the entire collider export
is not claimed to be a new watertight manifold. It preserves the source-unit
hierarchy and does not establish motion ownership or scoring/detector masks.

## Relief maps and the next visual representation

[`cad_relief_bake.bake_relief`](../python/cad_relief_bake.py) projects an explicitly
selected source mesh into a caller-owned plane frame. It produces source diffuse
RGBA, linear tangent normal RGB, signed millimetre height and per-pixel source
triangle ownership. A 512² bake of backing shell #4756187 demonstrates molded
pocket edges, small bores, bevels and posts without inventing painted colors.

This is intermediate texture infrastructure. No normal-map material or new UV
chart is attached to the visual candidate yet, and the bake contributes **zero**
additional triangle savings to the table above. UV charts, gutters, mip filtering,
renderer tangent conventions and textured replacement comparisons remain needed.
The height map is not ambient occlusion, and normals must not be sampled as sRGB.

Fine bevels, shallow recess shading and small screw heads can move to texture
layers where they do not affect the silhouette. Outer rims, broad folded panels,
through openings, deep returns and LEDs remain geometry. Undercuts need another
projection or retained geometry. Broad cover returns cannot be flattened merely
because one front view looks flat—the rejected collision trial demonstrates it.

[Benchmark inputs, commands and measurements](../benchmarks/2026-10-17-base-surface-lods/README.md)
retain the source pin, explicit selection policy, integrity results and failures.

The subsequent [17 mm gap and LED pass](base-gap-led-rmuc2027.md) extends these
approved candidates with width-based closure and a separate, tighter LED policy.
The tables above retain this experiment's historical counts.
