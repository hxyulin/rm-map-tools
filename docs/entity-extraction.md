# Separate scene entities

`extract_entities.py` moves explicitly selected triangles out of a static asset
into separate visual and collision GLBs. Every unit has its own local origin and
inherits all placements of the parent asset. The output manifest lists the units
as separate static assets, so rm-simulator already loads and renders them. Physics
currently combines static scenery for contact handling. These files prepare the
units for future independent bodies; they do not enable movement or define mass.

```sh
ocpenv/bin/python python/extract_entities.py INPUT_PACKAGE \
  --rules selections.json --out NEW_OUTPUT_PACKAGE
```

An export job can include an `entities` stage with `package`, `rules`, and `out`.
The output must be a new directory. The input package stays unchanged. Run before
semantic binding and before further per-asset simplification. Already simplified
inputs can be partitioned, with the parent's error metadata retained and explicitly
labelled as measurements made before partitioning.

The selection file has `schema_version: 1`, `asset`, an `evidence` list, `inputs`
with `visual.sha256` and `collision.sha256`, and `entities`. Each entity has a
unique `id`, an `origin_m` in the source GLB scene frame, and separate `visual` and
`collision` selection lists. Each selection names a unique `node`, a `primitive`
index, and half-open `triangle_ranges`. Audit both inputs independently; simplified
visual and collision triangle ordinals differ. A checksum mismatch, overlapping
selection, empty unit, or invalid range stops the export.

Extraction keeps triangle winding, all vertex attributes, materials, and rest
positions. Shared meshes are separated by occurrence, and vertex storage is
compacted. No geometry is clipped, discarded, or replaced by a collision proxy.
`entity-extraction.json` records the input checksums, selections, and evidence.
Regenerate the simulator minimap after installing the new manifest.

For the measured resource-zone extraction and the next simplification candidates,
see [the resource entity audit](../benchmarks/2026-09-11-resource-entities/README.md).
