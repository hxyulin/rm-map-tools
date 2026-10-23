<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Finite patch matching and primitive-fit discovery

`python/cad_patch_matching.py` starts finite trimmed-patch matching on the source
CAD. `python/cad_shape_fitting.py` adds measured approximation proposals for
simpler boundaries and profiles. Both preserve source geometry, ownership,
styles, semantic uses and runtime assets. Neither applies a replacement or
produces a mesh. Their `PATCH_CONTRACT` and `FIT_CONTRACT` describe prerequisites,
correspondence and the scope of each measurement.

These are the next stage of the [optimizer IR](cad-optimizer-ir.md), rather than
another simplification of already exported triangle meshes.

## Finite planar patches

`ir.polygon_patch(face_id)` resolves a reachable source face into a finite
polygon patch. The standalone `polygon_patch(document, face_id)` API can also be
used without building all IR views. The initial subset requires:

- One explicit `FACE_OUTER_BOUND`, one `EDGE_LOOP`, 3–64 straight `LINE` edges,
  explicit orientation flags and a `PLANE` surface.
- Source endpoint identities must connect the loop in order. Repeated source
  identity is retained independently from coincident coordinates.
- Exact mode requires rational equality between the decimal source vertices,
  underlying lines and plane. Zero vectors, degenerate and self-intersecting
  trims fail. Source tolerance is not silently used to admit approximate matches.

`patch_key(patch)` uses exact rational pairwise vertex distances, ordered
vertex/edge/use alias patterns, orientations and the loop side relative to the
plane normal. Cyclic starting vertices normalize without reversing winding.
The complete key is compared after hashing; equal keys prove congruence of this
finite polygon subset, rather than just equality of an infinite plane.

`patch_correspondence(reference, candidate)` requires one source document/context
and yields the original face, bound, loop, oriented-edge, edge and vertex maps,
a proper rigid transform and its floating-point reconstruction residual.
Reference ordering and alias patterns must agree. Different material bindings
or semantic ownership are not merged. Automatic mesh reuse still needs its
backend to consume these maps, retain original face styles and verify numerical
transform error at the selected tessellation tolerance.

`patch_key(patch, quantum=.01)` is a separate discovery mode in source length
units. Rounded distances can identify near-equal finite polygons despite CAD
coordinate noise. They are not equality certificates. Its correspondence result
is explicitly labeled discovery-only. Keys are local to the source audit and
must not be reused across unit/context namespaces as bare global hashes.

Faces with holes, curved boundaries, multiple outer bounds, unsupported frames
or oversized loops are counted as skipped. Normalized UV domains, curved patch
trimming and shell-level mesh reuse remain future work.

## Approximation proposals

Polygon fitting first removes near-collinear boundary vertices within a stated
source-unit budget, then tests triangles, rectangles and right triangles.
Rectangle and right-triangle models constrain orthogonality rather than snapping
each angle independently. Every proposal retains its original face ID, component
names, source-local bounding box, chosen corners and error.

The simplifier rechecks every original chain vertex against its final chord and
requires monotone chord projections. The maximum chain displacement plus maximum
fitted-corner displacement bounds the corresponding **vertex-polyline boundary**
in both directions. It is not a healed/native B-rep deviation certificate when
STEP vertices disagree slightly with their underlying line or surface. A future
edit pass must recheck native trimmed boundaries, area, topology, thin features,
paint/LED boundaries, contact clearances and shared-edge consistency before
applying changes. Independent adjacent-face fits must not create cracks.

Curve discovery currently evaluates full-span, simple, nonrational
`B_SPLINE_CURVE_WITH_KNOTS` edges directly from source controls and knots.
Partial trims, complex/rational forms and invalid endpoint agreement are refused.
All selected curves are independently evaluated by OCCT as a cross-check on the
SciPy evaluator; no full-model import or ordinal-to-source inference is needed.

Candidate families are:

- A line from the principal axis, a circle, and a rotated ellipse in a fitted
  plane. Circle/ellipse errors are sampled Euclidean distances to the complete
  analytic primitive; finite arc endpoints/trims still need an explicit mapping.
- A sine profile with offset, slope, period and phase (sine/cosine coefficients).
- A periodic semielliptic arch profile. Height equal to half-period is the
  semicircular special case; the height/half-period ratio is retained.

