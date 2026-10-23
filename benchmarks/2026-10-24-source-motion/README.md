# Source hierarchy: requested motion identification

This is a source-bound identification pass, not an animated export or a runtime
joint package. Original STEP, hierarchical STEP, meshes and simulator assets
are unchanged. It defines eight mechanism records across fourteen placed uses:
two Outpost rotors, two Rune faces, six Base covers, two Base target carriages,
and two Dart-station doors. It does not assert these are every moving mechanism
in the field; the separate Dart platform and Tech Core are outside this scope.

## Evidence and findings

The authoritative selection namespace is original STEP product/body/shell/face
IDs, qualified by source SHA-256. Whole component selectors refer to
`out/rmuc2027-hierarchy/hierarchy.json`. Mesh/native ordinals and 2026 numeric
pivots are not copied into 2027 source coordinates.

- **Outpost:** three `outpost/rotor/module-*` components share one axis. The
  source central 95 mm cylindrical surface #2010905 establishes the axis through
  `[-9.437883451525, 1137.4399976, -1.0455166794]` mm, direction `[0,1,0]`.
  Parent occurrence transforms preserve the source's slight field tilt. Tower,
  upper dart target and other fixed clusters are excluded. Existing 2027 module
  membership is used; carrier/fasteners outside these groups still need review.
- **Rune:** five long arms on each bank are moving. The common shaft axis is
  confirmed by original 53 mm cylinders in bodies #161473 and #83346, with
  perpendicular line discrepancy below 0.000001 mm. Witness surface #160752
  gives point `[-423.4287973876,121.5088436247,93]` mm and oriented direction
  `[0.9355854080889,-0.3531004731958,0]`. Both banks use the **same signed common
  angle**, which appears clockwise/counterclockwise from opposing viewpoints.
  User review confirms that the center hubs and short spokes rotate with the
  arms. Hub source units #161473 / #83346 (central R-logo/shaft-end assemblies)
  stay stationary; all other bank hub units now rotate. The older 2027 binding
  moved only long arms. The preview retains original materials on the fixed
  center assemblies so the stationary R remains visible.
- **Base covers:** main bodies #4314593, #4353403, #4392221 are identified.
  Attached details and the linkage trajectory remain unresolved. Neither the
  2026 illustrative outward/down slide nor the old 2027 250 mm radial slide
  establishes real travel. Figures 4-11/4-12 establish closed/open states but do
  not supply a complete actuator model. An arbitrary large cylinder on a cover
  is not assumed to be a hinge.
- **Base dart target:** its stationary crossbar is body #4268930. Product-local
  X maps to opposite signs of field Y for the two Base placements. Travel is
  ±280 mm from the initial target location. Bodies #4072376/#4077428 are the
  central target/light **candidate core**, not a complete certified carriage.
  Sensor fittings, surface-model details and fixed end drives need the finer
  partition before animation. The old reviewed-motion policy classified all
  these bodies as fixed; it is incomplete for this task.
- **Dart door:** guide bodies #3301978/#3317722 have matching long straight edge
  directions `[0,-0.9659258262891,0.2588190451025]` in source coordinates. Opening
  is upward along that direction; rails remain fixed. `dart-station/door-candidate`
  provides the candidate moving ownership, pending a hardware sweep review.
  End stops remain unknown. The 2026 1.16448 m stroke is illustrative and is not
  transferred. Door and sliding launch platform are separate mechanisms.

All points above are original product-local millimetres, not glTF metres or
simulator FLU. `motions.json` includes original occurrence matrices and transformed
field axes, with separate confidence/review fields. Unknown motion is never
silently converted into a fixed classification. No invented limits are installed.

## Rulebook and 2026 reference

The attached 2027 V1.0.0 rulebook was extracted locally and Figures 4-11/4-12
were inspected as rendered pages. Its SHA-256 is recorded in `motions.json`.
Printed page numbers are one less than PDF page numbers.

- Section 4.2.2, pp. 37–39: Base closed/open states and dart sensor/light assembly.
- Section 5.6.1, pp. 95–96: Outpost middle armor rotation, 0.8π rad/s after at
  most 5 seconds, with both teams retaining the same rotation direction per match.
- Section 5.6.3, pp. 96–97: Rune common-axis rotation and viewpoint convention.
- Section 5.7.3, pp. 110–111: door approximately 7 s to open; Base target and light
  keep their relative pose, with ±280 mm field-width motion. Opening duration
  does not determine a geometric stroke.

2026 references: `rules/semantics-legacy-field.json`,
`rules/semantics-legacy-equipment.json`, `docs/base-dart-target.md`,
`docs/base-reconstruction.md`, `docs/dart-window.md`. The source-bound 2027
`rules/reviewed-motion-rmuc2027.json` is also compared. Their limitations are
retained rather than upgrading demo parameters into mechanical measurements.

