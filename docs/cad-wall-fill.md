<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Bounded native wall filling

`python/cad_wall_fill.py` closes reviewed openings in a derived native B-rep,
then merges adjacent coplanar faces and collinear edges. It is an approximate
optimization pass: real apertures become solid. Original STEP remains immutable;
geometry, source identifiers and full presentation authority remain available
from that checksum-pinned source. It does not decimate a previously exported mesh.

## Reusable operations

`WallPanel` describes an explicit box in a right-handed orthonormal source frame.
`FaceProfilePanel` uses a selected native planar face, a signed extrusion depth
in millimetres, and either of two profiles:

- `outer-wire` retains the exact source outline and omits its inner wires. This
  replaces grille cells with one panel while preserving outer chamfers.
- `convex-hull` bridges concavities in a straight polygon. It requires explicit
  selection; it must never be applied to every concave shape automatically.

An optional `window_uv_mm=(u0,v0,u1,v1)` clips the finite profile in its source
plane's coordinates before extrusion. This limits work to a ribbed cavity,
avoiding larger mechanical or traversable openings in the same body. Curved
outer boundaries are refused in hull mode. Signed depth follows the native plane
axis, independently of the topological face orientation.

`fill_wall(source, panel, source_colours, max_added_volume_mm3=...)` returns a
`WallFillResult`: derived solid, per-face diffuse colors, source-native face
correspondence and validation measurements. The implementation performs an
additive Boolean union, followed by native same-domain unification. Different
diffuse colors protect their shared edges from unification. Every Boolean result
face needs source or panel history; ambiguous source appearance is rejected.
`None` keeps unresolved source paint unresolved, with a tagged neutral preview
fallback. Generated panels inherit the selected face's diffuse binding.

The ledger concerns diffuse appearance and native shape correspondence, not
complete STEP material/presentation re-encoding. Original source references stay
authority for metadata that the derived inspection STEP does not transfer.

## Acceptance checks

The pass requires a valid single source solid, complete per-face appearance
accounting, positive overlap, nonempty additions and a reviewed added-volume
budget. The result must remain one valid native solid. Native difference checks
measure removed material and additions outside the panel, each limited to
0.01 cubic millimetres by default. Volume conservation is checked separately.
These are OCCT Boolean/volume checks at kernel tolerance, not a mathematical
certificate of zero surface deviation. No triangle sampling authorizes removal.

A 0.00001 mm depth overlap beyond nominal thickness is recorded in the RMUC
policy. At exactly 3 mm the source grille's coincident-cap Common operation
incorrectly produced an empty intersection in OCCT 8; the tiny overlap avoids
that failure. It is not an increased meshing or simplification error allowance.
The same validity and difference checks still apply.

`python/apply_wall_fills.py` checks source/hierarchy hashes, component STEP
checksums, source face counts, selected face area/normal/wire count and original
placement counts before running a policy. Native face indices are scoped to
an extracted component STEP checksum; they are not original STEP face IDs.
The report retains the original source component's face inventory and the
pre-serialization native history ledger. STEP may reorder faces, so that ledger
is explicitly not indexed against the serialized STEP. Read-back checks validate
face count, volume and diffuse-color accounting, then remesh at the same settings.

## RMUC 2027 candidate

The [policy](../rules/wall-fills-rmuc2027.json) selects two grille definitions,
used twice each, and the six-rib cavity in each central tunnel-side high-ground
wall. These narrow wall cavities are selected below their roof and above their
original feet level. Their other functional openings remain outside the window.
This adds about 64.6 and 64.7 litres inside the selected wall envelopes, replacing
open cavities with solid material. It does not change the deck artwork, main
roads, trapezoid highlands, collision/scoring equipment or source assembly.

At the native baseline of 0.4 mm / 0.25 rad:

| Selected geometry | Placed triangles before | After |
| --- | ---: | ---: |
| Under-highland grilles, two uses | 3,632 | 72 |
| Tunnel grilles, two uses | 2,624 | 76 |
| Both tunnel-side walls | 2,668 | 2,306 |
| Total selection | 8,924 | 2,454 |

That is 6,470 fewer placed triangles (72.50%); it is not an arena-wide saving.
The main roads and their borders still dominate native terrain cost. Counts
exclude the separately approved 16-section road preview, which has not yet
replaced full native road meshing. The resulting STEP and GLB are candidates;
no runtime package or published archive is changed.

[Measurements and reproduction](../benchmarks/2026-10-17-wall-fill/README.md)
include matched source/candidate views. Visual and collision export can consume
the same derived solid, avoiding two independent approximations. Runtime
integration and approval remain separate from this native working pass.
