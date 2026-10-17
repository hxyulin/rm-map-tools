<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Automatic vector geometry and precision-controlled export

`python/cad_vector_ir.py` adds finite parametric curves and source-anchored
polygon boundary templates to the [optimizer IR](cad-optimizer-ir.md). The
accepted representation stores formulas/control data rather than a fixed mesh.
Each source edge retains a separate use record, vertex IDs, pinned endpoints,
source curve ID, sense, component labels and its acceptance evidence.

`ir.vector_layer(findings)` requires every requested source edge/face to be
reachable in the parent IR. `build_vector_ir(document, findings)` can also build
a selection directly without allocating the entire recipe pool. Findings must
match the source SHA-256 and the geometry unit must be millimetres. Input CAD,
released packages and simulator runtime assets remain unchanged.

## Automatic policy

The default `FitPolicy` is:

| Setting | Default | Meaning |
| --- | ---: | --- |
| Absolute fit limit | 0.25 mm | Maximum source-to-fitted curve error |
| Feature fraction | 0.005 | Further caps error at 0.5% of a relevant feature |
| Certificate slack | 0.005 mm | Tighten the stored bound near the measured residual, rather than merely stopping at 0.25 mm |
| Numeric guard | `1e-8` mm | Explicit allowance for float64 computation |
| Certification interval cap | 65,536 | Fail closed instead of unbounded subdivision |

The effective fit limit is `min(0.25 mm, feature_size × 0.005)`. Feature size is
line length, ellipse/circle minor diameter, or the smaller of wave period and
peak-to-trough amplitude. Polygon templates use minimum projected width over
source edge directions. A thin detail therefore does not inherit the full
0.25 mm allowance of a large terrain part.

The simplest qualifying curve wins: line, circle, ellipse, then sinusoid. A
circle is stored as an ellipse with equal radii. The semiellipse-train discovery
family has no automatic conversion yet. Unsupported/rejected fits retain the
original spline rather than an unverified approximation.

Fitted curves are finite: line endpoints, circle/ellipse angle intervals and wave
abscissa domains are explicit. Analytic curves have a linear endpoint correction
that pins both ends to the original shared source vertices. The correction stays
in the vector formula; a corrected ellipse need not remain a pure conic. Acceptance
is recomputed **after** pinning, so a good unpinned fit can still be rejected.

## Continuous curve checks

The automatic stage does not promote the earlier 2,049-sample result directly to
a continuous bound. It recomputes the source curve from its original spline
controls/knots, pairs source intervals with finite candidate intervals, and uses:

```
source-relative error <= maximum paired endpoint residual
                      + source chord-error bound
                      + candidate chord-error bound
                      + numeric guard
```

Each chord bound is `max_norm_second_derivative × parameter_span² / 8`.
Source knot spans are always partition boundaries. Piecewise polynomial power
coefficients bound source second derivatives even at repeated knots where a
global spline derivative API would fail. Ellipse and sine derivative bounds are
analytic. The source and candidate chords have a linear correspondence, which
bounds displacement in both directions for their complete intervals. Pairing
must stay within the finite domain and have consistent sampled order; unsupported
windings, over-budget residuals and interval exhaustion reject the fit.

This is a conservative continuous geometric bound computed in float64 with an
explicit roundoff guard, **not formal interval arithmetic or arbitrary-precision
numerics**. The selected source evaluators are independently cross-checked with
OCCT. Tests include a narrow spline peak, sine waves whose midpoint is flat,
repeated-knot spans, finite trims, endpoint cancellation and resource caps.

## Vector representation and export

The portable `rm-cad-vector-selection-v1` JSON stores:

- Shared vector definitions: finite lines, ellipses/arcs, sine profiles and source
  B-splines. Formula parameters are float64 values serialized without deliberate
  quantization. Original spline controls and knots retain their exact decimal
  **strings**, degree, multiplicities and source traversal direction.
- Independent curve uses and original source topology/semantic locators.
- Original source spline fallbacks for every selected curve. These remain even
  after a fit is accepted. They are essential for tighter later exports.
- Polygon boundary templates with original loops, source vertex/edge/use IDs,
  orientation flags, exact source coordinate strings, surviving corner indices
  and the original boundary fallback.
- Policy, acceptance evidence, source SHA, units, definition checksums, whole
  selection checksum and a source-geometry ownership notice. The build output
  also retains the repository `NOTICE.md`.

This selection reloads without STEP. It is **not a complete field/solid format**:
source native surfaces, face styles, appearance inheritance, assembly/motion
ownership and unsupported metadata remain in the parent IR/source document.
Absolute source-local coordinates currently limit prototype reuse; rigid local
frame normalization is a follow-up, rather than an unproven instancing claim.

`layer.export_curve(edge_id, total_error_mm)` accounts for **both** fit and
export chord error. If the accepted fit's stored error bound cannot satisfy the
request, it automatically uses the original spline. It allocates the remaining
budget to derivative-controlled tessellation and reports the complete split.
All exported shared endpoints are pinned to their source positions; any original
spline/vertex discrepancy also consumes error budget. Requests below this source
join discrepancy or the numeric guard fail explicitly.

