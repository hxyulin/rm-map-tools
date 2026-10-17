<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 equipment pipeline trial

The latest visually approved Base has **66,502 visual triangles per placement**,
133,004 across both Bases, and unchanged collision at 16,857 per Base. This trial
inventories the complete source hierarchy and tests reusable passes on the other
equipment. Source geometry and artwork remain DJI / RoboMaster property.

## Complete-field accounting

| Composition | Placed visual triangles |
| --- | ---: |
| Uniform native reference, all 116 work definitions | 8,311,552 |
| Substitute the approved Base and four terrain wall fills | 7,019,378 |
| Also substitute this equipment LOD trial | 3,805,082 |

The new equipment trials save **3,214,296 placed triangles**, 45.79% of the
previous experimental field composition. This ledger includes every occurrence;
it is not unique buffer storage, visible triangles after culling, or an installed
runtime count. Native meshing uses 0.4 mm linear / 0.25 rad angular throughout.
The original native Base at those settings is 709,354 per placement; it is
replaced, not added alongside the approved candidate. Wall-fill inputs and
placement multiplicities are checked against the earlier qualified report.
Projected 16-section road savings are excluded because that preview has not
replaced the complete road meshes in this composition.

## Results on other equipment

| Group | Native placed | Planar only | Planar + LOD |
| --- | ---: | ---: | ---: |
| Two Dart stations | 2,126,076 | 2,116,050 | 970,094 |
| Complete Rune | 1,393,258 | 1,393,192 | 478,828 |
| Two Outposts | 1,136,898 | 1,136,118 | 719,798 |
| Two Technology Cores | 664,492 | 660,398 | 306,858 |
| Twelve Energy Units | 534,216 | 534,216 | 338,304 |
| Ten fans | 406,660 | 406,660 | 406,660 |
| Two resource-area products | 374,928 | 374,562 | 213,602 |

Ancillary Dart components and small fixtures are included in the complete totals
but omitted from this short table. The selection contains 41 work definitions.
Together they fall from 6,654,472 to 3,440,176 placed triangles, **48.30% fewer**.
Planar skins alone save only 15,336 placed triangles; constrained LOD accounts for
most of the reduction. Per-definition savings are multiplied by source uses;
instancing itself is not called a triangle reduction.

The ten fans do not shrink: their source appearance is unresolved and the
conservative policy freezes it. No procedural palette is invented. Equipment
with unresolved face materials may likewise have substantial retained detail.

## Policy and interpretation

Process each original native shell independently, retaining reviewed component
paths and local source-shell identities. Planar skins retain holes/material
regions within 0.001 mm numerical plane/boundary tolerances. The LOD trial uses
0.25 mm nominal / 1 mm sampled quality, with native broad-planar-outline vertices
and larger-opening boundaries seeding locks. Chromatic and unresolved materials
retain original ordered source triangles. Smaller than 128-triangle shells keep
their native geometry. No interior, screw, hole, paint or LED classification is
inferred from size or color alone.

The exporter independently verifies triangle counts and chromatic position/color
equality. Changed shells receive end-to-end sampled checks on actual GLB data.
Six matched whole-product views compare the native, planar and LOD stages.
All **1,128 checked exported shells** pass, with a maximum sampled distance of
**0.99903 mm**. The largest relative foreground-mask difference across the
six-view group comparisons is **0.1513%**, on the Energy Unit. Whole-product
GLBs use a representative source occurrence's rotation converted to Y-up for
inspection; component source geometry and membership remain separate.
These are source-pose, flat two-sided diagnostics; they do not certify runtime
PBR, all moving poses or continuous Hausdorff/trim distance. Unresolved materials
retain the exporter's existing neutral preview fallback, with their unresolved
provenance still present in the GLB.

Base-specific bore filling, source-panel surgery, backing shells, light proxies
and texture baking still need new source/semantic bindings on these entities.
Their absence here is deliberate: transferring the whole sequence blindly could
close functional openings or change detector/light artwork. Collision and
scoring remain unchanged, and no candidate is installed automatically.

The next useful detailed targets are the Dart frame and deck, Outpost upper
cluster, and Rune's repeated arm/module shells. Resolve contextual appearance
on the fans before attempting color-dependent simplification there. Preserve
these generic candidates as the reference before adding source-bound closures,
surface-aware primitives or artwork textures.

[Reproduction and measured ledgers](../benchmarks/2026-10-17-equipment-pipeline/README.md)
include the complete inventory, per-shell checks, output checksums and matched
view metrics. Generated complete-product GLBs and images remain under
`out/rmuc2027-equipment-pipeline/review/`.

Validation: 338 Python tests run, 337 pass and one optional USD test is skipped;
documentation checks find no missing local links.
