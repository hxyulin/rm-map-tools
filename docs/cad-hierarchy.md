<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Hierarchical source STEP export

`python/cad_hierarchy.py` writes the reviewed work parts into one real STEP
assembly. The result contains original analytic CAD faces and curves, not a
triangle-mesh conversion. Shared model definitions are referenced at their
original placements. It is suitable for opening and selecting named components
in a CAD editor before further processing.

The [RMUC 2027 policy](../rules/hierarchy-rmuc2027.json) combines the reviewed
[partitions](cad-partitions.md), [remaining equipment](remaining-equipment-rmuc2027.md),
[terrain/source units](terrain-equipment-rmuc2027.md), and
[complete equipment compositions](appearance-compositions-rmuc2027.md).
The Base stays one work group containing its complete original bodies; no finer
functional Base partition has been reviewed.

## Reviewed motion preparation

The default RMUC 2027 policy now runs [source motion preparation](cad-source-motion.md)
before grouping. It corrects Outpost carrier ownership, Rune hubs and fixed logos,
Base target/shield ownership and the Dart door. The counts and original tree below
describe the earlier 116-part checkpoint; the new motion-prepared hierarchy is a
separate verified output. Body #2101579 is the explicit exception to whole-solid
retention: complete original faces form two open surface parts, with no geometric
approximation. See the source-motion guide for the wrapper and validation contract.

## Organization

```text
rmuc-2027
  equipment
    red-base-with-footing / blue-base-with-footing
      base / source-model
      base-footing / body-4069550
    red-outpost-with-footing / blue-outpost-with-footing
      outpost / fixed / ...
      outpost / rotor / module-0, module-1, module-2
      outpost-footing / ...
    red-dart-complete / blue-dart-complete
      dart-station / frame, rails, door-candidate, deck-and-shared-hardware
      dart-station-timber / ...
      ancillary products / ...
    red-high-point-complete / blue-high-point-complete
      upper/lower terrain, fan frame, fan instances
    red-resource-complete / blue-resource-complete
      resource-area / ...
      energy-unit / ... (six source occurrences per side)
    rune / banks / bank-a, bank-b / arm-0..4, hub-cluster
    rune / support-and-shared
    technology-core / pedestal-and-shoulder, arm-and-shared, toolhead
  terrain
    floor, central deck, tunnel sides, roads, fortresses, other terrain
  fixtures
    remaining fan instances, fan frames, grilles, drone pads
```

Each slash-separated work path becomes an actual intermediate STEP assembly.
The same Rune/Outpost/fan/product definition can be referenced by its placed
instances; the export does not concatenate a fresh copy of every placed mesh.
The original source's mechanical meaning remains separate: work labels do not
install joints or certify that a proposed group can move independently.

The reviewed full-field export has **116 work-part definitions**, drawn from
32 body-owning products and 426 original body definitions. It retains all
**110,586 original face definitions**. Its 68 whole-product occurrences account
for **644 original placed bodies and 214,794 placed faces**. Definition counts
and placed counts describe different things.

## How preservation works

A surface-model container can contribute different original shells to several
work parts. Reusing its original wrapper/product IDs across those parts inside
one STEP would merge their identities. The exporter therefore gives each work
part a private namespace for its product, representation, styles, metadata and
narrowed surface-model wrappers. Original geometry and topology descendants
remain shared, retaining their source IDs and byte-identical entity records.
Original solid bodies remain solids; surface-model shells remain surfaces.
No Boolean operations, faceting, capping or healing/re-export through OCCT occurs
in the writer. The module-0 open cover candidate is not overlaid on the whole
upper solid; it would duplicate faces and requires a separate topology decision.

Reference remapping skips quoted strings and comments, preserving literal
numbers, names and full STEP appearance data. Product names alone are replaced
with the work-part names. Source face IDs, body-wrapper mappings, private-ID
maps and original occurrence paths remain in `hierarchy.json`. Full source
style records are retained; the exporter does not replace them with preview
RGBs, procedural colors or the unpainted gray display fallback.

