<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Base crossbar and lower-housing investigation

This read-only investigation follows the approved [light primitive candidate](base-light-primitives-rmuc2027.md).
It isolates source units #4268930 (top crossbar) and #4527988 (lower outer housing).
Source STEP, the approved 136,982-triangle visual candidate, 16,857-triangle
collider, stage-one hierarchy, detector bindings and installed field remain unchanged.
DJI / RoboMaster retains ownership of the underlying CAD and its appearance.

## Current geometry

| Member | Current visual triangles | Collision triangles | Source native faces |
| --- | ---: | ---: | ---: |
| Top crossbar | 39,790 | 5,244 | 2,965 |
| Lower outer housing | 21,620 | 4,224 | 3,247 |

Both names describe inspected appearance, not inferred motion ownership. One
Base definition is reused twice. Their combined visual cost is 44.8% of a Base.

The crossbar has 36,060 dark-grey triangles and 3,730 unresolved-source neutral
triangles. The housing has 18,550 medium-grey, 1,850 unresolved neutral and 1,220
dark-grey triangles. Neutral fallback is not established to be paint: it includes
raised members, hardware and lettering. Replacing all neutral faces with decals
would discard structural geometry.

Current triangles on original supporting planes account for 16,617 triangles
(41.8%) and 79.2% of crossbar surface area, and 10,488 triangles (48.5%) and
72.5% of housing area. This classification requires parallel triangle normals,
all vertices within 0.01 mm of a source plane and containment in an expanded
source-face AABB. It is not finite trimmed-face ownership. The remainder includes
curved facets, changed relief and numerical seams; it cannot all be called fillets.

Even the two broad housing sheet planes account for only 3,176 current triangles.
Flattening those sheets alone cannot eliminate most of the housing's cost.
Narrow folded returns, thickened cutout borders, curved transitions and many
small details need separate panel/feature decisions.

## Native details and a targeted trial

The original crossbar has 461 inner planar-wire occurrences, including 398
whose complete native width bound is below 17 mm. The original housing has
1,144, including 1,089 narrow occurrences. These count both sides of many holes;
they are not distinct holes and are not all removable features. Markings,
mounting apertures and structural slots remain semantically distinct.

Complete circular bore discovery finds 66 crossbar bores (1.6–6.5 mm diameter)
and 425 housing bores below 17 mm. The earlier approved housing pass already
plugged **422** of its bores. Recounting those as new savings would be misleading.
The three additional housing candidates have 12 mm diameter. Crossbar visual
bores remain present; its collider already used bore closure.

The trial uses the existing native surface closure pass, preserving other faces
by identity and source diffuse assignments. It re-tessellates at 0.1 mm linear /
0.6 rad angular deflection, then uses material-border-locked 0.25 mm LOD with a
separate 1 mm sampled guard and up to 8,192 triangle selections per material.
No surface-error threshold is increased. Closure itself intentionally changes
openings; the 1 mm guard measures LOD against the derived closed geometry.

| Isolated visual trial | Current | Trial | Decision |
| --- | ---: | ---: | --- |
| Crossbar, close 66 bores | 39,790 | 18,626 | Promising; retain for visual review |
| Housing, close 425 source bores | 21,620 | 28,326 | Reject: larger than approved |

The crossbar saves 21,164 triangles (53.2% of that member). Adopting it alone would
leave **115,818 visual triangles per Base**, a 15.5% reduction, or 231,636 placed
triangles for two Bases. Collision would stay 16,857 per definition. These are
conditional counts, not a promoted or installed model.

Housing medium-grey LOD requests 0.25 and 0.125 mm both encounter a 1.7419 mm
sampled distance; whole-material refinement to 0.0625 mm produces 25,225 triangles
in that region alone. A feature-local refinement strategy is therefore preferable
to retaining this whole-member rebuild. Sample sets and tessellation connectivity
also differ from the earlier experiment; counts are not a pure bore-count effect.

## Validation and limitations

The crossbar's current-to-trial sampled distance reaches 5.3410 mm inside removed
bore walls. Every sampled point over 1 mm in either direction lies within a
closed-source-bore cylinder expanded by 1 mm. Outside those envelopes, the sampled
maximum is 1 mm. This explains closure differences; it does not certify a
continuous bound or prove hiddenness. Samples use 8,192 deterministic triangle
selections in each direction (49,152 point evaluations total).

The crossbar-only assembly is compared in 18 two-sided 1200² orthographic views.
Maximum changed RGB pixels above 10/255: **0.05744% of the image**. Maximum
foreground difference relative to current foreground: **0.01776%**. Seven isolated
views per member include top, bottom, both faces, end and two obliques. Depth-owner
edge overlays expose small detail; teal/orange diagnostics separate original-plane
matches from unmatched triangles. These are fixed source-pose diagnostic renders,
not runtime PBR, moving-pose, contact or complete hidden-surface validation.

The ten existing surface-LOD and gap-closure regression tests pass. All six
benchmark scripts compile, current input hashes and trial counts are verified,
and documentation links pass. The full Python suite was not rerun because no
production pass implementation changed.

The closure output remains a surface compound; invalid source topology is not
silently described as a healed watertight solid. No guessed functional grouping,
source palette replacement or detector simplification is introduced.

## Recommended next passes

1. Review the crossbar closure candidate, retaining its raised trim, end blocks,
   large openings and exposed underside structures.
2. Partition the housing into source panels, returns and local detail patches.
   Refine only failing patches, preserving shared boundaries and material edges;
   one local feature should not force denser LOD across an entire material.
3. Identify remaining narrow slots and bore transitions individually. The 17 mm
   policy authorizes width-based changes, not replacing every perforated member
   with a convex shell or flattening broad structural returns.
4. Bake confirmed flat markings and shallow relief into color/normal layers after
   defining panel UVs and silhouettes. The existing relief bake is infrastructure;
   no new texture savings are included in these measurements.

Reproduction and measurements
retain source hashes and accepted/rejected trial evidence. Nothing is committed
or promoted solely because a sampled view looks similar.
