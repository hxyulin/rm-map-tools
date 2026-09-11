# STEP detail audit and export jobs

The next optimization pass targets small-radius detail and perforated surfaces.
Keep the source STEP intact and export candidates to a new directory. The
simulation preset remains the default. The experimental detail policy changes
angular tolerances only for resource-zone, base, dart-station and tech-core.

For package setup and JSON jobs, see [Exporting](exporting.md#configure-a-complete-export). For the full reduction workflow, see [Simplification](simplification.md).

## Audit source geometry

```sh
ocpenv/bin/python python/audit_geometry.py rules/audit-resource.example.json
```

The audit job chooses exact source product names, small-detail thresholds and
named tessellation samples. Each sample clears cached triangulations and uses
the production face-recovery path. An incomplete mesh fails the audit. The JSON
report records:

- Triangle counts by analytic surface type and by face, plus recovery statistics.
- Small-radius cylindrical, spherical and toroidal surfaces. Torus radius means
  the minor radius, which describes its rounded cross section.
- Small solids and shells with bounding boxes and triangle costs.
- Inward-facing cylinder candidates and circular inner wires on planar faces.
- Full spheres, hemispheres and trimmed spherical patches.
- Mesh bounds and elapsed tessellation time for each sample.

Face and body indices are local OCCT import indices qualified by the split STEP
file's SHA-256. They are diagnostic locations, not original STEP entity numbers
or stable semantic IDs. Counts describe one imported part, before scene placement.
Candidate categories overlap and their triangle counts must not be added as
estimated savings. The report refuses to overwrite a previous result.

## What can be removed

Small extent alone is insufficient evidence of a fastener. In the resource-zone
sample most imported bodies are single-face shells. A tiny shell can be a face
of a larger structure, a marking, or an optical surface. Group connected geometry
and recover source ownership before adding removable-fastener classifications.
Keep verified visual and collision exclusions independent.

Circular inner wires identify openings in planar faces. The same through-hole
can have an opening on both sides, so opening counts are not unique hole counts.
Reversed cylinders are weaker candidates because an open shell's orientation
does not establish a solid interior. A hole-removal operation must rebuild the
surrounding faces and retain closed, valid collision geometry. Removing the wall
triangles alone is incorrect. OCCT provides a
[defeaturing algorithm](https://dev.opencascade.org/doc/occt-7.6.0/refman/html/_b_rep_algo_a_p_i___defeaturing_8hxx.html)
for removing features such as holes and fillets, but we have not enabled it on
these fragmented source shells.

For spheres and cylinders, first tune the mesh. OCCT uses both
[linear and angular deflection](https://github.com/Open-Cascade-SAS/OCCT/wiki/mesh),
so a tight angular setting can retain substantial detail even when its absolute
size is small. The audit's relaxed-angle samples leave linear tolerance unchanged.
Synthetic tests check sphere and cylinder deviation, but these tests are not an
exhaustive error bound for every imported face.

A sphere shader would require simulator rendering changes and a separate
collision representation. Trimmed spherical faces also need their boundaries,
materials, depth and shadows preserved. No shader or near-sphere substitution
is implemented here. The current detector recognizes exact analytic surfaces;
it does not fit arbitrary B-splines to spheres.

## Experimental candidate

```sh
ocpenv/bin/python python/export_job.py rules/export-detail-job.example.json
```

The candidate policy uses 0.9 rad visual and 1.2 rad collision angles for the four
assets above, while retaining their 4 mm and 6 mm linear tolerances. Terrain,
rune and outpost retain simulation settings. This is an opt-in comparison, not
a new default for close camera work or scoring surfaces. Copied animation-ready
assets keep their source meshes. The example writes `out/detail-preview-runtime`;
it does not install assets or repin semantic rules.

The first resource-zone sample dropped from 670,718 to 474,598 visual triangles
and from 525,843 to 398,757 collision triangles, relative to the simulation
preset. The deployed package drops from 7,308,820 to 5,785,692 visual triangles and
from 4,929,741 to 3,973,663 static collider triangles. See the
[benchmark report](../benchmarks/2026-09-11-detail-audit/README.md) for validation. No frame-time or physics speedup is inferred from triangle
counts.

## Simplify the bound package

The subsequent [mesh simplification pass](mesh-simplification.md) reduces the
base, dart-station and other semantic geometry after binding, without reusing
triangle selectors on a different source export. It provides the larger reduction
and measured startup improvement that tessellation tolerances alone did not.