Wave fitting requires a monotone end-to-end abscissa and searches 1.5–12 periods.
It is not a universal wave detector. Each fit uses 129 training and 2,049
validation samples. Validation errors are sampled distances/displacements,
**not continuous Hausdorff bounds**. Curves with very uneven parameterization
may require knot-span/adaptive subdivision even at these sample counts. A later
replacement pass must preserve trims, seam endpoints and source use identity and
establish continuous error bounds. Error alone must not favor an unnecessarily
complex model; the audit reports the simplest tested model within each budget.

## Reproduction

Install the pinned CAD environment and the existing simplification requirements
(which include SciPy). Then run:

```sh
ocpenv/bin/python python/audit_patch_fits.py \
  out/rmuc2027-hierarchy/field.step \
  --hierarchy out/rmuc2027-hierarchy/hierarchy.json \
  --curve-limit 24 \
  --out out/patch-fits/summary.json
```

The CLI requires explicit millimetre geometry units, checks the reviewed hierarchy
checksum, scans all reachable source faces, and checks the input checksum again
at completion. It inventories simple full-span spline edges at 17 samples, then
fits a budgeted selection: long road curves first, followed by long genuinely
curved and almost-straight examples. The sample is intentional and not an
exhaustive primitive-family classification of every edge. Reports cap group
examples at 20 and polygon examples at 40, with full aggregate counts and explicit
source IDs. All coordinates/bounds/transforms use source-local millimetres; this
is not a placed/world triangle or draw-call count.

## RMUC 2027 findings

Evidence and producer hashes
refer to the reviewed stage-one STEP SHA-256
`f561429d829e463fae5dd06d2b4eedbd9a7bbb87a0c9507ac6524fb47a021e73`.

- Of 110,586 source faces, **42,376** meet the straight-boundary polygon subset.
  Strict exact incidence admits 436 of those; most others have decimal-coordinate
  noise relative to the source plane/line. There are **65 exact metric groups**
  with **131 additional face uses**. Rounded-distance discovery at a 0.01 mm
  quantum finds **6,716 groups / 29,032 additional uses**, without certifying
  their deviation or authorizing reuse.
- **34,109 faces** fit a rectangle within a 0.1 mm vertex-polyline boundary bound.
  Many are already rectangles, so this is an inventory rather than a savings
  count. Examples `2687499`, `2694202` and `2698626` in `fan/body-2717086` have
  55–58 source edges and fit four corners with errors below `1e-8` mm. Shared
  neighboring-edge and native-surface checks are still required before editing.
- **4,037 faces** fit triangles within 0.1 mm; **3,659** fit a right-triangle
  candidate within the same bound. These overlap and must not be added together.
- Of 18,459 supported full-span spline edges, **6,130** look straight within
  0.01 mm at the initial 17 samples. These are coarse candidates, not accepted
  replacements. A budgeted 24-edge follow-up includes 12 of the 14 road splines.
  Every selected curve's SciPy and OCCT samples agree within `7.6e-12` mm.

| Representative source edge | Location | Fitted model | Maximum error at 2,049 samples |
| --- | --- | --- | ---: |
| `3795912` | red-road-surface/shell-3797315 | Sinusoid, period 240.642272 mm, height about 70 mm | 0.000304 mm |
| `3788670` | red-road-surface/body-3789460 | Sinusoid, period about 240.642 mm | 0.000212 mm |
| `3788666` | red-road-surface/body-3789460 | Sinusoid, companion profile | 0.188567 mm |
| `1430864` | technology-core/arm-and-shared | Ellipse, semiaxes about 111.804 / 76.000 mm | 0.002658 mm |
| `2642978` | red-trapezoid-highland/body-2643575 | Line | 0.000106 mm |

The road's sine fit is particularly strong. The tested semielliptic arch
candidates fit these profiles much worse; this source supports using a sine
profile for further work. These measurements characterize edges, not the entire
road solid or its collision mesh. A source-backed sine surface/solid candidate
must still preserve end caps, joins, thickness and adjacent geometry.

No fitted model is applied, no source face/edge is removed, and there is no
claimed placed-triangle reduction yet. The next concrete edit should be a
component-scoped candidate with shared-edge/native deviation checks and a
before/after visual and collision review.

The next [automatic vector stage](cad-vector-ir.md) now uses a feature-limited
policy, continuous curve checks and original-parametric fallbacks. The discovery
counts above remain the historical sampled-fit experiment, not automatic edits.
