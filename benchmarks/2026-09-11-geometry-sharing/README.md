# Geometry sharing and distribution size

The GLB exporter now hashes local geometry and colours, stores matching meshes
once, and uses node matrices for repeated placements. Field source occurrences
and full-map element placements retain their transforms. Arena GLB composition
also keeps local geometry and transforms instead of baking every placement.
Node names remain separate, and the triangle counter still counts placed
triangles. Identical position/normal pairs share vertices; hard edges stay split.
Indices use 16 bits when possible and 32 bits for larger meshes.

## Measured results

Existing `rm2026-field-elements` assets were decoded once per asset and fed to
the previous and current writers with their manifest placements. No CAD
retessellation or triangle simplification was performed. Sizes are decimal MB.
These totals are sums of separately placed asset scenes, not a measured single
full-map file or a comparison against the current installed runtime package.

| Output | Previous writer | New writer | Reduction |
|---|---:|---:|---:|
| Placed visual assets | 815.42 MB | 401.07 MB | 50.8% |
| Placed collision assets | 815.42 MB | 401.07 MB | 50.8% |
| Ten STEP files, original versus ZIP | 941.15 MB | 199.29 MB | 78.8% |

The input package uses identical visual and collision files, hence the equal
results. Each input GLB checksum and the exact baseline Git revision are in
[results.json](results.json).

| Placed visual scene | Previous | New |
|---|---:|---:|
| base | 150.49 MB | 68.85 MB |
| outpost | 65.17 MB | 28.71 MB |
| rune | 81.45 MB | 76.04 MB |
| dart-station | 150.09 MB | 65.68 MB |
| resource-zone | 311.76 MB | 130.04 MB |

## Validation and limits

All triangle coordinates were compared in node/triangle order after applying
scene transforms. Node names, triangle counts, and per-triangle colours match.
The largest coordinate difference is 0.000477 mm, from float32 storage before
versus after placement. This is not a normals comparison or a runtime speed
measurement. The hard-edge and reflection regression checks cover normals and
winding behavior on fixtures.

All 24 generated GLBs passed the Khronos glTF validator with zero errors and
zero warnings. See [gltf-validation.json](gltf-validation.json). The Python suite
passes 106 tests, including sharing across placements, different colours,
reflections, composition round trips, hard edges, large indices and anchors.

STEP archives were extracted and SHA-256 compared with the originals. The
uncompressed STEP files are unchanged. Each inspected element references each
of its selected leaf products once; that count does not establish whether
separate products contain equivalent geometry. Detecting those equivalences,
including true mirror shapes, remains future work. ZIP saves transfer/storage
space but requires extraction before ordinary STEP import.

Candidates and archives are in `out/geometry-sharing`. The GLBs are static
placed benchmark scenes, not drop-in local-frame element files. The benchmark
reconstructs flat CAD colours and does not preserve animation, semantic extras,
or textures. It must not be used as a general GLB conversion tool. The installed
runtime package was not changed. Regular exporter runs retain their normal
metadata/semantic pipeline and will use the updated writer.

## Reproduce

From the repository root, with the OCP environment and a new output directory:

```sh
PYTHONPATH=python ocpenv/bin/python python/benchmark_geometry_sharing.py \
  /Users/hxyulin/dev/RM/assets/rm2026-field-elements \
  out/geometry-sharing-repeat \
  --baseline BASELINE_REVISION
```

Use `baseline_revision` from `results.json` for `BASELINE_REVISION`.

```sh
PYTHONPATH=python ocpenv/bin/python -m unittest discover -s python
```

## tar.zst comparison

Zstandard 1.5.7, one compression thread, levels 3, 9 and 15. STEP archives
contain the ten original files. GLB archives contain all 24 compacted static
benchmark scenes, both visual and collision, totalling 802.13 MB. Each archive
was streamed back through tar and every member checked against its input SHA-256.
Tar metadata is normalized for reproducibility. Sizes include the archive headers.

| Bundle | Level | Size | Compression | Decompression and SHA-256 check |
|---|---:|---:|---:|---:|
| STEP | 3 | 200.50 MB | 2.27 s | 0.85 s |
| STEP | 9 | 170.53 MB | 10.79 s | 0.82 s |
| STEP | 15 | 167.19 MB | 78.95 s | 0.76 s |
| GLB | 3 | 294.69 MB | 1.75 s | 0.72 s |
| GLB | 9 | 257.08 MB | 6.14 s | 0.62 s |
| GLB | 15 | 252.03 MB | 28.66 s | 0.69 s |

Level 9 is a useful default for this dataset. STEP tar.zst at level 9 is
170.53 MB, 14.4% smaller than the ten separate ZIP archives at 199.29 MB.
Level 15 saves another 3.33 MB but takes 78.95 seconds instead of 10.79 seconds.
This compares one tar bundle with separate ZIP archives; it does not isolate
codec choice from bundling effects. Timings are single desktop samples, with
the independent STEP and GLB runs overlapping, not controlled throughput claims.

Archive artifacts are under `out/geometry-sharing-step-zstd` and
`out/geometry-sharing-glb-zstd`. Detailed measurements and input checksums are
in [step-zstd.json](step-zstd.json) and [glb-zstd.json](glb-zstd.json).

```sh
ocpenv/bin/python python/benchmark_distribution_archives.py \
  /Users/hxyulin/dev/RM/assets/rm2026-field-elements out/step-zstd-repeat
ocpenv/bin/python python/benchmark_distribution_archives.py \
  out/geometry-sharing out/glb-zstd-repeat --glob '*.glb'
```
