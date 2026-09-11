# Simplification counts

The tables below separate tessellation presets from later mesh and artwork passes. Counts depend on the source revision, selected scene, and placements. A preset name alone does not identify a finished package.

## Four tessellation presets

These measurements use the same three V1.2.0 source products for every preset. They cover one product from each asset, not the complete asset or arena. Each product is written to a separate GLB with one mesh; material groups become primitives within that mesh. No edge collapse, artwork conversion, or scene placements are applied.

<!-- BEGIN PRESET TABLES -->
Totals across the three sampled products. Visual and collision files are counted separately.

| Preset | Output | Meshes | Primitives | Vertices | Triangles | GLB MB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `legacy` | visual | 3 | 20 | 3,979,519 | 1,560,441 | 114.12 |
| `legacy` | collision | 3 | 20 | 3,979,519 | 1,560,441 | 114.12 |
| `simulation` | visual | 3 | 20 | 2,596,287 | 1,038,539 | 74.70 |
| `simulation` | collision | 3 | 20 | 2,053,099 | 826,855 | 59.15 |
| `preview` | visual | 3 | 20 | 1,768,476 | 721,432 | 51.07 |
| `preview` | collision | 3 | 20 | 1,661,682 | 685,151 | 48.07 |
| `vision` | visual | 3 | 20 | 13,649,520 | 5,100,635 | 388.65 |
| `vision` | collision | 3 | 20 | 3,979,519 | 1,560,441 | 114.12 |

Triangle counts by source product:

| Asset sample | Source product | Preset | Visual triangles | Collision triangles |
| --- | --- | --- | ---: | ---: |
| resource-zone | `7000001_1_ASM` | `legacy` | 1,030,355 | 1,030,355 |
| resource-zone | `7000001_1_ASM` | `simulation` | 670,718 | 525,843 |
| resource-zone | `7000001_1_ASM` | `preview` | 456,640 | 435,286 |
| resource-zone | `7000001_1_ASM` | `vision` | 3,609,422 | 1,030,355 |
| dart-station | `0013_1_ASM` | `legacy` | 323,469 | 323,469 |
| dart-station | `0013_1_ASM` | `simulation` | 222,716 | 183,620 |
| dart-station | `0013_1_ASM` | `preview` | 160,987 | 150,887 |
| dart-station | `0013_1_ASM` | `vision` | 971,104 | 323,469 |
| base | `001_1_ASM` | `legacy` | 206,617 | 206,617 |
| base | `001_1_ASM` | `simulation` | 145,105 | 117,392 |
| base | `001_1_ASM` | `preview` | 103,805 | 98,978 |
| base | `001_1_ASM` | `vision` | 520,109 | 206,617 |
<!-- END PRESET TABLES -->

Vertices are stored `POSITION` entries summed over material primitives, so hard edges and material seams can duplicate positions. Meshes are glTF mesh definitions, not connected CAD bodies. Primitives are material batches, not measured GPU draw calls. GLB sizes use decimal MB and include the complete file.

[Raw measurements and reproduction](../benchmarks/2026-09-11-preset-inventory/README.md) include source hashes, output hashes, resolved policy settings, and face-recovery counters. The mesher can refine difficult faces beyond the requested tolerance. See [export presets](export-presets.md) for tolerance units and per-asset exceptions.

## Whole-field passes

These are retained measurements from 11 September 2026. Rows are separate benchmark snapshots; source corrections and semantic changes occurred between them. Compare the before/after pair within each report instead of treating every row as one cumulative pipeline.

| Snapshot | Visual triangles | Static collider triangles | Runtime mesh entities | Visual + collider GLB MB | Evidence |
| --- | ---: | ---: | ---: | ---: | --- |
| Corrected geometry baseline | 9,743,200 | 8,425,384 | 2,218 | Not recorded here | [Baseline](../benchmarks/2026-09-11-simulator-baseline/README.md) |
| Simulation tessellation candidate | 7,334,576 | 4,927,403 | 2,218 | Not recorded here | [Tessellation](../benchmarks/2026-09-11-tessellation-presets/README.md) |
| Input to locked-border pass | 7,527,046 | 5,968,039 | Not recorded | 587.17 | [Locked borders](../benchmarks/2026-09-11-mesh-simplification/README.md) |
| Locked-border output | 3,018,741 | 2,169,201 | Not recorded | 259.67 | [Locked borders](../benchmarks/2026-09-11-mesh-simplification/README.md) |
| Unlocked-border output | 1,183,564 | 938,536 | Not recorded | 113.89 | [Unlocked borders](../benchmarks/2026-09-11-unlocked-mesh/README.md) |

The first two visual totals come from runtime scene inventory and include procedural geometry. The later totals count placed CAD geometry. Static collider totals come from the simulator loader after its cleanup, not from adding all collision GLB triangles. Referenced GLB bytes count each asset file once, regardless of placements. Runtime mesh entities and unique glTF meshes are different measures; missing historical mesh counts are left explicit.

The matched locked-border comparison reduced placed visual triangles by 59.9% and static collider triangles by 63.7%. The unlocked comparison reduced them by another 60.8% and 56.7% relative to its recorded previous default. These passes rebuild from unsimplified inputs; they do not repeatedly simplify the previous output.

### Per-asset locked and unlocked results

Visual triangles per instance, from the [unlocked count record](../benchmarks/2026-09-11-unlocked-mesh/counts.json). Multiply by placements to reproduce the placed scene totals above.

| Asset | Placements | Locked visual triangles | Unlocked visual triangles |
| --- | ---: | ---: | ---: |
| floor | 1 | 12 | 12 |
| arena-static | 1 | 119,776 | 119,776 |
| rune | 1 | 231,258 | 73,705 |
| outpost | 2 | 99,793 | 25,349 |
| centre-platform | 1 | 33,255 | 33,255 |
| dart-station | 2 | 389,586 | 90,904 |
| resource-zone | 2 | 462,486 | 167,914 |
| outpost-footing | 2 | 20 | 20 |
| base | 2 | 316,623 | 176,155 |
| tech-core | 2 | 48,712 | 18,066 |

## Later artwork and component passes

These experiments and subsequent installations use later package snapshots. Their reports identify exactly which assets changed.

| Pass and scope | Before | After | Reduction | Evidence |
| --- | ---: | ---: | ---: | --- |
| Native texture artwork and backing, placed scene visual triangles | 1,172,056 | 878,139 | 25.08% | [Native textures](../benchmarks/2026-09-11-native-textures/README.md) |
| Artwork removal and backing, actual static collider triangles | 927,028 | 828,829 | 10.59% | [Collision artwork](../benchmarks/2026-09-11-collision-artwork/README.md) |
| Resource zone component refinement, visual triangles per instance | 160,836 | 112,591 | 30.0% | [Component refinement](../benchmarks/2026-09-11-component-refinement/README.md) |
| Base component refinement, visual triangles per instance | 78,166 | 60,434 | 22.7% | [Component refinement](../benchmarks/2026-09-11-component-refinement/README.md) |
| Geometry sharing, separately placed visual asset GLBs, decimal MB | 815.42 | 401.07 | 50.8% | [Geometry sharing](../benchmarks/2026-09-11-geometry-sharing/README.md) |

Geometry sharing leaves placed triangle counts unchanged. Texture results include replacement quads. These figures do not establish FPS or physics-step improvements. See [performance](performance.md) for measured startup times and test conditions.
