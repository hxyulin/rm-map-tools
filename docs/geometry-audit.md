# Field geometry and STEP audit

Audited 2026-09-11 against the installed V1.2.0 and V2.0.0 source indexes,
per-product split files, element rules and generated meshes.

The lossless text split and the simulator export are different stages. A
complete split does not prove that a later product or body filter preserved
every visible part.

## Confirmed export issues

- Both missing M letters in the centre platform's ROBOMASTER lettering are
  62 `SHELL_BASED_SURFACE_MODEL` faces in `0006_1_ASM`, source body IDs
  78039–78100. The solids-only export removed them.
- That same product directly owns 14 tech-core solids and 3,348 tech-core
  sheet faces. Selecting only child products `0006_1_24..49` left the
  solids in the platform and discarded the sheets. Explicit body groups now
  partition all 3,424 directly owned bodies into the two cores and lettering.
- The fortress's coloured outer outlines, `BREP_549..554_1`, are ground
  markings. They remain in `arena-static`; standalone fortress assets contain
  the ramp bodies and white markings on top. Their world positions were
  already at ground level, so this corrects ownership rather than elevation.
- Origins previously used unions of transformed STEP vertex boxes. Rotating
  a box overestimates the footprint, and topology vertices do not describe
  curved extrema. Origins now use the actual meshed footprint centre and
  lowest point. The tech-core origin also changes when its missing parts are
  restored. Resource-zone and platform origins had smaller offsets.
- One V1.2.0 outpost body is turned 3.607 degrees relative to its footing.
  Exporting them as one rigid element put the other footing at the wrong
  angle. They now have separate assets with their exact source placements.
- The solids-only policy also discarded sheets from bases, the rune, dart
  stations and resource zones. Sheet geometry is now retained throughout the
  element export, including the companion STEP assemblies.
- OCCT can return no triangulation for a face without failing the import.
  Meshing now retries narrow faces and splits closed analytic surfaces into
  smaller angular sections, preserving their source colours. Validation
  records retries and unresolved faces rather than silently dropping them.

The exporter audits full-map body ownership before tessellation. All 79,247
V1.2.0 source bodies must have one owner; reusable arena subassets are not
counted twice. Missing and conflicting assignments fail the export.

## What the text parser accounts for

`python/audit_step.py` checks the current files rather than claiming support
for every possible STEP schema or exporter.

| Check | V1.2.0 | V2.0.0 |
|---|---:|---:|
| Indexed entities | 13,268,374 | 7,011,285 |
| Bodies linked to products | 79,247 / 79,247 | 803 / 803 |
| Occurrences with explicit transforms | 1,071 / 1,071 | 446 / 446 |
| Unresolved references | 0 | 0 |
| Unplaced geometry products | 0 | 0 |
| Non-rigid occurrence transforms | 0 | 0 |

The Rust/Python scanners retain the original entity text and references.
The model interprets ownership, topology and styles; OCCT reads the actual
curves, surfaces, knot vectors, rational weights and trimming boundaries.
Complex B-spline entities are retained even though they are indexed under
`CPLX`. They are not discarded just because the model does not implement a
spline evaluator.

## Useful fields beyond the current runtime data

| Source fields | Use and current treatment |
|---|---|
| Geometry context units | Geometry is in millimetres in both releases. V1.2.0 also defines metres for density, so examining every LENGTH_UNIT indiscriminately would give the wrong answer. The element exporter checks geometry contexts before applying its mm-to-m conversion. |
| Angle units | V2.0.0 defines degrees through a conversion to radians. OCCT handles surface/curve parameters; assembly rotations are built from direction vectors, not interpreted as degree-valued numbers. |
| Material names and density | V1.2.0 has 1,014 material-name items and 1,014 density items, including steel and 7,850 kg/m³. Useful for labels or a later material model. These are preserved in STEP but do not establish friction or restitution and are not applied to static scenery physics. |
| Presentation layers | V2.0.0 has 3,848 assignments. They can help identify parts and preserve CAD organisation. They do not justify dropping geometry. The split retains applicable assignments; the scene exporter does not turn them into visibility rules. |
| Surface and curve styles | Face, shell and body colours matter. Curve styles describe CAD edge presentation and are not filled-surface colours. V2.0.0 includes overrides and front/back styles; the renderer currently uses one surface colour on both sides. |
| Modelling uncertainty | The files declare 0.01 mm and 0.005 mm geometry tolerances. These describe source connectivity accuracy, not a request to tessellate the entire arena at that resolution. |
| Approval, dates, organisation and security metadata | Useful for provenance; no additional visible geometry. Preserved where applicable by the splitter. |

No `MAPPED_ITEM`, invisibility or transparency entity family occurs in these
indexes. The audit reports all simple and complex entity types, so additions
in later DJI releases can be reviewed rather than assumed irrelevant.

Known limits remain: OCCT heals some source faces and may lose their colours;
V2.0.0 has a documented shell-colour import loss. This audit does not prove
that OCCT implements every STEP surface and style perfectly. Mesh validation
and rendered inspection are still needed after the text-level checks.

```sh
ocpenv/bin/python python/audit_step.py v12.npz --out out/v12-audit.json
ocpenv/bin/python python/audit_step.py v20.npz --out out/v20-audit.json
ocpenv/bin/python -m unittest discover -s python -p 'test_*.py'
```

## Validated regeneration

The regenerated V1.2.0 elements passed body ownership, mesh and placement
validation: 79,247 bodies accounted for, no unresolved nondegenerate faces,
no bounding-box mismatches and no placement warnings. Two source faces have
numerically zero area (below 1e-8 mm²) and produce no triangles; these are
counted explicitly as `degenerate_faces`. Meshing recovered 90 faces with
finer tolerances, 591 by splitting periodic surfaces, 29 full analytic bands
and two very narrow faces at 0.0001 mm tessellation tolerance. No additional
wire healing or collision hull construction is applied.

The simulator now uses visual triangles directly for static collision. Its
arena boxing/extrusion module and equipment voxel API have been removed.
Deployment also replaces legacy proxy files with visual meshes for other
consumers. In particular, the old rune silhouette prism that enclosed empty
space around the centre island is no longer used. Moving target colliders
remain owned by the simulator's rule model.

All ten companion STEP assemblies also passed read-back, including bounding
boxes and face counts against the imported source. OCCT adds six base faces
and one resource-zone face during import; those deltas are recorded in the
manifest. The corrected centre-platform lettering was verified in a rendered
simulator screenshot.
