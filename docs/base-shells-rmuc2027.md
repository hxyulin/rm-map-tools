<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Base planar skins and backing shells

The user visually accepted the [82,414-triangle detail candidate](base-aggressive-lod-rmuc2027.md)
and requested simpler shells. This experiment adds boundary-defined planar
patches, applies the current detail policy to the previously excluded crossbar,
and tests four native source-outline backing plates as a separate approximation.
DJI / RoboMaster retains ownership of source geometry and appearance. Original
STEP, installed assets, collision, scoring geometry and source membership stay
unchanged.

| Complete Base | Visual triangles | Two placements | GLB bytes |
| --- | ---: | ---: | ---: |
| Approved reference | 82,414 | 164,828 | 6,408,448 |
| Planar skins + crossbar LOD | 73,258 | 146,516 | 5,756,472 |
| Also use backing plates | 68,080 | 136,160 | 5,352,476 |

The plate-backed candidate saves **14,334 triangles (17.4%)**. The crossbar falls
from 18,456 to 10,494; the lower housing from 9,064 to 8,893; three tall covers
from 9,814 to 8,871; and the module frame from 4,643 to 4,571. Four backing shells
fall from 5,348 to **162** (30, 32, 32 and 68). The remaining 330 source members
retain exact rendered positions, normals and materials. All **2,822 light
triangles** retain exact decoded GLB positions, normals and materials, including
lights belonging to replaced covers. Collision remains 16,857 triangles per Base.

## What the representation changes

`cad_planar_shell.planar_skin()` finds connected nearly coplanar patches within
one material, using exact-position adjacency rather than a proximity weld.
Patches must lie within 0.001 mm of one fitted plane and have disjoint closed
boundary loops. It retains apertures, rejects nonmanifold patches and keeps
original positions for the remaining boundary vertices. Redundant boundary
subdivisions can disappear only if **every original point** on the resulting
chord is within 0.001 mm, preventing cumulative drift. VTK triangulates the
projected loops; area accounting and bidirectional samples reject mismatches.
Unresolved or non-saving patches retain input.

Accepted patches record a compact shared boundary-vertex table, loop indices,
material ids and plane frames. Interior tessellation vertices do not belong in
that vector representation. Source triangle membership remains available for
qualification and reproducibility. The generated full boundary IR stays in
ignored output; tracked measurement ledgers omit its coordinate payload and
record a checksum. This is groundwork for retessellating patches at selected
LODs, not a new complete STEP/B-rep model or a lossless claim.

The crossbar starts from the **approved hole-closed 18,456-triangle mesh**; it does
not revert to native detail and reintroduce the mounting row. Native broad-face
corners seed protected vertices, with unmatched corners recorded as neighborhood
fallbacks. The nominal metric is 1 mm and the sampled guard is 3 mm, increased
from this member's earlier 0.25 mm / 1 mm policy. Vertex guard repair produces
10,576 triangles; planar skins remove another 82. Final combined sampled distance
to that approved crossbar reaches **2.99909 mm**. This is not a claim of 3 mm
distance to every original STEP trim or a complete analytic crossbar shell.

## Explicit backing approximation

Each backing replacement is a **1.5 mm native-profile extrusion** from the source
face pinned in the [policy](../rules/base-shells-rmuc2027.json). Its native outer
wire is retained before tessellation/LOD; inner loops strictly narrower than
17 mm are filled. Native validity and volume accounting pass. The plate mesh
uses a separate 1 mm nominal / 3 mm sampled LOD against its derived profile.

These plates intentionally omit molded recesses, ribs and posts. Their distance
to the previous whole backing reaches **10.50–13.21 mm**, admitted under an
explicit **15 mm whole-backing sampled budget**. They do not inherit the
crossbar's 3 mm budget. The backing shape and source diffuse colour remain
separate source members rather than being removed because another member hides
them. Colors are source dark grey; no procedural palette or material inference
is introduced. Normal/colour texture bakes are not attached in this experiment.

The 73,258-triangle alternative retains the previous backing shells, allowing
independent review of this larger approximation. The plate candidate remains
available for visual judgment; it is not installed or promoted automatically.

## Visibility and appearance checks

A read-only 62-direction audit finds that 11,590 of the crossbar's 18,456 triangles
never own a pixel in isolated views; 12,889 never own one in assembled views.
Most module-backing triangles are hidden by the assembled equipment. These are
raster samples, not proofs of enclosure; no face is deleted solely from those
observations. The crossbar's main mesh component also has open/nonmanifold
incidence, so it cannot simply be treated as a certified opaque closed solid.

Eighteen assembled views and thirty-four isolated views compare both variants
against the approved Base at matched 1200² resolution. Maximum foreground-mask
difference relative to reference foreground is **0.07581%** without plates and
**0.07596%** with plates. Maximum whole-image RGB changes above 10/255 are
0.1523% and 0.1898%, respectively. The backing substitution alone changes at most
0.003282% of assembled foreground; isolated backs expose the deliberately removed
detail more clearly.

Green LED pixel masks remain identical in these views. Substantial red-mask
views change by at most 0.304% with plates. The underside's three reference red
pixels disappear. Geometry remains exact; these differences concern occlusion.
These are fixed source-pose, flat two-sided diagnostics, not runtime PBR,
arbitrary camera distance or all moving poses.

Validation: **331 tests run, 330 pass, one optional USD skip**. New cases exercise
planar loop storage, holes, protected materials, accumulated nonplanarity and
invalid policies. Full GLB composition independently checks lights, unselected
attributes, member metadata and counts.

## Remaining opportunities

The crossbar (10,494), lower housing (8,893), module frame (4,571), and three tall
covers (8,871 combined) remain the main shell targets. Broad panel skins now
have a reusable boundary representation; replacing deep folded returns still
requires explicit source panel/profile decomposition. The earlier three-profile
cover replacement lost returns by up to 135 mm and remains rejected.

After that, inspect raised lettering and shallow grooves individually for UV
colour/normal layers. Source-neutral geometry is not automatically decoration.
Use component-specific LOD and preserve source ownership so close-up equipment
and distant field scenery can choose different detail without changing collision.

[Reproduction and measurement ledgers](../benchmarks/2026-10-17-base-shells/README.md)
retain alternative compositions, native profile proofs and all sampled views.
