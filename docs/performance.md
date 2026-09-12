# Performance and memory

[Documentation](README.md) · [Split proof](split-proof.md) · [简体中文](zh/performance.md)

The aim is to make field CAD practical on a laptop. The main measurements are elapsed time and peak process memory, with each operation named explicitly.

## Whole-file reference runs

| Software | Hardware | Elapsed | Peak RAM | Evidence |
| --- | --- | ---: | ---: | --- |
| OCCT whole-file conversion | M5 Max Mac | 32,229 s, about 8 h 57 min | ~40 GB | [Conversion log](../benchmarks/whole-file-reference/occt-conversion.json); RAM in [project notes](split-proof.md); machine attributed by project owner |
| SolidWorks 2024 | Ryzen 9 9950X3D | 15 h | ~25 GB | Project-owner report, 2026-09-11; no raw timing log |

The OCCT log refers to `RMUC2026_V2.0.0.stp`. It records 25.1 s for file read, 7,834.6 s for XCAF transfer, 21.3 s for meshing, and 24,342.2 s for GLB serialization. Its reported total is 32,229.4 s. The log does not contain machine or RAM fields; those attributions are separate evidence. The SolidWorks report does not separately identify import, rebuild, and export phases, or pin the exact source version/settings.

## rm-map-tools on M3 Pro

Apple M3 Pro, 11 cores, 18 GiB RAM. Rust timings, OCCT part reads, and source-preservation details are recorded in the [split proof](split-proof.md). These are historical measurements, not a new rerun for this page.

| Operation | V2.0.0, 1.25 GB | V1.2.0, 993 MB |
| --- | ---: | ---: |
| Index | 1.3 s | 1.1 s |
| Inspect saved index | 0.5 s | 0.7 s |
| Split all products | 8.4 s, 429 parts | 2.7 s, 1,047 parts |
| Split peak RSS | 3.6 GB | 1.9 GB |
| OCCT accumulated part-read time | 205 s | 117 s |
| OCCT part-read peak RSS | 4.5 GB | 3.2 GB |
| OCCT validation + meshing wall time | 257 s (4 min 17 s) | Not separately recorded here |
| OCCT validation + meshing peak RSS | 4.7 GB | Not separately recorded here |

The largest V2.0.0 equipment product is still a 674 MB part and dominates the CAD-kernel cost. Splitting by product does not promise that every individual part is small.

The stages run separately. Do not add their peak RAM figures together. The 4.7 GB measurement demonstrates the tested workflow on an 18 GiB machine; it is not a promise that any 4.7 GB machine can run it. Preview generation, other export presets, and concurrent tasks can use additional memory.

## What the comparison means

The split workflow avoids repeatedly transferring the complete STEP assembly into a CAD kernel. It preserves geometry entities and processes smaller files independently. That changes where the expensive work happens.

The whole-file OCCT result includes a single large GLB write. The 257 s part validation result does not. The SolidWorks figure is a reported application workflow on another machine. Presenting these times side by side explains the practical motivation; dividing them into a universal speedup factor would hide those differences. Mesh quality, source version, and output format must also be matched for an end-to-end benchmark.

## Simulator startup

A separate three-run alternating comparison on M3 Pro measured median scene-ready time falling from 15.497 s to 5.734 s after bound-mesh simplification. Referenced GLBs fell from 587,168,572 to 259,669,320 bytes. OS caches were not cleared, and scene-ready means CPU instance setup, not first displayed frame. [Report and raw records](../benchmarks/2026-09-11-mesh-simplification/README.md).