## Reproduce and validation

```sh
ocpenv/bin/python benchmarks/2026-10-24-source-motion/discover.py
ocpenv/bin/python benchmarks/2026-10-24-source-motion/build.py
```

Outputs: `out/rmuc2027-source-motion/analytic-inventory.json` (2,053 original
body/shell units with source bounds and cylinder witnesses) and `motions.json`.
Discovery reads only exact source records; it does not import/heal/re-tessellate.
Bounds use source topological vertices and are inspection hints, not certified
curved-surface bounds. PCA axes are diagnostic; the door uses original long-edge
endpoint directions instead. Joint lines use selected central analytic surfaces,
not arbitrary first cylinders or largest dimensions.

Checks pass for source/hash preservation, hierarchical STEP payload hash, source
component/body existence, axis normalization, source Rune shaft coaxiality,
Dart guide parallelism, disjoint selected whole-component faces, and both Base
placements' field-width axes. These are ownership/frame checks, not collision
clearance or complete mechanism validation. Animated GLBs and runtime binding
remain the next stage after the unresolved fine partitions are reviewed.

## Interactive review

Run `ocpenv/bin/python benchmarks/2026-10-24-source-motion/prepare_review.py`
to stage pinned unsimplified references, then
`python3 benchmarks/2026-10-24-source-motion/serve_review.py`. Open
`http://127.0.0.1:8767/?case=rune` for the corrected Rune review.
Viewer code lives beside this report. Three.js 0.180.0 modules and its MIT
license are isolated under the ignored output `review/vendor/`; they do not
change the project dependency set. Geometry is loaded through local symlinks,
never rewritten. Diagnostic poses and exported review notes are not runtime
bindings.

### Layer review update

User review found missing Outpost carrier layers and Base target layers.
`complete_layers.py` creates a separate review-only partition of upper-cluster
source body #2101579, selecting 91,622 existing triangles for the carrier/arms.
It does not move the complete connected upper body. This uses an explicit finite
manual triangle envelope; the carrier/frame interface still needs confirmation.
The output retains all 251,597 original upper-cluster triangles with an exact
float32 triangle-position multiset check. Source NPZ/GLB files stay unchanged.

The candidate Base target now contains 62 source bodies/shells, including central
backing, side plates and fittings, rather than only the two detector/light bodies.
The long rail and end hardware remain context. Exact selectors and the Outpost
triangle selection are recorded in `out/rmuc2027-source-motion/layer-review.json`
and `outpost-carrier-triangle-selection.npz`. This is a review selection, not a
certified kinematic partition or installed joint.

Reproduce additions with `ocpenv/bin/python
benchmarks/2026-10-24-source-motion/complete_layers.py`, then rerun `build.py` and
`prepare_review.py`. The browser verifies zero rest-matrix change before/after
sweeps for both updated cases; total source triangles remain 568,449 for Outpost
and 709,354 for Base. Browser resources now use content-hash query parameters to
avoid displaying a stale partition during repeated reviews. Door and cover
classification code is unchanged.

### Top correction, full door travel and shield inspection

The user confirmed Rune, Base target and Dart door membership, but flagged a
small piece of the Outpost top as rotating. The manual carrier envelope included
1,458 triangles in five disconnected top patches. `complete_layers.py` now
retains the principal connected carrier only (90,164 triangles); those top
patches remain present and stationary. Connectivity uses 0.00001 mm rounded
aliases for discovery only and changes no vertex or triangle data.

The door slider now runs **0% closed → 100% open**, replacing the ±100 mm
inspection displacement. The source pose is the open endpoint. The original
source lowest door point is product Y = -1173.533596 mm; a floor reference at
Y = 150 mm and the rulebook's 205 mm platform height give closed bottom Y = -55 mm.
Travel along the original 15° guides is **1157.991189 mm**, with signed joint
coordinates [-1157.991189, 0] mm. The source coordinate endpoint and frame check
pass; the closed stop remains an inference, not an actuator measurement.

Base shields have separate outward radial groups and a 0–100% opening control.
At full opening, each translates 170 mm outward and 45 mm down, exposing only
the existing unsimplified CAD interior. This is explicitly an **inspection
motion**, following the older illustrative preview; it does not certify the
actual linkage or add reconstructed internals. Open/Close buttons supplement
the slider. Rune and target selections stay unchanged.

Browser checks for all five cases confirm fixed/context matrix deltas stay zero
under diagnostic motion, all geometry returns exactly to its source rest matrix,
and source triangle totals remain unchanged. At door closure, translation is
[0, 1118.533596, -299.710174] mm, giving the required -55 mm product-local bottom.
