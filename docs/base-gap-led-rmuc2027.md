<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Projectile-width collision closure and LED LOD

This extends the [approved separate visual/collision candidates](base-surface-lods-rmuc2027.md).
The user authorizes collision openings strictly narrower than **17 mm** to be
closed. This is a geometry policy for vehicle and 17 mm projectile contact,
not a 17 mm mesh-deviation allowance. It does not establish identical ricochets.
Source STEP, runtime assets and gameplay detector definitions remain unchanged.

## What the width rule means

A rigid 17 mm sphere cannot pass through a slit whose minimum width is less than
17 mm. It can partly enter the slit and touch its edges, so filling it changes
contact position, grazing and bounce. Near-threshold apertures have especially
little clearance. Openings exactly 17 mm wide are retained by the strict policy;
this does not imply they offer usable clearance in a numerical physics engine.

The pass covers explicit source members, not every arbitrary gap in the arena.
Fusion across independently moving members remains excluded. Larger geometric
features are not deleted because their sampled surface distance happens to be
less than 17 mm. Material-only visual simplification and scoring surfaces keep
separate policies.

## Native closure passes

`cad_surface_lods.wire_width_bound_mm()` measures a finite planar opening with
native oriented boxes, without tessellation. It tests the plane axes and native
straight-edge directions. Each caliper width bounds the complete native curve;
a successful box narrower than 17 mm certifies a narrow opening. The available
calipers are conservative discovery: failure to find one keeps the opening.
This is not a general maximum-inscribed-circle calculation.

`profile_prism(maximum_gap_mm=17)` uses that strict width policy instead of its
legacy area threshold. A 15 × 50 mm slot may close even though its area exceeds
100 mm²; a 17 × 50 mm slot remains open. Source outer wires and signed plate
thickness remain unchanged. Four backing plates process 74 source inner loops,
including small holes already closed by the earlier area-based candidate. All
74 meet the new strict width condition. The three smaller backing plates become
12-triangle solids; the upper backing becomes 18 triangles.

`close_bore_surfaces()` discovers complete cylindrical bores with two planar
inner-wire ends, using the existing split-cylinder incidence analysis. It closes
only diameters strictly below 17 mm, with a 1e-6 mm exclusion margin at the exact
threshold. The end planes are rebuilt without those specific inner wires, and
the bore's cylindrical walls are removed. All other native faces remain by
identity. This avoids whole-solid Boolean operations on the source crossbar,
whose outer shell was already invalid. It exports a derived **surface compound**,
not a newly healed/watertight solid. Source face correspondence remains scoped
to the pinned component checksum and native face inventory.

Accepted replacements close 335 complete circular bores: 66 in the crossbar,
77 in each tall cover and 38 in the module frame. Countersinks, intersecting or
unresolved bores and other unsupported holes remain untouched. The lower
housing trial does not improve its previous collision count and is rejected;
its approved collider is retained.

Each reconstructed candidate is natively tessellated, then reduced with the
existing 3 mm collision metric and a separate 6 mm sampled-distance guard.
Material/boundary locking remains enabled. Candidate-to-approved collision
samples have a separate 15 mm rejection guard; the maximum accepted measurement
is 5.94 mm. These samples do not certify every opening or continuous surface.

## LED-aware visual reduction

Visual candidates derive from the earlier **476,924-triangle reference**. They
are not repeated reductions of the 275,172-triangle approved successor.
Per-unit candidates larger than the approved unit or failing their sampled guard
retain that approved unit. The pass preserves the source-unit hierarchy and
material palette. New triangles record regional source ownership rather than a
fabricated single CAD-face id.

`material_lod(material_policies=...)` now accepts stricter settings for selected
materials. Ordinary regions request a 0.25 mm metric and a 1 mm bidirectional
sampled-distance guard. Red and green source LED regions request **0.025 mm** and
**0.1 mm** respectively. Failed regions retry smaller metrics without relaxing
their guards. Open material borders stay locked; component retention prevents
small disconnected details disappearing. Source colors and shader/emission
settings are unchanged. The LED mesh is now approximate rather than byte-exact.

The maximum accepted LED sampled distance is 0.09542 mm. Measurements are on the
source tessellated mesh, not exact native support or a continuous Hausdorff bound.
All 340 source-unit material palettes are independently checked after serialization.

## Results and inspection

| Representation | Previously approved | New candidate | Saving |
| --- | ---: | ---: | ---: |
| Visual triangles / Base | 275,172 | 142,120 | 48.4% |
| Collision triangles / Base | 20,095 | 16,857 | 16.1% |
| LED triangles / Base | 16,806 | 7,960 | 52.6% |

The visual is 80.0% below the original 709,354-triangle native tessellation. Two
Base placements reuse the same definition: 284,240 placed visual triangles and
33,714 placed collision triangles. LED counts are part of visual, not additional.

Eighteen matched 1200² source-pose views measure at most 0.1464% RGB change above
10/255 and 0.01535% foreground change against the approved visual. Isolated LED
renders change at most four foreground pixels out of 1,440,000. Enlarged LED
close-ups reach 0.1681% silhouette difference relative to source foreground area.
These are diagnostic raster views, not runtime shading, moving-pose or bounce
validation. The comparison page includes whole Base, crossbar/housing, complete
modules, isolated red strips and the green optic.

Tests include exact-threshold circular and rectangular apertures, a rotated
16 mm slot with wide axis-aligned bounds, material-specific refinement settings,
and native sphere intersections: a 17 mm sphere intersects a 16 mm bore's walls
but fits an 18 mm bore. **295 tests run: 294 passed and one optional USD skip.**

[Reproduction and full ledger](../benchmarks/2026-10-17-base-gap-led/README.md)
retain rejected trials, settings, source identities and measured deviations.
