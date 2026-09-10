# Aggressive tessellation and mesh-boundary study

This study measured the previous locked-border default. The subsequent
[unlocked export](../2026-09-11-unlocked-mesh/README.md) is now deployed.

The current edge-collapse algorithm is useful, but locking every open edge
limits it heavily on CAD face fragments. A checked tolerance increase reduced
the deployed scene from 3,018,741 to 2,520,663 visual triangles, 16.5%. Separate
boundary-relaxation experiments suggest more savings than another tolerance
increase. This study did not change the deployed default.

## Candidate using the existing collision contract

`out/checked-aggressive` is a complete simulator-loadable candidate. It starts
from exact archived unsimplified rune, outpost, dart-station and base meshes.
Resource-zone and tech-core meshes are copied unchanged from the deployed
package. Terrain, centre platform and footings are also unchanged.

| Metric | Deployed | Checked candidate |
| --- | ---: | ---: |
| Placed visual triangles | 3,018,741 | 2,520,663 |
| Static collider triangles, simulator loader | 2,169,201 | 2,107,611 |
| Referenced GLB bytes | 259,669,320 | 229,180,948 |

The candidate requests a 2 mm simplifier metric independently for visual and
collider files, with a 5 mm sampled-distance acceptance limit for each. It uses
1,024 triangles per direction per changed primitive, contributing up to 6,144
sample locations. Failed sections retry at tighter error settings, then retain
the original. Open borders stay locked; exact welding, component retention and
semantic protections are unchanged.

The current deployed settings are 0.5 mm visual and 1 mm collision, with 2/3 mm
sampled limits and 96 sampled triangles per direction. Stronger sampling makes
these different quality checks, not simply a uniform scaling of tolerances.
The candidate's unchanged assets retain their previous settings and validation.

The matched-source runs produced 2,673,570, 2,520,663 and 2,795,890 visual triangles
at requested visual errors of 1, 2 and 4 mm. The coarsest request is worse because
more sections fail sampled checks and fall back to finer geometry. Collider
settings are identical in those three runs. `counts.json` has per-asset results.

Local visual comparisons are in `out/tolerance-validation/`. Base, dart station
and rune overviews retain their silhouettes, text and classified optical surfaces.
This is not exhaustive close-range visual or collision validation.

## Startup measurement

Three alternating warm-cache runs of the same simulator executable measured
median CPU scene-ready time of 5.418 seconds for the current default and 5.084
seconds for the checked candidate, a 6.2% reduction in this small local sample.
Manifest/semantic verification fell from 0.990 to 0.830 seconds. Median collider
parsing was effectively unchanged at 2.016 versus 2.017 seconds. One candidate
run was slower than its paired default run. This is not a cold-start guarantee
or evidence of an FPS/physics-tick speedup. CPU scene-ready is the final instance
load log, not the first displayed GPU frame.

Raw run records are in `startup.json`. Logs and screenshots remain at
`out/tolerance-startup/`. The benchmark used the previous study's
`benchmark_startup.py` with three runs.

## Boundary treatment is the larger opportunity

After welding exactly equal positions, the fractions of current triangles
touching an open edge are 95.5% for the large resource-zone section, 91.8% for
the large dart-station detail section and 90.0% for the large base detail section.
Every vertex on those edges is currently locked. Some edges are actual openings;
others may be disconnected CAD face seams. Geometry alone does not identify
which is which.

`border_probe.py` uses the same edge-collapse algorithm and component-retention
step, but allows open boundaries to simplify. No approximate welding is used.
At a 0.5 mm metric, with 4,096 sampled triangles per direction:

| Current visual section | Before | Experimental after | Reduction | Sampled max distance |
| --- | ---: | ---: | ---: | ---: |
| Resource zone n1 p1 | 335,459 | 159,482 | 52.5% | 2.108 mm |
| Dart station n1 p5 | 168,320 | 44,219 | 73.7% | 1.507 mm |
| Base n1 p1 | 154,049 | 44,273 | 71.3% | 1.944 mm |

These three sections repeat twice in the arena. Their combined experimental
saving is 819,708 triangles, 27.2% of the current scene. This is not additive to
the tolerance candidate: the experiments simplify overlapping source geometry.
They are isolated section studies, not a deployed full-package reduction.

Distance measurements are relative to the **current already simplified visual
meshes**, not original STEP or original collider geometry. There are 24,576
sample locations per section, uniformly selected by triangle index rather than
weighted by area. They do not certify a maximum surface distance or preservation
of every hole, thin wall, silhouette, contact surface or joint attachment.
Disconnected components are retained, but that alone does not preserve topology.
The isolated experimental GLBs are marked `study_only` and are not simulator
packages. No production collider contract was weakened.

Raising the experimental metric to 2 mm produced sampled outliers near 10 mm
in the resource and dart detail sections, and near 20 mm in the separate dart
frame. The 0.5 mm boundary experiment is the more useful starting point.

A separate grid-welding probe at 0.001, 0.01 and 0.1 mm reduced counts less than
boundary relaxation. It can merge components and move vertices, so it is also
inspection-only. Results are in `seam-probe.json`. Its sample budget is 1,024
triangles per direction, not the denser boundary probe's 4,096.

The next implementation should distinguish CAD seams from intentional boundaries,
allow measured simplification along suitable borders, and test holes and contact
surfaces explicitly. Removing internal hardware or small CAD features remains a
separate opportunity. Simply increasing global tolerance is a weaker approach.

## Source recovery and the initial sweep

The previous temporary `out/semantic-detail-source` was no longer present.
Archived packages contained exact originals for four affected assets, but only
older, denser exports for the resource zone and tech core. `restore_source.py`
creates `out/tolerance-source` from those archives and checks file hashes.
`source-record.json` records which files match the previous export exactly.

An initial sweep used the same reconstructed inputs for all four runs. Its control
has 3,761,695 visual triangles, so it must not be mistaken for today's 3,018,741
triangle deployment. It yielded 3,252,318 at moderate settings, 3,018,109 at
aggressive settings, and 3,181,457 at coarse settings. The archived resource and
tech-core inputs are too dense for a useful direct deployment comparison.

The later matched-source study therefore keeps those two deployed assets as-is.
Its `checked-*.json` configs describe the actual candidate. Input meshes are
never repeatedly simplified in a production package. The isolated seam/border
probes explicitly study an additional pass and report that limitation.

## Exporter change and validation

The exporter now accepts `deviation_samples` in JSON defaults or per-asset
settings. Values must be integers from 96 to 16,384; the existing default is 96.
The selected budget is recorded in the output metadata. A denser independent
check of the initial aggressive sweep found 1–2.5 cm outliers missed by the
96-triangle checks, which motivated using 1,024 for the final candidate.

All 64 Python tests passed, including a synthetic local deviation that sparse
sampling misses but denser sampling detects, and validation of the new setting.
The actual simulator inspector successfully loaded each full study package and
verified its semantic/collision contract. `counts.py` uses the selected glTF scene
and arena placements for visuals, and the simulator loader for static colliders.

Reproduction scripts, configs and logs are alongside this report. Run Python
scripts from the repository with `ocpenv/bin/python`. CAD files and screenshots
stay local under `out/`. No simulator code, default assets or source reference
assets were changed by this study.
