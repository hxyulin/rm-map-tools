# Geometric deduplication exploration

Commit `34021d7` contains the GLB sharing changes and tar.zst benchmarks.
This follow-up is a read-only investigation of additional geometry reuse.
No deduplicated STEP or replacement runtime assets were produced.

## Results

The CAD scans used the complete original V1.2.0 STEP, 993.30 MB, with 79,247
body definitions. This is a different denominator from the ten exported
STEP assets in the compression benchmark. Checksums are pinned in the reports.

| Scan | Findings |
|---|---|
| Identical ordered STEP geometry graphs | 49 redundant body definitions; one pair of products with matching body geometry |
| STEP graphs in a common rigid coordinate frame | 15,014 candidate redundant bodies across 6,009 groups |
| Candidate geometry-record size bound | 40.19 MB, 4.05% of the original STEP, before replacement placement/style overhead |
| Whole-node mesh rotation/reflection matching | 182 matching nodes, 51,961 triangles, 0.96% of decoded triangles |
| Mesh matches across distinct source product IDs | 148 matching nodes, 6,957 triangles, 0.129% of decoded triangles |

Whole-node results include repeated source occurrences already addressed by
instancing and the road present in both arena-static and the separate road
asset. They must not be counted as wholly new savings. Input GLBs are the
existing `rm2026-field-elements` visual files, counted once per asset file;
full-map and manifest placements were not expanded. Mesh matching used the
24 proper axis-aligned rotations and 24 reflections, arbitrary translation,
a bijection of all unique vertices within 0.01 mm, and matching oriented
triangle connectivity. Colours are checked separately. Different triangulations
and arbitrary-angle rotations are not found by this mesh pass.

## CAD candidate checks

Rigid normalization found mostly sheet details: 5,956 sheet candidate groups
and 53 solid groups. Some repeated sheets have areas as small as 0.006 mm².
Counting bodies therefore overstates the potential byte savings. The 40.19 MB
bound sums 719,939 candidate geometry records after excluding records still
reachable from retained bodies. It is only a bound for the detected candidates,
not a bound on every possible form of geometric deduplication. The calculation
ignores new occurrence records and style/metadata remapping, and does not predict
compressed size.

Five pairs were extracted without re-exporting their geometry and imported
independently into OCCT: three sheet pairs and two solid pairs. The most rotated
candidate in each selected group was checked. All ten shapes were valid.
Applying the proposed rigid transforms gave matching area, and matching volume
for solids. Bidirectional boolean subtraction completed and left zero area
for every pair. The largest bounding-box difference was 1.27e-10 mm.
These checks support the five sampled pairs only; all 15,014 candidates have
not been CAD-validated. See [occt-sample-validation.json](occt-sample-validation.json).

The text scans ignore entity IDs, simple geometry display names, whitespace
and comments. The strict scan otherwise preserves numeric spelling and ordered
topology. The rigid scan expresses 3D points and directions in the first
explicit axis frame, with point quantization of 0.00001 mm and direction
quantization of 1e-9. It preserves 2D parameter-space coordinates. 7,870 bodies
without an explicit axis frame were skipped. Mirror shapes, reordered topology,
and scalar numeric spelling differences remain outside this CAD scan. Appearance,
product identity, tolerances and annotation ownership still need explicit handling
before any candidate is replaced.

## What to try next

A bounded prototype should share a repeated group of sheet details inside one
product, preserve per-occurrence names and styles, and compare both raw STEP and
tar.zst sizes after OCCT re-import. Grouping related sheets may avoid creating a
separate assembly occurrence for every microscopic face. The newly measured
ceiling for these candidates is modest; the observed 50.8% GLB benchmark reduction
and tar.zst compression are much larger established wins.

The audit code is exploratory and does not run during exports. Raw candidate
transforms and extracted sample STEP files are under `out/geometric-deduplication`.
The complete 14 MB candidate list remains there; this directory retains its
summary and the leading groups in [step-rigid-summary.json](step-rigid-summary.json).
Other reports are [step-exact.json](step-exact.json) and
[mesh-congruence.json](mesh-congruence.json).

## Reproduce

From the repository root using the source-pinned `v12.npz` index:

```sh
PYTHONPATH=python ocpenv/bin/python python/audit_geometry_duplicates.py \
  v12.npz --out out/dedup-repeat/step-exact.json
PYTHONPATH=python ocpenv/bin/python python/audit_body_symmetry.py \
  v12.npz --out out/dedup-repeat/step-rigid-candidates.json
PYTHONPATH=python ocpenv/bin/python python/audit_mesh_duplicates.py \
  /Users/hxyulin/dev/RM/assets/rm2026-field-elements \
  --out out/dedup-repeat/mesh-congruence.json
PYTHONPATH=python ocpenv/bin/python python/validate_body_symmetry.py \
  v12.npz out/dedup-repeat/step-rigid-candidates.json \
  --out out/dedup-repeat/samples
PYTHONPATH=python ocpenv/bin/python -m unittest discover -s python
```
