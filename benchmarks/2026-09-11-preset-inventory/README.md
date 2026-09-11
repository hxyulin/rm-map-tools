# Four-preset source-product inventory

Measured on 11 September 2026 with the current tessellator and GLB writer. The
[documentation tables](../../docs/simplification-results.md) are generated from
[samples.json](samples.json). [Provenance](provenance.json) records the source
STEP hash, implementation hashes, base revision, and local Python/OCP versions.

Each preset processes the same three complete source products from V1.2.0:
`7000001_1_ASM`, `0013_1_ASM`, and `001_1_ASM`. These are samples from resource zone,
dart station, and base. They are not the complete corresponding assets. Source
product geometry can contain bodies from multiple scene occurrences; there is
no arena placement or ownership extraction in this benchmark.

Each output contains one mesh, with a primitive for each used material group.
Counts are read back from the generated GLB JSON. Vertex totals sum stored
POSITION accessor counts per primitive; triangles sum index counts divided by
three. File bytes include headers and buffers. The retained records also include
resolved settings, per-file SHA-256, split-source SHA-256, and recovery counters.
Visual and collision files are written separately, including for `legacy`.

All twelve preset/product pairs completed. The nine legacy/simulation/preview
pairs reproduce the triangle counts in the earlier
[tessellation samples](../2026-09-11-tessellation-presets/samples.json) exactly.
`vision` adds the previously unmeasured fourth preset. There are no unresolved
faces in the retained recovery records. This inventory does not measure rendering
speed, collider loading, or geometric deviation against STEP.

## Reproduce

Run from the repository root with the OCP environment. Use unused output paths:

```sh
ocpenv/bin/python python/p21index.py source/RMUC2026_V1.2.0.step out/docs-presets-v12.npz
ocpenv/bin/python python/p21split.py out/docs-presets-v12.npz out/docs-presets-parts \
  --products 7000001_1_ASM,0013_1_ASM,001_1_ASM
ocpenv/bin/python benchmarks/2026-09-11-preset-inventory/measure.py \
  out/docs-presets-parts out/docs-presets-inventory
```

CAD and GLBs stay under ignored `out/`. To adopt a new measurement, review its
input/settings hashes and recovery results, copy its `samples.json` into this
benchmark directory, and refresh `provenance.json` for the run. Then regenerate:

```sh
python3 scripts/update_simplification_counts.py
npm run docs:check
```

The documentation check rejects stale generated preset tables. Timing fields in
the raw record include tessellation and GLB serialization, with no controlled
cache or background-load conditions; they are not used for speed comparisons.
