<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 Base geometry analysis

The original RMUC 2027 Base is **709,354 triangles per definition**, with two
placed uses (1,418,708 placed triangles) at native 0.4 mm / 0.25 rad meshing.
The stage-one hierarchy already references the same Base definition twice;
this is not two independent geometry payloads. This investigation changes no CAD,
installed runtime asset, motion or scoring bindings. The earlier
[Base interior audit](base-interior-audit.md) concerns the older source releases;
its reconstruction and triangle counts are not this 2027 baseline.

## Source structure and cost

`base/source-model` retains 16,811 original source faces, split across 26 solid
bodies and 314 original surface-model shells. All 340 units have disjoint face
ownership and together cover every source face exactly once. Native STEP transfer
identities bind all original face IDs bijectively to the imported faces; native
record count and face types are checked. Native face ordinals remain scoped to
the component STEP checksum, not a portable source identity.

The Base is still one reviewed work part. Separating a source body or shell is
not yet a mechanical/motion classification. The following labels describe the
inspection renders only:

| Source unit | Inspection description | Triangles |
| --- | --- | ---: |
| Solid #4527988 | Lower outer housing | 165,672 |
| Solid #4268930 | Top crossbar | 144,438 |
| Solids #4314593, #4353403, #4392221 | Three tall covers | 113,292 total |
| Shell #4756187 | Small module back shell | 43,320 |
| Shell #4594338 | Module frame | 30,441 |
| Shells #4664029, #4693907, #4723785 | Three module backing shells | 55,452 total |

The two largest units contain 43.72% of all triangles. Solid units account for
511,274 triangles; surface-model shells account for 198,080. Only 52,333 triangles
(7.38%) are in whole units whose largest dimension is at most 20 mm. Tiny
standalone hardware is therefore only part of the problem: many tiny features
are embedded in large bodies.

## What makes the meshes dense

Cylindrical faces account for 301,189 triangles (42.46%), planes for 297,772
(41.98%), cones for 54,524, B-spline surfaces for 26,384 and tori for 24,082.
Small cylindrical features with radius at most 3 mm alone account for 262,099
triangles (36.95% of the Base); at most 2 mm accounts for 202,853. These are
surface-radius categories, not proof that each feature is a removable screw hole.

The lower housing's two densest planar faces are original source #4449640 and
#4452563: 19,365 and 18,454 triangles. Native trim inspection finds 353 and 332
inner wires, with 93 and 137 outer-wire edges. The inner trims remove about
13.48% and 14.35% of each outer profile's area. Thus even a flat face can be very
expensive because of holes and detailed outlines; planar instancing alone does
not eliminate that finite trim topology.

For scale, a 3 mm-radius circle sampled with 12 equal chords has about 0.102 mm
maximum radial chord error; 16 chords gives about 0.0576 mm. The native analytic
curve is already known, so it needs controlled sampling rather than a new fit.
Those curve bounds do not certify an entire face or solid: shared-edge samples,
trim coverage and resulting collider integrity still need validation.

This suggests two complementary source-level passes: feature-specific tessellation
for small curved surfaces, and selective removal/filling of reviewed nonfunctional
bores and recesses together with rebuilding their planar backing. Functional
openings, panel outlines, armor detection surfaces and LED strips need explicit
protection. The existing [wall-fill pass](cad-wall-fill.md) is useful infrastructure,
but filling every inner wire on these large faces would close real openings.

## Visibility and reuse findings

Twenty-six two-sided orthographic views at 1600 × 1600 pixels cover twelve
azimuths at 15° and 45° elevation, plus top and bottom, at the original source
pose. They observe 146,085 distinct triangles; 563,269 (79.41%) are never the
frontmost sampled triangle. This ranks inspection opportunities, **not removable
geometry**. Unobserved triangles can be occluded, subpixel or edge-on, and no
opened/moving pose is represented. Actual removal needs source containment and
motion-aware tests, retaining the complete exterior and scoring/light surfaces.

A frame-normalized source-graph audit finds 51 candidate reuse groups with 132
additional unit uses, representing 23,564 potentially redundant triangle-payload
uses. Its 1e-5 mm point and 1e-9 direction quantization is candidate discovery,
not verified incidence, face correspondence or material equality. It is not a
compressed storage result. Instancing those units would preserve every placed
triangle; its current conservative hits are smaller than the feature-detail cost.
The prior finite-patch pass already accepts 4,102 Base planar faces, independently
of this complete native baseline.

## Recommended order

1. Start with the separately identifiable top crossbar #4268930. Classify small
   bores/countersinks and seams, tessellate native curves at controlled quality, and
   preserve its outer envelope and artwork. It contains 144,438 triangles.
2. Apply the same tools to lower housing #4527988, with explicit protected
   openings and selected trim loops. Together these first two source units hold
   310,110 triangles; this is a target cost, not a promised saving.
3. Give module fronts, LED strips and backing shells separate protection and LOD
   policies. Source renderings show substantial mounting/recess detail behind
   small module faces. Preserve the source light-bar geometry and appearance.
4. Validate hidden-detail candidates across reviewed Base poses before deletion.
   Reuse verified whole-unit geometry as a separate storage optimization.

No reduction target is asserted until those native candidates are built and
checked. Evidence and reproduction
include full Base views, twelve isolated source units, spatial density plots and
sampled visibility by unit. Diagnostic colors preserve resolved source diffuse
values; 69,440 triangles across 1,433 faces retain unresolved local diffuse
appearance and use the existing tagged neutral fallback. No new finish is inferred.
