<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Native detail passes and Base trials

`python/cad_detail_passes.py` provides independent working passes over source
B-reps. Original STEP stays immutable. Shape identity, appearance and source
ownership remain separate; native face indices are qualified by their input
component checksum. The [RMUC 2027 policy](../rules/base-details-rmuc2027.json)
records the selected units, detail thresholds and quality used for these trials.
No runtime package or motion/scoring binding is changed.

## Interior passes

`enclosed(inner, opaque)` checks complete finite native surfaces with a Boolean
difference, then minimum distance to the opaque solid's boundary. It requires a
valid occluder, outside area no greater than 1e-6 mm² and clearance greater than
0.001 mm. Vertex tests and boxes can reject cheaply; they cannot accept a removal.
Air in an existing cavity is not opaque material. Independently moving source
members still need an ownership policy before promotion.

`fill_enclosed_voids()` retains the native outer shell by face identity and drops
only closed cavity shells that pass strict interior checks. Its output must be
a valid outward solid and retain each outer face's original diffuse binding.
It does not cap exterior openings. The original crossbar has an invalid native
outer shell, so this pass **rejects it**; no repair or visibility-based deletion
is substituted. No eligible whole small unit passed containment on this Base.
Both passes are implemented and regression-tested, but their Base trials are
explicit no-ops. The earlier 79.4% unobserved-pixel figure does not authorize
removal.

## Fastener-bore smoothing

`small_bore_groups()` discovers full circular features, including connected
half- and quarter-cylinder source faces. Native edge incidence groups them;
analytic axis/radius keys are compared at 1e-5 mm grouping precision. Angular
spans must sum to a full turn. Both ends must meet perpendicular planar inner
wires. Countersinks, curved ends, unresolved intersections, partial turns and
larger openings remain unchanged. Detection is a geometry-quality policy, not
an inference of mechanical function.

`plug_bores()` unions a valid source solid with explicitly bounded native plugs.
The plugs use the finite source endpoints, flush planar caps and 0.00001 mm
radial overlap. They carry source-plane diffuse colors to their caps; coplanar
unification protects boundaries with different colors. The result must remain
one valid solid. Positive volume gain must fit both the caller's budget and the
sum of plug volumes.

The production trial's change scope follows its **constructive union**: source
material plus finite plugs. Full differences between two large, almost coincident
Base solids are not claimed. The alternative `smooth_bores()` native defeaturing
backend performs full difference checks on accepted small fixtures, but direct
whole-Base difference work was too costly for this trial. It is not the backend
used to produce these measurements. No unmeasured outside-change value is
reported as zero for the constructive pass.

The lower housing accepts 422 complete bores with radius ≤3 mm and depth ≤25 mm.
Their plugs add 13,957.29 mm³ (about 14 cm³). Its native face count becomes 2,337,
from 3,247. This intentionally closes those small holes; it is an approximation,
not lossless simplification. Source loops for larger openings and artwork remain.

## Native detail LOD

`mesh_native_detail()` meshes an entire input unit through one native shared-edge
network. It changes no CAD surface, curve or trim topology. The trials use 0.1 mm
linear and 0.6 rad angular deflection; the original baseline was 0.4 mm / 0.25 rad.
A looser angular limit avoids oversampling tiny rounds while the tighter linear
request controls larger shapes. Every input face must still produce triangles.
This includes the original crossbar's unchanged pre-existing topology status;
the tessellation pass does not claim to repair it.

`sampled_support_error()` checks triangle vertices, midpoints and centroids on
analytic supports, plus up to 64 deterministic projected points per other face.
The accepted large-unit meshes have maximum sampled errors below 0.100 mm,
against a 0.12 mm trial limit. These are support samples, not continuous finite
trim-domain or Hausdorff certificates. Quality/appearance tests and matched
views supplement the native shared-edge mesher.

Two trials remain separate: the crossbar/lower housing, and 292 small analytic
hardware units. The latter limits maximum span to 20 mm, restricts surface kinds
to planes/cylinders/cones/spheres/tori and excludes red/green light-bearing units.
Module fronts, light bars, tall covers and other unselected units retain their
original meshes. The size/type filter is not a new functional/motion binding.

## Measured independent candidates

| Candidate | Triangles per Base | Saving |
| --- | ---: | ---: |
| Original native source | 709,354 | — |
| Enclosed-cavity removal | 709,354 | No accepted change |
| Enclosed small-unit removal | 709,354 | No accepted change |
| Crossbar + housing LOD | 540,058 | 23.9% |
| Small hardware LOD | 680,810 | 4.0% |
| Bore smoothing at baseline mesh quality | 630,304 | 11.1% |
| Combined accepted passes | 476,924 | 32.8% |

The savings overlap and must not be added. The combined model has 953,848 placed
triangles across two Base occurrences, down by 464,860. Its crossbar is 61,976
triangles and lower housing 44,248; only their latter count incorporates plugs.
Stage-one still instances a shared Base definition; no placed occurrence is lost.

The benchmark checks every retained
unselected unit's ordered triangle positions, source diffuse values and original
face IDs byte for byte. It also compares 18 matched source-pose views per accepted
candidate, with fixed original framing. Render thresholds are a 0.2% foreground
mask difference and 2% changed RGB pixels above 10/255. These are inspection
checks; all moving poses and runtime collision behavior remain separate promotion
work. Original source units and protected light/armor surfaces remain authority.
