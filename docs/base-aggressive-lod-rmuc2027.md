<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Aggressive Base detail LOD

After visual approval of the [15,832-triangle housing](base-housing-local-lod-rmuc2027.md),
this experiment extends local vertex constraints across fourteen heavy source
members. DJI / RoboMaster owns the source geometry. The native STEP, runtime
package, scoring geometry and collision remain unchanged.

| Visual geometry | Approved | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Lower housing | 15,832 | 9,064 | 42.7% |
| Other thirteen selected members | 46,717 | 26,039 | 44.3% |
| Complete Base definition | 109,860 | 82,414 | 25.0% |
| Two placed Bases | 219,720 | 164,828 | 54,892 triangles |

The composed GLB is 6,408,448 bytes, down from 8,464,224. All 2,822 approved
red/green light triangles retain exact decoded GLB positions, normals and
material parameters. The other 326 members retain exact rendered attributes and
materials. The approved 18,456-triangle crossbar is among those unchanged members;
its later hole closures must not be replaced by an older source-detail mesh.
Collision stays at 16,857 triangles per Base.

## Deliberately larger detail budget

The [experiment policy](../rules/base-aggressive-lod-rmuc2027.json) uses **1 mm
nominal simplifier error and a 3 mm sampled guard**, increased from the approved
0.25 mm nominal / 1 mm sampled policy. This is approximate LOD, not lossless CAD
cleanup. Each trial starts from the native-detail tessellation, rather than
repeatedly reducing a previous approximation. Original material borders and
component retention remain enabled. Previously approved lights are excluded
from body simplification and appended exactly; the GLB composition checks their
expanded indexed positions, normals and material objects independently.

`cad_local_lod.planar_outline_vertices()` seeds locks from native planar faces
of at least 20,000 mm². Outer wires and inner wires whose conservative width bound
is at least 17 mm are eligible. A 15° tangent-turn threshold retains corners,
along with sampled coordinate extrema, without locking every CAD subdivision.
This selects constraints; it does not modify source curves, preserve every
between-corner outline point or explicitly fuse all sub-17 mm features. Smooth
curved details still rely on the sampled surface guard.

Native points within 0.01 mm map to source-tessellation vertices. Unmatched points
lock their eight nearest reference vertices and are recorded as fallbacks. The
housing has two such native points, 1.1459 mm from the closest reference vertex;
these receive neighborhood protection rather than exact native-point preservation.
Their locations and wire selections are retained in the housing ledger.

Local guard repair checks three points per triangle (centroid, first vertex,
first-edge midpoint), in both directions. The configured triangle caps cover all
triangles in these material regions. Float32 quantization is reserved from the
guard. This is still a finite sample test, not a continuous Hausdorff bound or a
native trimmed-surface certificate. An independent combined check reaches
2.9891 mm for the housing; the largest other-body check is 2.8531 mm.

## Visual checks and limits

Eighteen assembled and forty-two isolated member views use matched 1200²,
two-sided source-colour diagnostic rendering. Maximum assembled foreground-mask
difference is 0.11893% of reference foreground. In the seventeen views with
substantial red-light coverage, red-mask difference is at most 0.3066%; the
largest absolute lost-red count is fifteen pixels. The underside has only
thirteen reference red pixels: all thirteen are lost and three new pixels appear,
so its relative difference is large. Green-mask difference reaches three pixels
(1.095% in the worst view). Exact light geometry does not imply exact occlusion.

These are source-pose diagnostics, not runtime PBR or all moving poses. The
candidate received user visual approval before the subsequent shell experiment. The suite runs **326 tests:
325 pass, one optional USD skip**, including native outline selection, collinear
subdivisions, aperture thresholds, seed locks and existing guard fallback tests.

Reproduction, complete member counts and measurement ledgers
retain the proof and the denser-lock alternative. No candidate is installed.
Further large reductions should replace whole layered covers with explicit
CAD-derived shell/planar representations and separate visual relief from body
geometry, rather than merely turning up the global error.
