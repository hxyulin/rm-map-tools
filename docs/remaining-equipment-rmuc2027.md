<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 remaining equipment partitions

The [remaining-equipment policy](../rules/partition-rmuc2027-remaining-equipment.json)
extends the [source partition exporter](cad-partitions.md) to the Technology Core,
resource area, Dart station and Energy Unit. It uses the same original RMUC
2027 V1.0.0 source SHA, retains complete source geometry, and installs no runtime
motion, collision, scoring or light bindings.

## Solids, shells and separation

The RMUC 2027 source has 426 body definitions: 406 `MANIFOLD_SOLID_BREP`,
11 `BREP_WITH_VOIDS` and nine `SHELL_BASED_SURFACE_MODEL` containers. Thus it
contains 417 solid bodies and nine surface-model containers, not nine individual
shells. A surface-model container can contain hundreds of original shells.
Solid bodies also have bounding shells; a shell describes connected surfaces
and can be open or closed. Neither representation establishes whether something
is static, moving, decoration or collision geometry.

The ground and terrain are mostly solids, while equipment often mixes solids
and surface models. Original bodies and shells are straightforward lossless
selection units. A useful mechanical boundary is not always a source topology
boundary: the Outpost cover required a face patch, and independent arm-link
membership still needs review. Easy export is not proof of articulation.

Other straightforward source-product selections include the drone landing
pads, fortress structures, fans and grilles, base/outpost footings and terrain
assemblies. Internal parts may still be fused even when the complete source
product is independently selectable. Generated exports and index caches can be
rebuilt from the retained original STEP and source-pinned policies.

## Source and work boundaries

| Source product | Source bodies | Source surface shells | Source faces | Work exports |
| --- | ---: | ---: | ---: | --- |
| Technology Core #1751926 | 1 surface model | 418 | 4,892 | Pedestal/shoulder, arm/shared, tool head |
| Resource area #3998852 | 44 solids + 1 surface model | 9 | 4,377 | Structure, mechanism, marking plates |
| Dart station #3749800 | 64 solids + 1 surface model | 371 | 25,090 | Frame, guide rails, door candidate, deck/shared hardware |
| Energy Unit #4056216 | 1 solid | 0 | 1,424 | Complete unit |

These are **11 disjoint work groups**, plus four complete product exports.
Source faces are assigned exactly once within each product. The full exports
include the same geometry and colors as their parts, at the original rest pose.

### Technology Core

The source is a surface model containing 418 original shells, not a single fused
solid. Whole-shell vertex envelopes identify a pedestal/shoulder group (13 shells,
769 faces) and a tool-head group (390 shells, 3,495 faces). The remaining 15 shells
(628 faces) stay together as `arm-and-shared`. No shell or face is cut to fit a box.

These broad work groups are not individual robot arm links. Shoulder and shared
hardware ownership, tool interfaces and any future articulation still require
review. The older 2026 joint bindings are not transferred. These source surfaces
are not claimed to be closed solids.

### Resource area and Energy Unit

The structure is the original 80-face solid #3957038. Two separate eight-face
bodies #3957486 and #3957758 form a `marking-plates` candidate: they are thin and
extend away from the compact mechanism. They remain exported geometry; this
classification does not remove their collision or replace them with textures.

The mechanism retains all other 41 solids and all nine surface shells (4,281
faces), including the source's lettering and small details. The separate Energy
Unit source product remains its own complete model. This CAD grouping does not
define a referee Supply Zone footprint or imply all supply equipment belongs to
this resource-area product.

### Dart station

The frame retains the large fused body #3098185, its four foot blocks, their four
cover shells and the crossmember shell #3460141 (10,231 faces). The long mirrored
358-face bodies #3301978 and #3317722 form `guide-rails` (716 faces).

`door-candidate` contains the raised panel body #3379458, nearby carriage
fasteners/brackets, two panel cover shells and four 304-face carriage shells
(15 solids, six shells, 3,544 faces). This is a proposed attachment grouping, not
an established movable door with verified travel. The nearby full-width
crossmember is deliberately retained with the frame instead of assigned by a
broad door box. The other 42 solids and 360 shells remain in
`deck-and-shared-hardware` (10,599 faces); small shared pieces are not guessed
into a moving owner. The fused frame can still contain details that need a
future exact face-patch selection.

The Dart source imports one zero-area native face. The exact STEP retains it.
The mesh exporter reports its measured area and surface type instead of
inventing triangles for it. A native face with nonzero area that cannot be
meshed still fails export. Unmeasured or mismatched degeneracy counts also fail.
This distinction changes no source face records or STEP topology.

## Reproduce

From `rm-map-tools`, with a fresh output path:

```sh
ocpenv/bin/python python/cad_partition.py \
  out/rm2027/RMUC2027_V1.0.0/source.npz \
  --policy rules/partition-rmuc2027-remaining-equipment.json \
  --components rules/components-rmuc2027.json \
  --motion-profile rules/reviewed-motion-rmuc2027.json \
  --export --out out/cad-components/remaining-separation
```

The original STEP can replace the optional index cache. Each product has
`full/{source.step.gz,selection.json,visual.glb}` and a `components/` directory
containing its work groups in the same format. `partition.json` records complete
source body/shell/face ownership, and `manifest.json` records file hashes,
read-back native counts, mesh statistics and group signatures. Source units and
placements follow the [existing partition coordinate contract](cad-partitions.md).

The optional `body_rules` policy field assigns explicit original solid-body IDs
without modifying the shared component catalog. Empty, duplicate, unknown,
surface-container or multiply assigned body selectors are rejected. Body and
shell group names remain constrained to safe paths within their source product.
