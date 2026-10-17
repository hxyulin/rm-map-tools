<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Remaining equipment: geometry opportunities

This analysis covers 17 source-bound work definitions: the complete Rune,
ten fans, twelve Energy Units, two resource mechanisms and two Tech Core tool
heads. They account for **1,645,224 placed visual triangles**, 53.5% of the
approved **3,075,154-triangle experimental field composition**. Source CAD and
appearance remain DJI / RoboMaster property. These diagnostics do not change
the approved field, collision, detectors or installed runtime packages.

## Measured opportunities

| Target | Current / definition | Diagnostic / definition | Uses | Placed saving |
| --- | ---: | ---: | ---: | ---: |
| Fan, scoped unstyled LOD | 40,666 | 9,618 | 10 | 310,480 |
| Energy Unit, angular tessellation + cavity omission | 28,192 | 16,916 | 12 | 135,312 |
| Tech Core tool head, angular tessellation | 104,561 | 71,297 | 2 | 66,528 |
| Resource mechanism, angular tessellation | 106,155 | 84,456 | 2 | 43,398 |
| Complete Rune, angular tessellation | 478,828 | 656,873 | 1 | Regression: 178,045 |

The first four disjoint trials total **555,718 fewer placed triangles**. Adopting
those choices would produce an arithmetic field total of **2,519,436**,
18.1% below the approved reference. All listed diagnostic meshes were generated
and reviewed at fixed poses; no new complete-field package is assembled or
promoted. This is not a promise of savings from the further proposed shape fits.
Instancing already retains source occurrences; repeated uses amplify a mesh
improvement but sharing storage alone does not remove placed triangles.

## Fans: the clearest immediate win

All 1,607 original fan faces lack surface fill colour. The earlier
[source appearance audit](appearance-compositions-rmuc2027.md) also established
that the source supplies no assembly-parent surface style to inherit. The
neutral preview is a deliberate fallback, not a missing recovered parent colour.

The generic pipeline froze the entire unstyled fan. Explicitly permitting this
one model's geometry to use the existing 0.25 mm nominal / 1 mm sampled LOD
reduces it to **9,618 triangles**, while keeping the exact fallback material
and unresolved provenance. Actual exported sampled distance reaches **0.95809 mm**;
maximum foreground difference across 14 views is **0.0833%**. No hole is
intentionally filled and no source component is intentionally removed.

The native model has 24,058 planar and 16,577 cylindrical triangles, with only
31 spline-surface triangles. This supports future panel/analytic meshing rather
than treating it as an inherently complicated freeform shape. The 102 discovered
small bores remain potential local-detail work, not automatic closure choices.

## Energy Units: a proven interior and an overbroad protection policy

Of 28,192 current triangles, **21,436 (76.0%)** are frozen: 11,650 because the
authored cream exceeds the conservative RGB-range threshold, and 9,786 because
their source appearance is unresolved. The cream colour does not itself establish
a light or artwork role. Keep both colours/provenance while selecting geometry
policies by reviewed source part.

The single valid native solid has an enclosed **206-face inner cavity shell**.
Native finite-surface difference leaves zero area outside the retained outer
solid; minimum boundary clearance is **0.200000 mm**. Retained exterior native
faces are identical by shape identity. Its current shell costs 4,624 triangles:
**55,488 across twelve copies**. Cavity-only omission retains exact exterior GLB
positions, normals and full materials, and produces identical images in all
14 diagnostic views. It does not change mass/physics or the source CAD.

Separately, changing the native angular request from 0.25 to 0.6 rad at the same
0.4 mm linear request retains all 1,424 faces and face styles and gives 21,308
triangles. Omitting the qualified 4,392-triangle cavity in that trial gives
**16,916**, not 21,308 minus the different current-mesh cavity cost. The exterior
sampled deviation to native reaches **0.44077 mm**. Angular+cavity images match
angular-only exactly; the angular change itself reaches **0.2513%** foreground
and **1.4856%** whole-image RGB-change fractions, so inspect its close-up shading.

Further opportunities are source-profile meshing of the two flanges, axial body
and groove/rib regions. The outer envelope is approximately 95 × 150 × 95 mm.
Native costs include 15,537 planar, 15,288 cylindrical and 9,677 torus triangles;
the many small fillet/trim patches matter as well as radial resolution. A simple
spool proxy remains a proposal requiring finite-profile and appearance checks.

## Resource mechanism: unstyled machinery and one dominant housing

**80,294 of 106,155 current triangles (75.6%)** are unstyled and frozen. Native
shell 4 accounts for **52,142** current triangles, 36,016 of them unresolved,
within an approximately 146 × 329 × 216 mm envelope. Start with that source-bound
cluster and repeated fittings, preserving material provenance and functional
clearances rather than freezing every unstyled triangle.

