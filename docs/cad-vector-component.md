<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Source-bound vector components and shared mesh export

The first component backend binds complete source **planar and linearly extruded
solids**, with original end caps, flat extensions, materials and edge ownership.
It implements the next stage after [vector curve selection](cad-vector-ir.md).
The initial candidate is `red-road-surface/body-3789460`: one complete closed
road-profile source body, **not the whole road assembly or all terrain**. This
body includes long flat extensions as well as its ten-wave profile region.

`python/build_vector_component.py` extracts that reviewed hierarchy component,
validates its source/native binding, builds a shared-boundary mesh, checks it
against native supports and exports matching visual/collision GLBs. It does not
install them into a runtime package or change approved assets/source CAD.

## Complete source binding

`OptimizerIR.component(body_id)` / `component_graph(document, body_id)` captures
all source faces, bounds, loops, oriented edge uses, curves, vertices and surfaces.
It requires a closed two-face edge manifold and retains IDs and ownership.
Source plane declarations/frames and extrusion declarations/expanded spline
basis parameters remain available. Every surface and boundary stays source-defined.

`NativeComponent` reads the small source STEP into XCAF. Native record positions
are candidate bindings only: before associating transferred shapes with source
IDs, it compares the complete reachable geometry graph's type, ordered reference
identity, numeric values, spline degree/knots/multiplicities and orientation/sense
flags. Missing/split faces, invalid solids and unsupported schemas fail closed.
Native ordinals are never silently presented as STEP IDs. XCAF retains effective
source color/inheritance; the export carries source face IDs per GLB triangle.

The backend adds explicit partial B-spline trim domains where source vertices
trim a larger construction curve. It records projections in the normalized base
parameter domain, requires endpoint agreement within 0.001 mm and retains native
trimmed edges as the authority. Vector evaluation/chord bounds now honor these
finite domains, including reversed traversal. The source construction data is
not discarded or retessellated into a fixed intermediate mesh.

The package includes `source.step` as its native fallback and metadata authority,
plus `component.json` for vector surfaces/topology. Unsupported vector meshing or
failed support checks fall back to complete native meshing; the reason is recorded.
Source/native binding failure itself aborts rather than guessing correspondence.
This is a component package, not a standalone replacement for every CAD schema.

## Shared boundaries and meshing

`python/cad_component_mesh.py` builds one sample network per **source edge**:

- Surviving endpoints use original vertex IDs and positions. Interior samples use
  edge identity and sample index. Unrelated coincident geometry is not welded.
- Planar faces are triangulated from their complete shared boundary samples;
  ear clipping does not delete collinear vertices needed by a neighboring face.
- Extruded faces are partitioned at their two transverse edges. Both profile
  chains need a complete polynomial translation bound and alignment with the
  source extrusion axis before strip meshing is admitted.
- Opposite profiles share a union of parameter requirements. Numerically duplicate
  samples may coalesce only after a point-displacement plus curvature check below
  `1e-7` mm. Adjacent planar caps consume the same resulting source-edge samples.
- Global triangle incidence must be a single connected, closed, consistently
  orientable manifold. No missing face or open seam is accepted silently.

The initial mesher allocates a quarter of the requested quality to curve chords,
with separate small allowances for verified normalization/profile pairing and
source endpoint discrepancies. It retains source spline surfaces: the previous
sine fits are **not substituted independently** into a closed solid. A future
piecewise fitted-surface pass must update the complete shared network coherently.

The initial reviewed baseline used the same indexed visual/collision geometry.
The exporter now consumes the [visual-only terrain marking catalog](../rules/roles-rmuc2027-terrain.json):
colored border solids retain their visuals and have zero collision triangles.
The empty collision GLB retains an anchor without invalid zero-length buffers.
Embedded markings require separately owned unpainted backing coverage; the
initial policy preserves that footprint until backing coalescing is validated.
See the profile LOD and role measurements.
Source-local metre
coordinates are centered at the reported `origin_mm`; axes remain CAD Z-up.
The report supplies the origin for reassembly. This review package is not yet a
field-package replacement or the simulator's FLU adapter. Float32 GLB vertex
error is measured separately and included in the sampled-support margin.

