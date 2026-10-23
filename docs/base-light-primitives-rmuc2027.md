<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Base light primitives and hidden overlap

The approved [gap closure and LED LOD](base-gap-led-rmuc2027.md) is committed in
`16a2a86`. This experiment derives further visual candidates. It changes no
original STEP, runtime package, collider, motion binding or gameplay detector.

## When overlap is useful

A visual light surface may extend inside an opaque housing if the extra area is
occluded. It must not emerge through the other side or outside the bezel.
Coplanar overlapping faces can flicker; an inward offset can avoid that, provided
it does not hide the desired light or leave visible seams. The complete assembly
must be inspected, including rear and oblique views. Pixel tests are not a proof
that all future moving poses keep an overlap hidden.

Collision has separate requirements. Exterior contact geometry matters, and
overlapping collision meshes can generate redundant contacts. A visual quad is
not automatically a suitable replacement collider. These candidates keep the
approved **16,857-triangle collider unchanged**. Solid fusion and removal of
internal collision faces would be a separate physical operation.

## Long strips become exact front quads

Three explicit source faces are rectangle fronts:

| Source unit | Source front face | New triangles |
| --- | --- | ---: |
| #4314593 | #4295960 | 2 |
| #4353403 | #4334742 | 2 |
| #4392221 | #4373580 | 2 |

The [policy](../rules/base-light-primitives-rmuc2027.json) pins these source ids;
normal direction or color alone does not authorize another part's replacement.
The planar fronts are 439.2 × 23.4 mm. The final rectangles use no inset or padding.
They replace the old red source surfaces of those members, including backing
and mounting detail. The source front outline stays rectangular; removing the
other red surfaces is an explicit visual approximation, not a lossless claim.
The three members' red triangle count falls from 2,522 to six.

The reusable `cad_light_primitives.rectangle_cover()` computes minimum-area
calipers on a caller-selected planar point set. Its general enclosing rectangle
can overfill source trims; the caller must review that excess. It rejects plane
residuals above 0.0001 mm. The exact source front selection above does not rely
on a heuristic bounding rectangle hiding its excess behind another member.

## Why the raised lights are not single quads yet

The six raised module lights have visible side surfaces and finite shaped ends.
One chosen front quad loses light at oblique angles. Independent source-plane
rectangle covers leave dark seams when their curved joins are omitted. An
oriented enclosing box has only twelve triangles but exposes extra red areas
outside bezels and through rear gaps. These three strategies are rejected.
Hidden overlap is allowed; those exposed areas violate its constraint.

For those module lights and ten small red source parts, the final candidate
retains source-derived geometry with locked material borders. It requests a
0.25 mm meshoptimizer metric and a separate 0.5 mm bidirectional sampled guard,
refining failed regions. Inputs are the original audited source red surfaces,
not another reduction of the accepted light mesh. Source colors do not change.
The small red parts are selected by source appearance for this visual experiment;
they are not newly classified as functional LEDs from color alone.

The module lights fall from 580–606 to 210–282 triangles each. Their visible ends
and side surfaces remain geometry. A shaped extrusion or texture-masked proxy
may reduce them further, but neither is asserted to work by this experiment.

## Green optic: a clipped icosphere cap

Source faces #4072327 and #4072367 are spherical supports on source unit
#4072376. Fitting their original source vertices, with local rebasing, gives a
**40 mm radius sphere** and a maximum vertex radial residual below 0.00001 mm.
This is a source-vertex support fit, not a fit to the shaded preview.

A native-mesh boundary discovery welds position keys at 0.00001 mm to identify
the aperture loop. The plane fit uses original coordinates, not the rounded
keys. The sphere axis and aperture plane are retained in the report. The mesh
is clipped one millimetre behind that plane. Its rear remains open: exporting a
whole green sphere would risk showing the rear through the housing.

`icosphere()` generates an outward-wound unit template with 20 × 4ⁿ triangles.
`clip_halfspace()` clips its placed triangles to the retained cap. Intersections
remain on the triangular chords, rather than being pushed outward onto the
sphere. The recommended level-2 template has 320 full-sphere triangles and
**90 retained cap triangles**, down from the approved 326.

The cap has at most 0.7102 mm inward deviation from the fitted sphere's support.
This is obtained from the closest mesh point to the center; all vertices are
inside/on the sphere to numeric tolerance. Every triangle remains on the retained
side of the rear clipping plane. These are sphere/plane constraints, not a
continuous finite-trim or housing-occlusion proof.

The export uses normalized radial vertex normals for the green primitive. Other
surfaces retain their flat normals. Source diffuse colors, emission settings and
other material parameters are unchanged. Independent GLB inspection confirms
radial normals within 3e-8 component error. The diagnostic renderer interpolates
those same normals; it is a diffuse renderer, not the application's PBR renderer.

The 34-triangle clipped level-1 alternative loses 8.55% of green foreground in
the front close-up and is rejected. The 90-triangle cap changes ten green pixels
out of 569,481 in that view (0.00176%), and 1.15% in the oblique close-up. The rear
comparison has no new green pixels.

## Counts and verification

| Per Base | Approved | Recommended |
| --- | ---: | ---: |
| Long strip red surfaces | 2,522 | 6 |
| Raised module red surfaces | 3,552 | 1,454 |
| Small red source parts | 1,560 | 1,272 |
| Green optic | 326 | 90 |
| All red/green surfaces | 7,960 | 2,822 |
| Whole visual | 142,120 | 136,982 |
| Collision | 16,857 | 16,857 |

Light geometry falls 64.5%; the whole visual falls 3.6% because all **134,160
non-light triangles remain byte-exact**. Two placed Bases share the definition:
273,964 placed visual triangles and 33,714 placed collision triangles.

Independent serialized checks compare every non-light position, color, source
face id and unit id, all source-unit material palettes and exported green normals.
Eighteen whole-assembly source-pose views and eleven in-situ close-ups retain
surrounding opaque geometry. The recommended model changes at most 0.01257% of
whole-image RGB pixels above 10/255. Red foreground differences reach 1.76% of
visible red pixels in the worst whole view. These are sampled source poses, not
complete occlusion, all moving states or runtime bounce validation.

**300 Python tests run: 299 passed and one optional USD skip.**
Reproduction and measured evidence
include the rejected box, planar-cover and coarse-sphere trials.