Leaf geometry stays in its original product coordinates. Equipment-composition
assemblies get a translated local origin near their placed bounds, with relative
child transforms and a compensating parent placement. The field root keeps the
original source frame: **millimetres, Z up**. Coordinate values are not baked into
new geometry. The source's repeat placements are each assigned exactly once;
compositions that overlap another composition are rejected.

Before publication, the exporter reparses the STEP and checks:

- Every reference resolves and every original face ID remains.
- Original geometry records retain a matching byte digest.
- Private records match the selected source records exactly after the intended
  wrapper/list filtering, reference renumbering and product-name substitution.
- Every encoded assembly edge and rigid pose matches the intended tree.
- Every whole-product source-world pose remains exactly once, including repeats.

`--validate-native` also imports the complete geometry and assembly names through
OCCT/XCAF, requiring one root assembly and the expected placed face count.
It disables full-field per-face presentation-label transfer: style records have
their separate exact preservation proof and native colored-instance regression,
and populating every display/metadata label is unnecessary for coverage.
Native import is a check;
its healed working representation never replaces the written source records.
The tessellation helper resolves colors in each native definition before
applying instance locations, retaining face overrides inside nested assemblies.
The native regression test includes a two-shell colored body split into separate
parts, nested names, a translated/rotated repeated instance, source body fill
and an explicit face-color override.

## Run

From `rm-map-tools`, using the normal OCP environment:

```sh
ocpenv/bin/python python/cad_hierarchy.py source/RMUC2027_V1.0.0.stp \
  --policy rules/hierarchy-rmuc2027.json \
  --out out/rmuc2027-hierarchy --validate-native
```

An optional source `.npz` parser cache can replace the original STEP path. No
separate per-part export bundle or mesh intermediates are needed. The output
path must be fresh. Generation stages the complete result before renaming the
directory into place; a failed check does not publish a partial package.

## Stage-one release

This is the source-preparation checkpoint in the new pipeline. It preserves
existing assembly instances but does not yet apply the in-memory exact geometry
or appearance-sharing passes. Runtime exporters still use the original STEP
and their existing rules; a future adapter must retain the identity manifest
when consuming this hierarchy.

The committed [release builder](../scripts/build_hierarchy_release.py) rebuilds
stage one, performs native geometry/assembly checks, optionally compares it with
the approved baseline, and packages a `.tar.zst` at level 22 with provenance and
SHA-256 checksums. `--archive-format zip` retains ZIP/DEFLATE level 6 when needed;
`--zstd-level` overrides the Zstandard setting for development.
It requires a clean committed source checkout. Minimal exporter dependencies are
pinned in [requirements-cad-hierarchy.txt](../python/requirements-cad-hierarchy.txt).

```sh
ocpenv/bin/python scripts/build_hierarchy_release.py source/RMUC2027_V1.0.0.stp \
  --tag rmuc2027-cad-stage1-example \
  --work out/stage1-release-work --out out/stage1-release \
  --baseline out/rmuc2027-hierarchy
```

