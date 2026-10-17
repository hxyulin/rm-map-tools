<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Global mounting-hole and fastener discovery

`mounting-details` is a registered **read-only** discovery pass over the shared
`CadDocument`. It inspects source STEP topology and analytic supports across
terrain and equipment, without OCCT import, healing, tessellation or geometry
edits. It works before an optimization IR or mesh export. Findings carry the
source document checksum and original STEP body, shell, face, bound, loop and
edge IDs, plus owning products and optional hierarchy component membership.
Native import ordinals are never substituted for STEP IDs.

```sh
ocpenv/bin/python python/audit_cad_passes.py out/rmuc2027-hierarchy/field.step \
  --source-sha256 f561429d829e463fae5dd06d2b4eedbd9a7bbb87a0c9507ac6524fb47a021e73 \
  --passes mounting-details --out out/mounting-discovery.json
```

The standalone entry point adds work-part membership and budget options:

```sh
ocpenv/bin/python python/audit_mounting_details.py out/rmuc2027-hierarchy/field.step \
  --source-sha256 f561429d829e463fae5dd06d2b4eedbd9a7bbb87a0c9507ac6524fb47a021e73 \
  --hierarchy out/rmuc2027-hierarchy/hierarchy.json \
  --maximum-diameter-mm 17 --maximum-fastener-length-mm 60 \
  --maximum-slot-length-mm 60 \
  --out out/rmuc2027-mounting-details/audit-final.json
```

Output paths must be new. Existing reports, source CAD and caches cannot be
overwritten. The original source checksum is verified, millimetre units are
required, and the source is checked unchanged after discovery. Both entry
points also accept a source-owned parser index cache. No new dependency is
needed for the discovery code beyond the existing graph/parser infrastructure.

## Evidence and qualification

- **Circular opening mouths:** exactly one explicit planar outer bound, an
  explicit inner `FACE_BOUND`, a connected ordered loop, coincident analytic
  circle supports, planar incidence, and one full signed turn. Split circles
  are supported. Source `SURFACE_CURVE`/`SEAM_CURVE` wrappers are unwrapped to
  their explicit 3D curve. A circular outer silhouette is not a mounting hole.
- **Narrow analytic openings:** other connected planar inner line/circle loops.
  Conservative calipers use the face axes and straight-edge directions; each
  trimmed arc contributes its complete circle bound. Defaults require width
  strictly below 17 mm and length at most 60 mm. These may be slots, sockets or
  other functional openings; their mounting role remains unconfirmed.
- **Possible fastener units:** bounded native body/shell definitions with coaxial
  analytic cylinders, plane/cylinder/cone surfaces and supported line/circle
  trims. Conservative spans in a frame aligned to the cylinder axis must be
  below 17 mm transversely and at most 60 mm axially. At most 256 source faces
  per unit are inspected by this classifier. Large, noncoaxial, freeform,
  toroidal/spherical or unsupported units are reported as skipped.
- **Source-name evidence:** a recognized owning-product hardware name is a
  separate hint. Geometric candidates remain unconfirmed: pins, bushings,
  hinges and indicator shells can resemble fasteners. Name hints do not grant
  removal permission.

All original body definitions are inspected, including any unowned definitions.
Shared source units retain every body/product reference. Product summaries are
reference counts and need not be additive. Source bounds/edges with unsupported
curves, missing outer-bound semantics, invalid frames or unresolved incidence
are counted by skip reason rather than guessed.

Circular mouths are grouped into source-body-scoped coaxial families using a
rounded analytic support key for discovery. Every original mouth remains in the
report. Neither a family nor two aligned mouths proves through-hole topology,
blind-hole topology or physical-feature equivalence. Slots, threaded/freeform
bores and merged fastener detail are incompletely covered; absence is not proof
that a component has no mounting details.

## RMUC 2027 source inventory

The complete hierarchical source has **447 body definitions, 2,766 units and
110,586 face definitions**. The default audit finds:

| Finding | Count |
| --- | ---: |
| Circular opening mouths | 17,507 |
| Narrow noncircular opening mouths | 2,299 |
| Total opening mouths | **19,806** |
| Coaxial opening families | 6,580 |
| Possible fastener units | **1,098** |
| Candidates supported by an owning-product hardware name | 0 |

All findings map back to reviewed hierarchy components. Leading groups:

| Group | Opening mouths | Possible fastener units |
| --- | ---: | ---: |
| Rune | 7,642 | 772 |
| Dart station, including the two extra station-part groups | 3,694 | 167 |
| Outpost | 3,138 | 13 |
| Base | 2,796 | 108 |
| Tech Core | 1,607 | 10 |
| Resource area | 560 | 28 |
| Fans | 226 | 0 |
| Other terrain/equipment groups | 143 | 0 |

These are **original source definitions**, not placed occurrences, current
optimized runtime detail, physical hole counts or triangle-saving estimates.
For example, many Rune hits are already addressed by the front/back candidates.
A zero fastener count can mean the source merged hardware into a larger unit or
used unsupported geometry. The full report lists every candidate and skip.

The [benchmark record](../benchmarks/2026-10-17-mounting-details/README.md) retains
compact measurements, source/producer/report hashes and examples. The complete
source-bound report is generated at
`out/rmuc2027-mounting-details/audit-final.json`.

A future reviewed apply pass can consume explicit bound/face/unit selectors,
check material and motion ownership, fill only selected bores or replace selected
hardware, and validate local appearance/collision. This discovery pass writes
`actions: []`; it does not authorize or perform that work.

## Individual removal previews

The [native preview benchmark](../benchmarks/2026-10-17-mounting-preview/README.md)
turns explicit audit selections into separate original/holes/fasteners/combined
visual candidates for all 36 affected work parts, plus five full equipment
compositions. It fills only complete circular mouths under 17 mm and holds all
non-round openings. Nine unmatched hardware units and 29 invalid face profiles
remain unchanged. Original resolved face colours and untouched mesh attributes
are preserved directly in native memory. The read-only discovery pass itself
still writes no geometry or removal actions.
