<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Local Base housing LOD

This candidate reduces the lower outer housing, source unit #4527988, after the
approved [light and crossbar work](base-mounting-row-rmuc2027.md). DJI / RoboMaster
retains ownership of the source geometry. Original STEP, source topology,
collision, detector bindings and installed assets remain unchanged.

| Visual geometry | Approved | Candidate | Saving |
| --- | ---: | ---: | ---: |
| Lower housing | 21,620 | 15,832 | 5,788 (26.8%) |
| Complete Base definition | 115,648 | 109,860 | 5,788 (5.0%) |
| Two placed Bases | 231,296 | 219,720 | 11,576 |

The full inspection GLB composes the approved light model, approved top crossbar
and this housing, preserving the original source-member nodes. Its 338 other
members retain byte-exact GLB positions, normals, indices and material objects
against the light reference. That includes the smooth green optic. The composed
GLB is 8,464,224 bytes. These are inspection counts, not an installed field package;
collision remains 16,857 triangles per Base, including 4,224 for the housing.

## Protect failing neighborhoods instead of refining whole materials

The input is the approved **44,248-triangle native-detail tessellation**, including
the earlier 422 bounded bore plugs. It is not another reduction of the current
21,620-triangle mesh. The pinned [policy](../rules/base-housing-local-lod-rmuc2027.json)
uses the existing **0.25 mm nominal metric** and **1 mm sampled guard**.

`cad_local_lod.guarded_vertex_lod()` simplifies each source material independently.
It checks every input and output triangle in this housing at three deterministic
points: centroid, first vertex and first-edge midpoint. The 65,536-triangle cap
covers every triangle of each material here; larger callers remain sampled.
These are not continuous Hausdorff bounds or all possible surface points.

When source samples fail, their original triangle corners become locked vertices.
When candidate samples fail against the source, the nearest 32 source vertices
and their incident triangle corners become locked. The pass retries the same
original mesh at the same nominal metric, accumulating local constraints. It
never increases the surface guard. A stalled or unresolved material retains its
input geometry. Open material borders and the existing small-component retention
logic remain enabled.

The main grey material accepts after two repair iterations, with 1,193 source
vertices locked. Its triangle count drops from 18,550 in the approved LOD to
12,766. Dark geometry stays at 1,220; unresolved-source neutral geometry changes
from 1,850 to 1,846. No material is inferred to be paint or replaced with a decal.
No source hole, folded return or relief is explicitly deleted in this pass.

A shared rebased frame bounds input float32 quantization to **0.00003335 mm**.
The admission guard reserves four times that amount from the 1 mm limit, avoiding
roundoff accepting an otherwise exact-threshold result. Maximum per-material
checked distance is 0.9608 mm; an independent combined sample check reaches
**0.9558 mm**. These are checks against the native-detail tessellation, not direct
support/trim proofs against the STEP.

The existing simplifier now accepts original-input vertex indices to lock. Its
missing-component retries carry the same locks. The installed meshoptimizer
0.2.30a0 Python wrapper omits the ctypes signature for its attribute-aware entry
point; the adapter registers that ABI without modifying dependency files. A
constant zero-weight attribute exposes vertex locks without adding an appearance
attribute or weight to the geometric metric. Calls without locks retain the
existing backend path.

## Alternatives and comparison limits

Spatial subdivision is implemented separately as `adaptive_material_lod()`, with
locked shared patch boundaries and leaf-local metric refinement. It saves only
312 housing triangles (21,308 total); new patch seams consume most of the benefit.
It is not the selected candidate. A sparse vertex-guard trial also failed the
independent combined check; this motivated checking every source triangle here.
No failed check is treated as permission to relax its threshold.

The candidate differs from the previous housing by up to 1.7419 mm in the sampled
bidirectional comparison. That is distinct from its 0.9558 mm distance to the
native-detail input: both LODs are approximations, and the denser checks expose
features missed by earlier sparse sample patterns. The unchanged 1 mm policy
continues to refer to the native-detail input. It is not a claim that every pair
of successive approximations is within 1 mm of each other.

Seven isolated and eighteen assembled Base views compare source colours and
silhouettes at 1200² pixels. Maximum whole-image RGB change above 10/255 is
**0.1081%**; maximum foreground difference relative to reference foreground is
**0.03922%**. These are fixed source-pose diagnostic views, not runtime PBR,
changing poses or contact validation. The orange lock overlay marks candidate
triangles incident to protected vertices; it does not mean those whole triangles
are retained byte for byte.

The full Python suite runs **323 tests: 322 pass, one optional USD skip**. New tests
cover locked input aliases, retained components, unchanged material separation,
local retry policy, strict guards and unresolved-region fallback. Full GLB
composition independently checks the 338 unaffected members and total triangles.

[Reproduction and measurement ledgers](../benchmarks/2026-10-17-base-housing-local-lod/README.md)
retain candidate, alternative and validation provenance. The housing received user visual approval before the
[subsequent aggressive detail experiment](base-aggressive-lod-rmuc2027.md).
The preceding light/crossbar work is committed as `f64548c`.