## Normalized prototypes and caches

`python/cad_vector_cache.py` factors curves into proper rigid local frames and
independent source uses. Rounded signatures only locate candidates. Reuse needs
an independent bound: polynomial differences over the union of knot spans for
splines, endpoint bounds for lines and analytic coefficient/phase bounds for
ellipses/sines. Original parameter domains, scalar dimensions and source data
remain separate; a nonplanar mirror or differently scaled shape is not silently
admitted as a rigid instance.

The pool reserves `1e-6` mm for normalization. Tessellation entries are keyed by
prototype and the exact requested chord-quality value; different quality requests
cannot accidentally reuse an insufficiently fine mesh. Source uses retain their
placements and endpoints. Geometry sharing never merges appearance, source IDs,
face/semantic owners or contact identities. Tests cover rigid copies, scale and
mirror rejection, finite trims, differing quality requests and between-sample
polynomial differences.

## Candidate measurements

Evidence pins the reviewed
stage-one source SHA and the exporter implementations:

| Measurement | Result |
| --- | ---: |
| Complete source faces | 20 (18 planes, 2 extrusion surfaces) |
| Source edges / face boundary uses | 46 / 92 |
| Reachable native/source geometry entities checked | 2,028 |
| Native mesh at 0.1 mm / 0.2 rad | 219,060 triangles |
| Shared vector-boundary mesh | 9,368 triangles |
| Reduction in this component | 95.72% |
| Vertices in closed indexed mesh | 4,686 |
| Curve uses / normalized prototypes | 46 / 27 |
| Verified definition reuses / tessellation hits | 19 / 19 |
| Native support-distance samples | 46,880 |
| Maximum sampled native support distance | 0.019067 mm |
| Maximum GLB float32 vertex error | 0.000184 mm |
| Relative volume difference to native closed mesh | 0.004005% |

These savings come from meshing the source surfaces and shared boundaries better,
not deleting faces, raising the requested error or refitting the CAD. Colors
remain the original red and cream. The 0.1 mm native deflection setting and the
vector method's sampling budget are different algorithms, not a controlled
runtime performance benchmark.

Support checks include all mesh vertices, triangle centroids and edge midpoints,
projected onto bounded native supports. They are **sampled, one-direction support
checks**, not continuous/bidirectional trim certificates. The connected-manifold,
face coverage, original loop mapping and volume checks provide separate evidence.
Volume uses the closed native tessellation as reference; adaptive kernel volume
integration of these periodic supports did not provide a stable reference in the
investigation. No analytic-exact volume claim is made.

## Reproduction and visual review

```sh
ocpenv/bin/python python/build_vector_component.py \
  out/rmuc2027-hierarchy/field.step \
  --hierarchy out/rmuc2027-hierarchy/hierarchy.json \
  --component red-road-surface/body-3789460 \
  --quality-mm 0.1 \
  --out out/rmuc2027-road-vector

ocpenv/bin/python benchmarks/2026-10-17-vector-component/render.py \
  out/rmuc2027-road-vector \
  --out out/rmuc2027-road-vector/comparison.png
```

A new destination is required. The output includes `visual.glb`, `collision.glb`,
`source.step`, `component.json`, indexed geometry and native comparison data,
`summary.json` with file hashes, and the upstream ownership `NOTICE.md`.
Geometry stays in ignored `out/`; only tooling and diagnostic evidence are tracked.
The comparison uses matched XY views and a wave-region XZ view with vertical
scale x6. Inspect the GLB for ordinary 3D proportions and the complete extensions.

Next, extend the same backend to the other road bodies/surface shells, consolidate
eligible source edge chains across every owner, and add verified surface/whole
component prototypes before reusing complete meshes across placements. Broader
curved surfaces, holes, native right-angle edits and runtime installation remain
outside this first supported component subset.
