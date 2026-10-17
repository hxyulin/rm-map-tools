<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Base top mounting row

The user approved the [18,626-triangle crossbar](base-structure-audit-rmuc2027.md)
and requested removal of its visible top mounting holes. The row is pinned to
source face **#4202749**, inner wires 2–13, in Base source unit #4268930. A matching
row on the underside is not selected. All source CAD and appearance remain owned
by DJI / RoboMaster.

| Visual representation | Before | After |
| --- | ---: | ---: |
| Crossbar | 18,626 | 18,456 |
| Complete Base definition, composed with approved lights/housing | 115,818 | 115,648 |
| Two placed Bases | 231,636 | 231,296 |

The local edit removes 261 triangles and adds 91 cap triangles, saving **170**.
All 18,365 untouched crossbar triangles retain exact ordered corner positions and
source diffuse values. Other Base members, smooth green-optic normals, collision
(16,857 triangles per Base), detector definitions and installed assets are unchanged.
The complete-Base counts describe inspection composition, not a newly installed
field package.

## Native qualification and local geometry

The ten inner holes are complete coaxial stepped channels with 4.2 mm throats
and 7.5 mm counterbores. The existing straight-bore pass already capped their
throats, leaving blind recesses. The new `close_selected_axial_bores()` traces
native edge incidence through inward cylindrical walls and complete annular
shoulders to exactly two planar circular mouths. It also supports qualified
inward conical transitions for other callers. Full angular coverage, coaxiality,
strict width below 17 mm, valid rebuilt mouth faces and retained-face identity
are checked. Blind, intersecting and unsupported channels reject the selection.

Closing these ten whole channels subsumes ten of the previously approved 66
straight closures. The other 56 closures are checked against their original wall
identities. They are not silently lost or counted twice. Retained source faces
carry their original diffuse values through returned native indices.

The two end apertures encounter forward-facing internal cone/boss geometry;
they fail complete-channel qualification. Their visible 7.5 mm mouths are capped
using their existing mesh rims while retaining their interior geometry. No claim
is made that those interiors have been removed. This is a visual cover with
intentional nonmanifold cap/side-wall incidence; it is not used for collision.

A whole-crossbar rebuild would produce 25,364 triangles after its sampled LOD
checks, so that candidate is rejected. `cap_selected_recess_mesh()` instead edits
the approved crossbar locally. Facets removed from each of the ten qualified
recesses must lie entirely inside its finite native envelope, expanded radially
by 1 mm for the approved LOD. They must form one connected patch with manifold
incidence. Its single convex mouth loop must lie within 0.001 mm of a native end
plane. Existing rim positions and adjacent material are retained; caps use a
center fan with matching winding. Mixed materials, disconnected surfaces, open
walls and unresolved rims reject the edit. The two explicitly requested
`retain_interior` features only add mouth caps and delete no triangles.

The 1 mm envelope margin is a selection allowance around the already approximate
mesh, not a new whole-member LOD error threshold. Original CAD, hidden ownership
and independently moving parts are not inferred from visibility.

## Validation and reproduction

The explicit [selection policy](../rules/base-mounting-row-rmuc2027.json) pins the
component SHA-256 and distinguishes complete channels from end-mouth covers.
The [benchmark](../benchmarks/2026-10-17-base-mounting-row/README.md) retains native
proofs, the rejected rebuild, exact unchanged-triangle checks and matched renders.
Seven isolated views include a view along the top cover normal; eighteen
whole-Base views compare the approved crossbar with this successor. These are
fixed source-pose diagnostic renders, not runtime PBR or motion validation.

Validation: 314 tests run, 313 passed and one optional USD skip. Maximum whole-Base
RGB change above 10/255 is 0.01083% of image pixels; foreground masks are identical
in all eighteen sampled views. Documentation links and whitespace checks pass.
