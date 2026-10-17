<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Base panel surgery and source-colour texture patches

Following the approved [68,080-triangle shell candidate](base-shells-rmuc2027.md),
this experiment first tests local crossbar panels, then exports an actual glTF
texture replacement for the front artwork. Source geometry and artwork remain
owned by DJI / RoboMaster. The original STEP, installed package, collision and
scoring geometry remain unchanged.

| Complete Base | Triangles | GLB bytes |
| --- | ---: | ---: |
| Approved shell reference | 68,080 | 5,352,476 |
| Selected panel only | 67,455 | 5,305,716 |
| Panel and textured artwork | 66,502 | 5,245,600 |

The combined saving is **1,578 triangles (2.32%)**, or 3,156 for two placements.
This is a smaller return than the preceding shell pass. The crossbar decreases
from 10,494 to 9,869; the lower housing from 8,893 to 7,940. All other **338 source
members**, including all **2,822 light triangles**, retain exact rendered
positions, normals and materials. Member metadata is retained. Collision stays
at 16,857 triangles per Base. These GLBs are inspection candidates, not an
installed field package.

## First: finite panel replacements

The original crossbar is not a valid native solid, so the pass cannot infer
that everything invisible is enclosed. Four independent proposals instead use
specific native planar profiles extruded by **3–8 mm**. Native outer outlines
and larger openings stay explicit; only inner loops strictly below 17 mm are
filled. Validity and profile area × depth accounting must pass.

`cad_panel_replace.clip_panel_mesh()` clips finite mesh triangles against one
valid native replacement solid. Only the explicitly selected dark material is
eligible. Completely contained triangles disappear; crossing triangles are cut
and remeshed. Disjoint and unselected triangles retain ordered positions and
colours. Failed cuts/remeshes retain the input triangle and record it; they are
not silently discarded. This is intentional bounded panel reconstruction,
not a hiddenness or whole-model healing proof.

| Native source face | Signed depth | Raw crossbar triangles | Decision |
| --- | ---: | ---: | --- |
| 4202749 front cover | −6 mm | 10,447 | Select after seam cleanup: 9,869 |
| 4196198 rear plate | +8 mm | 11,213 | Reject; seam-cleaned 10,391 is a poorer independent saving |
| 4213567 left return | −3 mm | 10,524 | Reject: grows geometry |
| 4222186 right return | −3 mm | 10,529 | Reject: grows geometry |

The front-cover edit removes 474 complete triangles and clips 514. Four
unresolved cuts retain their original triangles. Its new native skin fills the
previously selected mounting channels rather than reverting to the unclosed
native model. The resulting seam cleanup rounds dark positions to a 0.0001 mm
grid, reconstructs qualified planar patches and applies local guarded LOD at
1 mm nominal / 3 mm sampled against the derived panel mesh. Approved non-dark
trim geometry remains exact. Native corner neighborhoods remain seeded locks.
This cleanup also affects dark tessellation outside the edited plate; its
saving is not all attributable to removing internal panels.

An independent bidirectional check against the preceding 10,494-triangle
crossbar reaches **3.000035 mm**. The explicit admission margin is 3.001 mm,
including the sub-0.0001 mm position normalization. No checked point exceeds
that margin. The qualifier additionally requires any larger sampled difference
to lie inside or within the same margin of the finite native edit solid. These
are deterministic samples, not a continuous error certificate.

## Then: a real textured artwork primitive

The front logo and lettering are explicitly selected on support face **4465456**
in lower housing **4527988**. Their 483 neutral artwork triangles lie essentially
on one plane, about 0.05 mm below that native support. The ROI is 210 × 140 mm
in a native plane frame; every admitted triangle lies within 0.1 mm of it.
Source-neutral geometry elsewhere is not classified as decoration.

`cad_texture_patch.replace_planar_rectangle()` subtracts that finite rectangle
from admitted triangles using four half-plane clips. Outside pieces and all
out-of-plane structures remain geometry. A two-triangle quad replaces the
inside patch. Removing the artwork's material boundaries also removes redundant
underlying panel tessellation: net saving **953 housing triangles**.

The existing source relief baker projects original diffuse colours into a
1024² image with **100% sampled pixel coverage**. This is not a proof of
continuous coverage; overlapping source sheets mean summed triangle area is
not a union-area certificate. No missing pixels are filled with invented paint.
The observed source height range is approximately −0.05003..+0.00002 mm.
An eight-pixel edge gutter yields a **1040² RGB PNG, 11,316 bytes**.

`attach_colour_texture()` embeds the PNG, UVs and a base-colour material in the
GLB. Its base-colour factor is linear one, texture colour is sRGB, metalness is
zero and roughness remains 0.8. UV V=0 maps to the top image row (+V of the source
plane); clamp wrapping and trilinear mip filtering are requested. This is a
self-contained textured primitive, not an unattached bake. It adds no normal,
height, emission or guessed source-paint semantics. Qualified artwork surfaces
are effectively planar, so no normal-map material is needed here.

## Groove trial retained as geometry

The crossbar's left-front groove rectangle was also projected. It reaches a
backing surface **6 mm** deeper and covers only **99.8778%** of sampled pixels.
A simple opaque quad would bridge actual uncovered openings. The exporter
rejects that proposal and retains the groove geometry; it does not fill pixels
or claim a triangle saving. A future candidate needs finite hole-preserving
patch geometry or explicit native aperture qualification. A normal map alone
would not preserve the uncovered openings or the undercut.

## Validation and limits

Both selected stages have matched **18 assembled and 12 isolated** 1200² views,
plus front-normal and oblique artwork close-ups. The diagnostic rasterizer
reads the **exported GLB's actual UVs and embedded PNG**, sampling it bilinearly.
It does not substitute precoloured geometry or a fake shaded replacement.
Maximum assembled foreground-mask difference is **0.03739%** of the reference
foreground for both stages. Maximum RGB changes above 10/255 are 0.08098% for
panel-only and 0.08778% combined. Red and green LED pixel masks remain identical
in all 18 sampled views.

These are fixed source-pose orthographic diagnostics, not runtime PBR,
perspective, mip/anisotropic filtering or all moving poses. Source normal maps
are not claimed to be integrated. The close-ups check readable artwork,
orientation and quad borders; the supplied GLB remains available for user review.

The full suite runs **338 tests: 337 pass, one optional USD skip**. New tests
exercise finite cut/material protection, crossing-triangle retention, rectangle
area conservation, out-of-plane geometry, UV orientation, embedded PNG survival
through compaction and the linear colour factor. Composition checks unchanged
source nodes, rendered attributes, triangle totals and preserved lights.

[Reproduction and measurement ledgers](../benchmarks/2026-10-17-base-panel-textures/README.md)
retain all proposals and the rejected groove projection. No source CAD or
runtime collision data is overwritten.