Changing export tolerance can therefore generate finer or coarser geometry without
refitting or starting from a previously simplified mesh. This is adjustable
**resolution**, not unlimited scalar precision or recovery of detail from a fit.
The retained source fallback is how tighter requests retain source fidelity.

## Polygon and surface boundaries

The automatic polygon stage recomputes near-collinear reductions within the
feature-limited budget. It recognizes a triangle/rectangle/right triangle only
when the surviving source corners agree with the fitted corners within the
numeric guard. It does not independently move shared corners to snap angles.
Requests tighter than the template's boundary bound use the original polygon.

These bounds cover the **original vertex-polyline boundary**, not a healed/native
trimmed face. The original surface ID, full edge-use list and orientation remain
available. Native face/solid replacement is explicitly false. Shared-edge chain
consolidation, incidence consistency, source line/plane noise and native surface
interiors must be handled before these outlines become production mesh faces.

`RuledSurface(first, second, reverse_second=False)` provides parametric surface
infrastructure between two vector curves. Its mesher bounds both curve chord
error and the bilinear twist error introduced by using two triangles per strip.
A saddle regression demonstrates why the twist term cannot be omitted. The
bound covers this defined mathematical surface; matching its two boundary curves
does **not** prove that an original CAD face has the same interior. Automatic
source-surface binding and complete closed-solid/STEP/GLB export are next work.

## Reproduction

Use the CAD Python environment plus the existing SciPy requirements:

```sh
ocpenv/bin/python python/build_vector_selection.py \
  out/rmuc2027-hierarchy/field.step \
  --findings benchmarks/2026-10-17-patch-fits/summary.json \
  --out out/rmuc2027-vector-ir

# This second command needs only the portable selection, not the original STEP.
ocpenv/bin/python python/export_vector_selection.py \
  out/rmuc2027-vector-ir/vectors.json \
  --tolerance-mm 0.1 \
  --out out/rmuc2027-vector-ir/curves-0.1mm.json
```

Both tools refuse to overwrite existing destinations. The build accepts
`--max-fit-error-mm` and `--feature-fraction`; the complete policy is retained in
the selection. Export accepts repeated `--edge-id` selectors; without selectors
it exports all curves and polygon outlines in the selection. These are 3D,
source-local millimetre polylines/outlines, not a placed runtime map. The source
and derived geometry retain their upstream ownership and terms; the software
license does not relicense CAD data.

## Next work

1. Bind native source surfaces to parametric patches, beginning with the road's
   ruled/extruded surfaces, and check their interiors and end caps. Produce a
   component-scoped visual/collision export from the same vector definitions.
2. Canonicalize complete edge networks and shared vertices before merging
   collinear chains or snapping angles. Neighboring faces must share one boundary
   and one sampling cache, including material/LED seams.
3. Intern local vector prototypes under verified transforms and cache tessellation
   by prototype, trim, tolerance and scale. Tighter recertification can reuse a
   fitted formula when its initial stored bound was conservative; preserve the
   source fallback when the fit itself cannot meet a request.

## RMUC 2027 selection results

[Retained evidence](../benchmarks/2026-10-17-vector-ir/summary.json) covers the
24 curve and 40 polygon examples from the prior audit. **19 curves** pass the
continuous automatic policy. The 40 pinned-corner polygon templates qualify,
reducing 1,982 source boundary vertices to 160 template corners. These are
boundary representations, not reduced native faces or placed triangle counts.

The accepted road sine profiles have stored continuous bounds around 0.0054 mm,
compared with earlier sampled errors around 0.0003 mm. Four companion profiles
that looked good at the earlier sample-only stage fail the 0.25 mm limit after
endpoint pinning; they stay as source splines. The difficult Tech Core curve
likewise keeps its original. The other Tech Core ellipse is accepted with a
continuous bound about 0.00784 mm.

The portable selection reloads without STEP, and four requested total tolerances
produce:

| Requested total curve error | Segments across 24 curves | Original spline fallbacks |
| --- | ---: | ---: |
| 1 mm | 2,244 | 5 |
| 0.1 mm | 5,524 | 7 |
| 0.01 mm | 21,690 | 11 |
| 0.001 mm | 56,712 | 22 |

The 0.1 mm standalone export also includes 40 polygon outlines. The portable
selection is 916,207 bytes, including all source controls and original polygon
boundaries; its 0.1 mm polyline/outline export is 348,892 bytes. These are selected
working data, not full-field storage or rendering performance measurements.

## Source-bound component backend

The first [complete source-bound component backend](cad-vector-component.md) now
covers closed planar/extruded solids with original end caps, shared edge sampling,
verified normalized curve prototypes and quality-specific tessellation caches.
It exports a road-profile component for review. The native source surfaces remain
authoritative; independent fitted-curve substitution, general curved/holed faces,
whole-field export and source edge-chain merging remain follow-up work.
