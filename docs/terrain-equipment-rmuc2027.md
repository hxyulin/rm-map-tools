<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 terrain and secondary equipment separation

The [source-unit policy](../rules/partition-rmuc2027-terrain-equipment.json)
separates the remaining 25 body-owning source products into **85 pieces** without
changing source faces, curves, coordinates, styles or solid topology. This covers
84 original body definitions and all 6,726 of their source faces. The extra piece
comes from splitting a two-shell surface-model container into its two original
shells. No geometry is simplified or deleted and no runtime package is installed.

| Family | Separate definitions | Placed pieces | Contents |
| --- | ---: | ---: | --- |
| Drone landing pad | 1 | 2 | Complete original 60-face solid |
| Fortress | 4 | 8 | Main body and three separate marking bodies |
| Fans, frames and grilles | 5 | 18 | Fan, two frames, two grille products |
| Footings | 2 | 4 | Base footing and Outpost footing |
| Terrain and markings | 66 | 66 | Floor, assembly area, deck, tunnel sides, highlands, high points, roads and markings |
| Dart-station ancillary products | 7 | 14 | Three timber-product bodies, one separate plate product, one solid and two sheets in another source product |
| **Total** | **85** | **112** | **25 source products** |

The original component catalog has 110 placed bodies in this subset; splitting
the two-shell container adds two placed pieces across its two occurrences.
The fan remains one definition used at ten source placements. Definitions and
placed geometry counts must not be confused: this review has 280,398 definition
triangles and 662,976 placed triangles at 0.4 mm / 0.25 rad tessellation.
These are inspection mesh counts, not runtime performance measurements.

## How far the source boundaries go

The floor has four source solids. The red and blue road-surface products each
have 24 solids and one surface shell, producing 25 pieces per side. Many of
these are thin marking/detail bodies, not large structural terrain chunks.
Each high-point upper product has two bodies. The fortress has four independent
bodies; its main body and three marking bodies are kept as geometry, with no
texture conversion or collision exclusion implied.

The drone pad, fan, grilles, footings, central deck, tunnel sides, trapezoid
highlands and lower high points are each single whole source solids. Their
internal faces are not automatically separate mechanical components. Fan rotor
versus housing, or finer pad/terrain subdivisions, would require an explicit
face-patch investigation and any necessary solid-topology review.

The central deck #1781935 has seven edge-connected face sets. These are its
284-face outer shell and six cavity shells (67, 67, 63, 63, 52 and 52 faces),
explicitly referenced by `BREP_WITH_VOIDS`. They are **not seven detachable
parts**. All seven shells remain in one solid-body export, preserving its voids.
This is why the source-unit mode separates surface-model shells but never
breaks a solid into its bounding shells.

Two exact geometry matches also remain in this subset: floor #24444 versus
red-road #3786822, and floor #24644 versus blue-road #3808637. The geometry reuse
audit confirms them; source identities, appearances and placements remain
separate. This review does not remove overlapping source geometry or claim
appearance equivalence.

## Reproduce

The existing [CAD partition exporter](cad-partitions.md) now supports
`split_source_units: true`. This produces one work group per original solid
body or original surface-model shell, named `body-<source-id>` or
`shell-<source-id>`. It rejects non-boolean settings and combinations with manual
body rules, shell rules or body-group overrides. Expected signatures in the
source-pinned policy assert all 85 body/shell/face memberships.

From `rm-map-tools`, with a fresh output path:

```sh
ocpenv/bin/python python/cad_partition.py source/RMUC2027_V1.0.0.stp \
  --policy rules/partition-rmuc2027-terrain-equipment.json \
  --components rules/components-rmuc2027.json \
  --motion-profile rules/reviewed-motion-rmuc2027.json \
  --export --out out/terrain-review/bundle
```

This writes 25 complete product exports and 85 component exports. Each contains
compressed STEP, GLB and original placement/selection metadata. Native read-back
counts and tessellation checks apply to every component. The review verified
all 110 STEP archive round trips, all bundle checksums, exact source-face
coverage once per product, and equality of full/component geometry, normals,
materials and transforms. Original CAD remains authority.

The [review renderer](../benchmarks/2026-10-17-terrain-separation/render-review.py)
produces depth-tested images, component contact sheets and the complete placed
subset. It needs NumPy, Pillow, a C++ compiler and a component catalog from
`cad_components.py`. Example:

```sh
ocpenv/bin/python python/cad_components.py source/RMUC2027_V1.0.0.stp \
  --policy rules/components-rmuc2027.json \
  --motion-profile rules/reviewed-motion-rmuc2027.json \
  --out out/terrain-review/catalog.json
ocpenv/bin/python benchmarks/2026-10-17-terrain-separation/render-review.py \
  --bundle out/terrain-review/bundle --catalog out/terrain-review/catalog.json \
  --out out/terrain-review/renders
```

The overview uses original source placements in metres with a single Z-up to
Y-up conversion. Views use original colors with illustrative shading and a
blue-grey backdrop so white marking bodies remain visible. Output geometry,
indexes, environments and previews are reproducible scratch; retain the original
STEP, exporter source and selection policy after review.
