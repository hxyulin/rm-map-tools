# Grouped sheet instancing prototype

The prototype stores a group of 67 sheet bodies once and places it six times,
replacing 402 distinct definitions with 67 definitions and six assembly
occurrences. It uses native AP214 product/assembly references. The reference
geometry is copied from the source STEP without tessellation or surface
reconstruction. This is an isolated experiment; production exporters and
installed simulator assets were not changed.

## Measured size

| Scope and format | Before, bytes | After, bytes | Reduction |
|---|---:|---:|---:|
| Isolated repeated group, STEP | 1,243,487 | 225,690 | 81.85% |
| Isolated repeated group, tar.zstd level 9 | 122,891 | 26,611 | 78.35% |
| Complete parent product, STEP | 81,333,913 | 80,317,434 | 1.25% |
| Complete parent product, tar.zstd level 9 | 14,687,467 | 14,658,879 | 0.19% |

The candidate tar.zstd archives include a 30,078-byte identity sidecar as well
as the STEP file. Baseline archives contain the STEP only, which already holds
the original body definitions and names. Archive paths and tar metadata are
normalized. Both sides use zstd 1.5.7, level 9, one thread. Every archive member
was decompressed and SHA-256 checked. Raw STEP figures exclude the sidecar.
STEP provenance headers record the extraction tool and original source hash.

The group alone saves about 78% after compression. Inside the complete parent
product, `001_1_ASM`, it saves about 1.02 MB of raw STEP but only about 29 KB of
tar.zstd, roughly 0.19%. Compression already captures much of the repetition
when the other product geometry is present. These are results for one group
and one parent product, not the whole map or every candidate in the prior audit.

## Selection and identity

The source is V1.2.0 with SHA-256
`90daa72dfaf83989e9fd81b9ff1fdebcb297fcbbe07006c62f7670d33d454a23`.
The seed is body #93562, previously validated against #93986. Candidate body
families must have one member at each of the seed's six rigid placements.
Selections cannot overlap, must belong to the chosen product, and must have
matching effective source style assignments. All 67 selected families passed
the style check. Actual imported geometry is checked after selection; approximate
matrix matching alone cannot approve a replacement.

Shared definitions keep the reference bodies' original IDs and display names.
Other occurrences reuse those definitions, so their distinct original names
are recorded in [identity-map.json](identity-map.json), not as separate native
body names in STEP. The sidecar maps every reference body to the original body
ID and name at each placement, and identifies the generated occurrence names.
It ships as `identity-map.json` inside the candidate archives. The loose output
folder calls the same file `selection.json`.

## Geometry and appearance checks

- All 402 changed faces passed a bijective correspondence check and OCCT boolean
  subtraction in both directions. Every subtraction left zero area.
- Both imported group shapes were valid. The largest bounding-box difference
  was 1.58e-9 mm and the largest face area difference was 5.16e-9 mm².
- Assembly traversal confirmed 67 stored faces and 402 placed faces. It also
  verified each placed face's colour against the baseline.
- The complete parent product retained all 12,194 placed faces, their colours,
  areas and bounds. Both imported full-product shapes were valid. Stored faces
  fell from 12,194 to 11,859, corresponding to 335 removed definitions.
- The 1,027,393 geometry records reachable from the unchanged remainder were
  retained and copied without rewriting. Full-product validation did not repeat
  boolean subtraction on the unchanged remainder; the replaced 402 faces were
  already fully checked in the isolated test.
- The Python suite passed 117 tests. New tests cover disjoint group selection,
  mirror rejection, colours on shared definitions, and rejecting a colour change.

There is an importer compatibility issue to resolve before promoting this to
production. Our existing flat `validate_parts.analyse` colour lookup reports
`None` for shared occurrences. The imported OCCT definitions do retain their
colours. The prototype's assembly-aware traversal reads colours from definitions
before applying occurrence locations, and checks them face by face. The raw
flat-reader output remains in [results.json](results.json) so this distinction
is visible. The same flat-reading pattern exists in the ordinary tessellator;
it should be updated and tested before using these STEP assemblies as general
export inputs. No claim is made about other CAD applications, loading time or
runtime memory usage.

## Artifacts and reproduction

Verified artifacts are under `out/grouped-sheet-prototype/verified`:

- `baseline.step` and `shared.step`: the isolated 402-face group.
- `baseline-product.step` and `shared-product.step`: the complete parent product.
- Corresponding `.tar.zst` archives, with identity maps included for candidates.
- `selection.json` and `results.json`: source identity mapping and measurements.

The prototype script hash and file checksums are recorded in the results.
Earlier `run1`, `run2`, `run3` and `final` folders are intermediate experiments;
use `verified` for the measurements in this report.

```sh
PYTHONPATH=python ocpenv/bin/python python/prototype_sheet_groups.py \
  v12.npz out/geometric-deduplication/step-rigid-candidates.json \
  --out out/grouped-sheet-repeat --whole-product
PYTHONPATH=python ocpenv/bin/python -m unittest discover -s python
```

For distribution size alone, this experiment supports keeping group deduplication
optional while using the already measured GLB sharing and tar.zstd compression.
The next adoption work would be assembly-aware consumers and identity handling,
followed by a measured trial across more groups. Scaling the group-local saving
to the entire map would be misleading.