The source has 147 small-bore candidates; 30,188 current placed triangles belong
to native shells no larger than 17 mm. Neither number is an authorized removal
budget. Three multi-shell solids fail the valid outward-shell test, so no
resource cavity/interior deletion is qualified. The 84,456-triangle angular
trial keeps all 4,281 native faces and styles; sampled native deviation reaches
**0.36854 mm**, with maximum foreground difference **0.1415%**.

## Tech Core tool head: a protected plate and fragmented source groups

The largest current native shell is entirely authored copper/brown:
**13,056 triangles**, within 155 × 434 × 9.3 mm. The colour policy froze it even
though it is a plate-like region; colour alone does not establish optical
function. Inspect its finite outline, holes and relief for a profile-based
replacement while retaining its source colour. Two other large shells cost
7,976 and 5,636 triangles.

The 390 original source shell groups import as **1,600 native shells**. In the
current mesh, 1,505 native fragments have fewer than 128 triangles and together
cost 12,517 triangles per tool head. These can include face fragments and must
not all be classified as independent fasteners. Bind imported faces back to
original source groups before coalescing compatible patches; preserve motion,
material and functional boundaries. Total current cost in native shells no
larger than 17 mm is 42,822 placed triangles.

The angular trial retains all 3,495 source faces/styles, reducing the tool head
to **71,297**. Actual native sampled deviation reaches **0.43095 mm** and maximum
foreground difference is **0.0164%**. Source colours are authored CAD colours;
there is no debug recolouring or missing parent palette to fix. There are 35
complete small-bore candidates for later local review.

## Rune: local hardware and optical panels, not global coarsening

The ten arm work groups contribute **381,212** current triangles; both hubs
44,632 and support/shared 52,984. Coarser native tessellation grows the complete
model to **656,873**, so retain the existing arm/hub meshes. The support alone
does modestly improve to 49,021; it is not included in the four-trial saving above.

Across these groups, 109,652 current triangles lie in native shells no larger
than 17 mm, and 3,368 complete small-bore candidates are discovered. About 41.2%
of current triangles are frozen by the broad colour policy. A representative
arm's two largest shells include 6,298 red-material triangles; they need explicit
light/target/artwork classification before flat-front or texture substitutions.

Prioritize repeated fastener detail, backing/housing profiles and individual
light/target panel representations. Preserve optical outlines and scoring/motion
ownership; do not remove every small shell or fill every discovered hole.
Original native face costs are dominated by cylinders (679,542 triangles) and
planes (615,638). Those native costs are not residual LOD triangle counts and
cannot be subtracted from the approved mesh as a saving estimate.

## Recommended order and evidence limits

Promote a reviewed **fan-only geometry-policy exception** and **Energy cavity
omission** first, then evaluate the three cheaper native tessellations. Next,
scope source-profile/primitive edits on the Energy Unit and resource housing,
followed by the tool-head plate and Rune optical/hardware subassemblies.

All distances are deterministic mesh samples, not continuous Hausdorff or native
trim certificates. Views are flat two-sided diagnostics at one source pose,
not runtime PBR or all-motion guarantees. Only the Energy cavity has qualified
native enclosure evidence; no general hidden-geometry removal is inferred from
these renders. [Reproduction and compact ledgers](../benchmarks/2026-10-17-equipment-opportunities/README.md)
retain source/output hashes, native feature costs, material-policy costs,
negative cavity results and all trial metrics. Generated meshes and interactive
comparisons remain under `out/rmuc2027-equipment-opportunities/`.

## Selective Rune detail candidate

The [selective Rune benchmark](../benchmarks/2026-10-17-rune-detail/README.md)
reduces the complete Rune from 478,828 to **407,696** triangles (71,132 saved),
with exact coloured/unresolved GLB attributes and a 5 mm chromatic-neighbour
lock. It is a review candidate: rear housing occlusion changes slightly despite
unchanged colour geometry. It does not replace installed assets or collision.

## Rune flat-back candidate

The user-approved [flat-back pass](../benchmarks/2026-10-17-rune-skin/README.md)
replaces the detailed arm backs with native-profile flat dark panels and removes
interior/rear surfaces and tiny neutral hardware. It reduces the Rune further
to **255,621 triangles**, cumulatively 223,207 (46.6%) below the generic candidate.
Large windows and separate arms survive; hubs/support keep their complete earlier
LOD geometry. This supersedes the open-back intermediate and remains a visual
review candidate, with collision and installed packages unchanged.

## Rune front-detail removal

The [smooth-front extension](../benchmarks/2026-10-17-rune-skin/README.md#smooth-front-candidate)
replaces front mounting bores and shallow concentric relief with authored-colour
native-profile panels. It also removes tiny cylinder-shell details and the newly
occluded interior. The complete Rune drops to **153,586 triangles**, another
102,035 saved beyond flat backs and 67.9% below the generic candidate. Flat backs,
large openings and separate arms survive; hubs/support remain unchanged. The
experimental field composition is **2,343,812 placed visual triangles**. Source
CAD, collision, detectors and installed assets are unchanged.
