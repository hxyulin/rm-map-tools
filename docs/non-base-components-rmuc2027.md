<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 outpost and rune component candidates

This continues the [whole-body component catalog](cad-components.md). Buff here
means the rune / energy mechanism (能量机关), not RFID footprints. The work uses
original source SHA
`a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0`.
It changes grouping metadata and produces isolated work files; installed
geometry, animation, physics, materials and collisions remain unchanged.

## Spatial grouping method

[rules/component-regions-rmuc2027.json](../rules/component-regions-rmuc2027.json)
contains 18 explicit boxes in original product-local millimetres, each with
expected source body IDs and evidence. Most boxes are the union of the manually
proposed group's vertex bounds, padded by 1 mm. Three outpost module boxes also
cover nearby source-shell envelopes.

`python/audit_component_regions.py` recalculates source bounds directly from the
original entity graph. A whole body is a candidate only when its complete vertex
box is within the region. A center inside the region is insufficient. The audit
separately reports straddling bodies, unknown bounds, unexpected/missing matches
and bodies excluded by an explicit reviewed motion filter. All 18 regions
reproduce their expected whole-body membership; all also intersect other,
straddling bodies. Matching the expected IDs validates a reproducible selection,
not a functional interpretation.

**Vertex bounds are not exact curved-surface AABBs.** They can omit extrema
between vertices. These boxes discover work candidates; they do not establish
clearances, collision envelopes or permission to cut a body. Work exports retain
the entire selected original body, including curved geometry outside its vertex
bounds. New groups remain `spatial-candidate` and have unknown physical roles.

## Outpost

Product #2603236 contains 43 body definitions and is placed twice. Its three
reviewed rotor-module groups retain five bodies apiece. The 28 other bodies now
have finer work groups:

| Selector | Bodies | Evidence / limitation |
| --- | ---: | --- |
| `outpost/fixed/lower-cluster` | 4 | Compact lower region, matching the existing fixed-motion profile |
| `outpost/fixed/column-cluster` | 3 | Main column region and adjacent pieces; functional labels remain candidates |
| `outpost/fixed/upper-cluster` | 20 | Box also contains all 15 rotor bodies; explicit `outpost.frame` motion filtering keeps them separate |
| `outpost/fixed/spanning-surface-model` | 1 | Original surface container #2601775, retained whole |

The spanning container is a `SHELL_BASED_SURFACE_MODEL` with **14 explicit source
shells and 3,966 faces**, not one indivisible solid. The three module boxes each
contain one nearby 688-face shell:

| Module region | Source shell | Faces |
| --- | ---: | ---: |
| `outpost/rotor/module-0` | #2498962 | 688 |
| `outpost/rotor/module-1` | #2527556 | 688 |
| `outpost/rotor/module-2` | #2556150 | 688 |

These shells surround the corresponding mechanical module regions, but spatial
proximity does not certify attachment or motion. Their parent container is fixed
in the existing simulator adapter; do not silently move the shells with the
rotor. Inspect their actual surfaces before deciding whether that binding needs
correction. The shell audit deliberately does not inherit the body motion filter.

## Rune / energy mechanism

Product #1354629 contains 160 body definitions. Repeated source face-count
patterns and spatial bounds identify ten ten-body arm candidates, arranged as
two banks of five. `bank-a/b` are local work labels, not team or facing identities.

| Selector | Bodies | Status |
| --- | ---: | --- |
| `rune/banks/bank-a/arm-0` through `arm-4` | 10 each | Repeated spatial candidates |
| `rune/banks/bank-b/arm-0` through `arm-4` | 10 each | Repeated spatial candidates |
| `rune/banks/bank-a/hub-cluster` | 19 | Spatial candidate |
| `rune/banks/bank-b/hub-cluster` | 20 | Spatial candidate; includes nearby body #228756 |
| `rune/spanning-surface-model` | 1 | Original surface container #1354072 |
| `rune/other-bodies` | 20 | Retained original bodies, not assigned functions |

Each arm's source face-count pattern is
`105, 101, 157, 121, 121, 157, 190, 34, 40, 40` (1,066 faces total).
This supports repeated mechanical subassemblies; it does not prove motion axes,
armor/light ownership or a complete arm's appearance.

The spanning surface model holds **1,063 separately referenced shells and 14,366
faces**. Arm boxes contain 87–94 shell candidates apiece, and hub boxes contain
50 each. Neighboring shells also straddle the boxes. Across all 18 regions,
83 shell IDs are contained by more than one region, including intentional
parent/child outpost-region overlap. These overlaps are explicitly reported.
Shells are not assigned to several work components or cropped to remove overlap.

The arm work files contain their ten mechanical bodies only. They exclude the
shared surface container, so a mechanical-only preview is not a complete visual
arm. Whole-shell extraction and reviewed ownership are the next finer boundary;
they are not implemented by this body-only exporter.

## Reproduce and inspect

From `rm-map-tools`:

```sh
ocpenv/bin/python python/audit_component_regions.py \
  source/RMUC2027_V1.0.0.stp \
  --plan rules/component-regions-rmuc2027.json \
  --motion-profile rules/reviewed-motion-rmuc2027.json \
  --out out/cad-audit/rmuc2027-regions.json
```

The component policy pins the region plan's hash. Catalog construction requires
its region audit to reproduce each spatial group's body set. Original source
body IDs and occurrence paths remain stable under these regroupings. The full
map still has 426 body definitions and 644 placed body occurrences, with 25
explicit manual groups. None of the rune's motion is newly classified.

Export representative work items with the component CLI and one selector:

- `outpost/rotor/module-0`: five solids, 3,107 source/native faces.
- `outpost/fixed/lower-cluster`: four solids, 1,061 source/native faces.
- `rune/banks/bank-a/arm-0`: ten solids, 1,066 source/native faces.

Their isolated STEP exports reparse with geometry/style records preserved, have
no dangling references and import into OCCT with matching face counts. Placement
sidecars retain all original instances. Review these mechanical selections and
the three outpost shell candidates before assigning finer functional ownership.

The follow-up [complete CAD partitions](cad-partitions.md) now export original
shell subsets as well as bodies. They include the larger Rune arm cover shells,
resolve arm/hub work ownership with an explicit priority, and retain all
remaining geometry in a named remainder. The discovery ambiguity above remains
a record of the earlier, narrower boxes; it is not geometry omitted from the
complete exports.
