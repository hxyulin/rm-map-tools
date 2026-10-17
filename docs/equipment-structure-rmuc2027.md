<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Dart frame and Outpost upper detail LOD

After committing the approved Base/equipment work as `05af970`, this experiment
targets native shell 1 in the source-bound Dart frame and Outpost upper cluster.
CAD/appearance retain DJI / RoboMaster ownership. Source STEP, collision,
detectors and installed runtime packages are unchanged.

| Visual triangles per placement | Approved | Selected candidate | Saving |
| --- | ---: | ---: | ---: |
| Dart frame component | 333,728 | 83,468 | 75.0% |
| Outpost upper-cluster component | 194,120 | 79,416 | 59.1% |
| Complete Dart-station source product | 485,047 | 234,787 | 51.6% |
| Complete Outpost source product | 359,899 | 245,195 | 31.9% |

Both source products are placed twice. The selected pair removes **729,928
placed triangles** and brings the [experimental complete-field composition](equipment-pipeline-rmuc2027.md)
from **3,805,082 to 3,075,154**, a further **19.18%** reduction. The accounting
retains all original occurrences and excludes projected road savings. It is not
an installed-runtime, culled-frame or unique-storage count. Source footings and
ancillary Dart products remain outside these complete source-product counts and
are retained separately in the whole-field ledger.

## Why the previous meshes remained expensive

The generic 1 mm complete-shell check fell back to planar input on the two main
shells: the Dart trial reached 1.725 mm, the Outpost trial 1.022 mm. This discarded
otherwise substantial reductions. The new policy uses the same **1 mm nominal /
3 mm sampled** visual budget as the approved aggressive Base, with native
outline-corner protection on broad faces. It starts from original native
0.4 mm / 0.25 rad tessellation rather than accumulating error on earlier LOD.

The Dart main shell falls from 315,700 to **65,440** triangles. The selected
Outpost main shell falls from 166,405 to **51,701**. All **100 other Dart shells**
and **27 other Outpost shells** retain exact rendered positions, normals and
full materials. In the changed shells, **33,401 Dart** and **34,299 Outpost**
chromatic/unresolved triangles likewise retain exact rendered attributes.
No part, bore, panel, light or artwork is deliberately removed.

The initial Outpost trial had 78,420 component triangles. Locking 5,509 vertices
within 3 mm finite distance of its chromatic geometry adds 996 triangles and
protects nearby dark detail. The selected 79,416-triangle component restores
identical green masks in all complete-product views. This proximity policy is
not a semantic LED classifier or an all-motion occlusion guarantee.

## Qualification and remaining visual differences

Actual GLB bidirectional sampled distances against the original native shell
reach **2.87277 mm for Dart** and **2.64806 mm for Outpost**, with 196,608 sampled
points per comparison. The guard is sampled, not continuous Hausdorff or trim
certification. Export checks include normals and complete material records,
not just source color labels or pre-export mesh arrays.

Eighteen matched views cover each complete source product, changed component
and changed shell. Maximum foreground-mask difference relative to approved
foreground is **0.0454% / 0.0694%** for the complete Dart/Outpost products and
**0.0675% / 0.3372%** for the changed components. The isolated Outpost shell
reaches **0.4979%**. These use flat two-sided diagnostic shading at the source
pose, with source occurrence orientation converted to Y-up.

Exact light geometry does not imply identical occlusion. Complete Outpost green
masks match; isolated component/shell views gain up to 28 green pixels. Red
visibility still changes: the complete-product top view loses 52 red pixels and
gains two, from 173 reference red pixels. Other substantial complete-product red
views differ by up to 5.44%. Inspect the top and underside as well as normal
oblique views before promoting the candidate. No runtime PBR or all articulated
pose guarantee is claimed.

## Next source-detail opportunities

The read-only audit finds **270 complete small-bore candidates in the Dart
main shell** and **197 in the Outpost main shell**, with radius at most 8.499 mm
and depth at most 25 mm. No hole is filled. Native source triangle cost by family:

| Main shell | Planes | Cylinders | Torus | Cones | Spheres |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dart | 140,950 | 119,039 | 25,020 | 14,513 | 11,400 |
| Outpost upper | 80,094 | 75,572 | 0 | 9,168 | 982 |

These are original native costs, not the residual candidate composition. The
remaining native families and highest-cost finite faces are in the audit ledger.
The next useful step is local qualification of fastener bores and shallow
panel details, followed by source-bound planar/analytic replacement or artwork
bakes. Size/surface type alone does not establish that a feature is disposable.

[Reproduction and compact ledgers](../benchmarks/2026-10-17-equipment-structure/README.md)
include both initial and colour-protected trial inputs. Generated selected
complete-product GLBs and all review images are under
`out/rmuc2027-equipment-structure-final/`. The user visually approved the selected
candidates; they remain separate from installed runtime packages. The pre-commit
Python suite passed 337 tests with one optional
skip; these new benchmark scripts additionally execute geometry, attribute,
count, source-hash and visual checks, without changing library code.
