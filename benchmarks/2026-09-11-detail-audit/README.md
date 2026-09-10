# Detail audit and angular-tolerance candidate

Date: 2026-09-11. Compare the existing `out/simulation-runtime` package with
`out/detail-preview-runtime`, built through the new JSON job runner. These are
fresh GLB traversal counts, before GPU culling, procedural optics and debug
geometry. The simulator loader independently confirmed the new collider total.
The semantic-reference composite from the simulator task is a different package
and is not the baseline here.

| Placed geometry | Simulation package | Detail candidate | Reduction |
|---|---:|---:|---:|
| Visual triangles | 7,308,820 | 5,785,692 | 20.8% |
| Static collider triangles | 4,929,741 | 3,973,663 | 19.4% |

| Asset | Visual before | Visual after | Collision before | Collision after |
|---|---:|---:|---:|---:|
| Resource-zone | 2,468,504 | 1,775,862 | 1,988,184 | 1,528,012 |
| Base | 1,305,338 | 943,050 | 1,009,088 | 817,564 |
| Dart-station | 1,242,440 | 888,038 | 1,008,362 | 771,998 |
| Tech-core | 288,830 | 175,034 | 209,916 | 141,898 |

The four assets use 0.9 rad visual and 1.2 rad collision angular tolerance.
Linear tolerances stay at 4 mm and 6 mm. Other assets retain their settings.
Copied rune/outpost files are byte-identical between the packages. All source
faces are retained except the existing, explicit centre-logo collision exclusion.
No fastener deletion, hole filling or analytic shader substitution occurred.

## Why the count is high

The largest resource-zone source part, `7000001_1_ASM`, has 38,894 faces. At
simulation visual settings it contributes 670,718 triangles per instance:

| Surface | Triangles | Share |
|---|---:|---:|
| Plane | 240,193 | 35.8% |
| Cylinder | 170,023 | 25.3% |
| Torus | 109,408 | 16.3% |
| B-spline | 76,623 | 11.4% |
| Cone | 38,614 | 5.8% |
| Sphere | 35,857 | 5.3% |

The <=5 mm radius subset contributes 124,628 cylinder triangles, 99,409 torus
triangles and 33,944 sphere triangles. For a torus this is its minor radius,
not its overall extent. The relaxed visual angle reduces all sphere triangles
to 15,813 and torus triangles to 59,057 without replacing their analytic shapes.
The complete source-part sample drops to 474,598 visual triangles and 398,757
collision triangles, versus 670,718 and 525,843 at simulation settings.

There are 2,014 planar faces with inner wires, accounting for 152,941 triangles.
Only 51 openings pass the exact circular-wire detector with radius <=5 mm;
other loops may be noncircular or represented by spline curves. There are also
3,010 small, reversed cylindrical faces, contributing 44,571 wall triangles.
These are diagnostic candidates, not a count of proven removable holes.
Opening and wall counts overlap; filling holes would also change adjacent plane
triangulation, so their current triangle count is not a savings estimate.

The source imports as 5 solids and 38,002 shells outside those solids. Of those
shells, 37,978 contain only one face. Small-body filtering would therefore delete
fragments of larger objects. The 34,368 bodies whose largest extent is <=30 mm
must not be treated as 34,368 fasteners. Connected geometry and source ownership
need to be recovered before hardware can be classified and removed.

Of 367 spherical faces, 51 are hemispheres and 316 are trimmed patches. None is
a full sphere. This makes a general sphere shader a lower-priority experiment
than detail classification and angular-tolerance control for this part.

## Validation and limits

- Field and element exports passed, with all 79,247 source bodies assigned,
  no read failures, no bounding-box mismatches and no warnings.
- The simulator's existing `inspect_assets` executable accepted the candidate
  and built 2,452,800 ground, 561,401 fixture and 959,462 equipment triangles.
- The Python suite passed 52 tests, including new hole/sphere detection tests,
  sphere error samples, policy-file preset selection and job validation.
- Base and resource-zone overview comparisons were rendered with identical
  cameras and inspected. Text, lights and overall geometry remain visible.
  These views do not certify close-range optical fidelity or every contact.
- Linear tolerance is unchanged, but changing angular tolerance still changes
  the mesh. Synthetic deviation tests are not a complete imported-geometry proof.
- No FPS or physics-tick improvement is claimed. The audit ran alongside exports
  and other development; recorded times are diagnostic, not a timing benchmark.
- Semantic rules remain pinned to their reviewed input. No rules were blindly
  repinned to this candidate. Terrain and articulated defaults were retained.

## Reproduce

Run from the repository root in the OCP environment. Output directories must be
new. Change paths in the JSON jobs when retaining an existing run.

```sh
ocpenv/bin/python python/audit_geometry.py rules/audit-resource.example.json
ocpenv/bin/python python/export_job.py rules/export-detail-job.example.json
python3 benchmarks/2026-09-11-detail-audit/compare_packages.py \
  out/simulation-runtime out/detail-preview-runtime /tmp/package-comparison.json
ocpenv/bin/python benchmarks/2026-09-11-detail-audit/render_comparison.py \
  out/simulation-elements/base.glb out/detail-preview-elements/base.glb \
  out/detail-preview-validation/base-comparison.png
```

The full face-level audit is in `out/resource-detail-audit.json`, ignored along
with the CAD artifacts. `resource-summary.json` retains aggregate evidence;
`package-comparison.json` records counts and file hashes. Screenshots are in
`out/detail-preview-validation/base-comparison.png` and `resource-comparison.png`.
See [detail optimization](../../docs/detail-optimization.md) for configuration
and the remaining hardware/hole-removal work.
