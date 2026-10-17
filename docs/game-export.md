<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Repaired Low simulator export

`python/export_repaired_game.py` packages the user-reviewed
[repaired Low visuals](../benchmarks/2026-10-18-low-repair/README.md) for
`rm-simulator`. CAD geometry/appearance belong to DJI / RoboMaster; the package
includes `CAD-NOTICE.md`. Generated exports and archives remain outside Git.

```sh
ocpenv/bin/python python/export_repaired_game.py \
  --out ../rm-simulator/local-assets/field-2027-low
```

The destination must not exist. Export stages atomically, requires the pinned
RMUC 2027 source identity and approved visual hash, verifies each collision
input, and checks written triangle positions/winding and complete placed counts.
Source files stay unchanged. Pruning preserves used material values, original
vertex attributes, embedded artwork and shared mesh references. Canonical
equipment instances must share mesh references and relative transforms before
the exporter emits multiple manifest placements of one file.

The inspection composition's Y-up/rebasing root is removed exactly once. Files
and placements retain original numeric CAD Z-up metres, with floor reference
`-1.640343675041 m`; the simulator handles its own CAD-to-FLU conversion.

| Partition | Placements | Visual triangles per copy | Collision triangles per copy |
| --- | ---: | ---: | ---: |
| Floor | 1 | 849 | 5,898 |
| Arena/static scenery | 1 | 70,436 | 181,763 |
| Rune | 1 | 27,001 | 117,442 |
| Outpost | 2 | 15,615 | 34,903 |
| Base | 2 | 18,635 | 16,857 |
| Tech Core | 2 | 14,342 | 68,488 |

Placed totals: **195,470 visual / 545,599 collision triangles**. Collision comes
from the previous equipment-shell ledger: dedicated collision candidates where
available, preceding approved visuals otherwise, zero for whole visual-only
marking definitions. Unbounded Low triangles never become collision geometry.
`reviewed-cad-proxy-v1` declares that independent approximation contract without
inventing exact-tessellation or meshopt error metadata. `runtime-build.json`
records all contributing hashes, coverage, local bounds and measured counts.

This is an explicit **rest-pose** export. The new source hierarchy does not
carry the former runtime body/detector bindings, and the exporter does not
fabricate them. Assets load for exploration with a combined-season simulator
build; native combat/motion binding remains separate work. The 2026 default
field and its release inventory are unchanged.

From the simulator checkout:

```sh
nix develop -c cargo run --locked -p rm-simulator-server \
  --features season-2027 --example inspect_assets -- local-assets/field-2027-low
nix develop -c cargo run --locked -p rm-simulator-app --features season-2027 -- \
  --cad-assets local-assets/field-2027-low --fly --start-paused
```

Actual native inspection: **187,661 ground**, **187,296 fixture** (including
48 simulator perimeter triangles), and **170,690 equipment** triangles.
Ten loader tests and eight layout tests pass. Python: **413 tests, 412 pass,
one optional USD test skips**, including five new export tests for shared
placements, source-frame extraction, artwork pruning, collision exclusions/hash
checks and overwrite refusal.

## Portable archive

The local export also has `field-2027-low.tar.zst`, a checksum sidecar and an
archive report beside the directory. Level 22 compression uses the existing
`cad_archive.create_archive` helper with prefix `field-2027-low`. It normalizes
tar metadata and verifies every member by SHA-256 on read-back. The result is
**9,730,802 bytes** from **38,099,507 source bytes** (3.92:1).

```python
from pathlib import Path
from cad_archive import create_archive

create_archive(
    Path('../rm-simulator/local-assets/field-2027-low'),
    Path('../rm-simulator/local-assets/field-2027-low.tar.zst'),
    level=22, prefix='field-2027-low',
)
```

Run the snippet with the repository's Python environment and `python/` on
`PYTHONPATH`. Archive creation refuses existing files. Extraction recreates the
field directory; this is a local export, not a published GitHub release or a
replacement of the simulator's tracked LFS package.