The archive includes the four CAD/check files, an upstream ownership notice,
README and `release.json`. A standalone `release.json` records the exact tool
commit, upstream source URL/hash, producer-file hashes, dependency versions and
reproduction command. `SHA256SUMS` covers the archive and standalone provenance.
Archive contents are streamed back through SHA-256 before publication.
Zstandard archives enable frame checksums and validate complete frame EOF;
ZIP archives validate entry CRCs. Tar metadata uses fixed timestamps, ownership
and modes. Generated STEP headers record their build time, so regeneration
preserves geometry/hierarchy invariants rather than promising byte-identical
headers. Packaging does not publish; upload the verified files to a separate
CAD asset release. Use a non-`v*` tag to avoid the CLI binary release workflow.
The original `rmuc2027-cad-stage1-20261017` tagged builder uses ZIP; use
`--archive-format zip` to request that format from newer tooling. The level 3/22 storage comparison is documented
in the [layer and compression investigation](cad-optimization-passes.md#pooled-layer-references-and-zstandard).

To replace only an existing release's compression, use
[`repack_hierarchy_release.py`](../scripts/repack_hierarchy_release.py). It pins
the original ZIP SHA-256, preserves all six payload files byte for byte (including
the original `release.json`), and verifies the tar.zst through every file hash and
complete frame EOF. A separate `repack.json` records the compression settings,
original archive hash, producer hashes and size/timing measurements. Updated
`SHA256SUMS` covers the new archive, unchanged provenance and repack metadata.
This does not apply the sharing candidate or move the original source tag.

```sh
ocpenv/bin/python scripts/repack_hierarchy_release.py \
  out/stage1-release/rmuc2027-cad-stage1-20261017.zip \
  --source-zip-sha256 c7ac29aa56c045e7aca11cae9cb619bdffc93151177376f70d68005f2337796f \
  --tag rmuc2027-cad-stage1-20261017 --out out/stage1-release-zstd
```

## Remaining reuse opportunities

The [source-backed optimizer IR](cad-optimizer-ir.md) now measures and prepares
sharing below bodies, including unit analytic shapes with exact per-use scales.
It keeps the reviewed hierarchy catalog and source ownership intact; it is not
yet a standalone replacement for this STEP checkpoint or a mesh exporter.

Existing instancing already stores the fan product once for ten placements and
the energy-unit product once for twelve. Both Outposts and both Bases likewise
share their respective model definitions; work-part definitions remain shared
through the parent references. See the [source pass evidence](cad-optimization-passes.md)
for measured counts and limitations.

The next useful work is:

1. Export canonical B-reps through a cache keyed by geometry, tessellation
   settings and effective appearance, retaining original face correspondence.
   Preserve shared mesh references through GLB and consumer loading.
2. Integrate the validated exact value/style sharing candidate into the pipeline.
   `python/cad_share_values.py` now writes a separate STEP candidate, reducing
   178,874 presentation assignments to 103 while retaining every binding, and
   sharing exact unnamed geometric values. See the
   [storage investigation](cad-optimization-passes.md#exact-step-value-sharing-and-storage-investigation)
   for measured raw/ZIP savings and identity-map costs. The published stage-one
   release has not applied this rewrite.
3. Adopt the opt-in pooled layer reference layout where consumers support it.
   `CadDocument.from_step(..., intern_layers=True)` now implements this sharing.
   The source has 3,674
   layer records but only 259 distinct membership lists. Preserve names and
   membership. STEP's inline aggregate lists still need representation, so an
   in-memory saving is not automatically a smaller standalone STEP.
4. Investigate rigidly congruent parts whose local coordinate frames differ,
   especially repeated mechanism modules. The strict graph audit found only
   two additional identical body pairs (426 to 424 definitions). A broader
   matcher needs a new geometric equivalence proof and per-face appearance map.
   The follow-up frame-normalized candidate audit has a raw geometry upper
   bound below 0.1% of the original file, before replacement metadata; it is
   not an equivalence certificate.

Instancing saves definition storage, repeated tessellation and mesh-buffer
duplication. Compatible runtime batching can save draw overhead. Each placed
copy still contributes visible triangles and physical collision shapes; sharing
does not itself reduce placed triangle counts. Metadata interning, geometry
sharing and shape simplification are distinct operations.

```text
field.step                  # final analytic CAD assembly, with source provenance
hierarchy.json              # hierarchy, source identity maps, coverage and checksums
native-validation.json      # full native read-back results, when requested
NOTICE.md                   # DJI / RoboMaster ownership and usage notice
```

The source CAD and runtime field package remain unchanged. The final export is
an ignored local deliverable; do not commit DJI STEP data. Keep the original
source, exporter and policies to regenerate it, and discard temporary indexes,
per-part inspection files and local environments when no longer needed.
