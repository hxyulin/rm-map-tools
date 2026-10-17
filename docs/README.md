<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Documentation

Start with [Getting started](getting-started.md) to split and validate a STEP file. Use [Exporting](exporting.md) to choose a package or simulator format, then [Simplification](simplification.md) to reduce its size.

## Guides

| Guide | Contents |
| --- | --- |
| [Releases and downloads](releases.md) | Choose STEP, GLB, simulator, or viewer archives |
| [Getting started](getting-started.md) | Install, download, split, and validate |
| [RoboMaster 2027](rm2027.md) | Source compatibility and CAD, GLB, simulator, and viewer builds |
| [Terrain and secondary equipment](terrain-equipment-rmuc2027.md) | 85 source-unit pieces, 25 products and preserved source placements |
| [Remaining 2027 equipment](remaining-equipment-rmuc2027.md) | Tech Core, resource area, Dart station and Energy Unit source partitions |
| [Complete CAD partitions](cad-partitions.md) | Full Rune/Outpost STEP and GLB exports with disjoint source-shell ownership |
| [Source CAD components](cad-components.md) | Whole-body component catalogs, manual groups and isolated STEP work items |
| [Hierarchical optimization and LOD](cad-lod-optimization.md) | Pass ordering, compact storage, protected detail and per-component quality |
| [Optimizer IR](cad-optimizer-ir.md) | Shared construction recipes, exact primitive normalization and source-owned instances |
| [Exporting](exporting.md) | Inputs, JSON jobs, GLB, SDF, URDF, MJCF, and USD |
| [Simplification](simplification.md) | Processing order, artwork conversion, mesh reduction, and checks |
| [Simplification counts](simplification-results.md) | Preset mesh inventories and measured reduction passes |
| [Architecture](architecture.md) | Pipeline and code layout |
| [Interactive viewer](viewer.md) | Inspect models and adjust joints in the documentation site |
| [2027 viewer](viewer-2027.md) | Inspect the 2027 arenas, assemblies, and energy unit |
| [Documentation site](site.md) | Run locally, edit pages, and deploy to GitHub Pages |

## Technical references

- [STEP internals](step-internals.md), [source structure](step-notes.md), and [split proof](split-proof.md).
- [Export presets](export-presets.md), [mesh simplification settings](mesh-simplification.md), and [texture atlas export](texture-atlas.md).
- [Composition and decorations](composition.md), [entity extraction](entity-extraction.md), and [detail audit](detail-optimization.md).
- [Semantic export](semantic-export.md), [reference assets](reference-assets.md), and [articulated formats](articulated-formats.md).

## Mechanisms and evidence

- [Base reconstruction](base-reconstruction.md), [interior audit](base-interior-audit.md), and [dart-target rail](base-dart-target.md).
- [Dart window](dart-window.md) and [Technology Core joints](technology-core-joints.md).
- [Read-only CAD optimization passes](cad-optimization-passes.md), [Geometry audit](geometry-audit.md), [performance measurements](performance.md), and the [optimization reports](simplification.md#audits-and-experiments).
- [RMUC 2027 non-base spatial components](non-base-components-rmuc2027.md), including rune/outpost shell candidates.
- [RMUC 2027 layer qualification review](rmuc2027-layer-review.md) and [source component selections](cad-components.md).
- [RMUC 2027 source colors and complete equipment compositions](appearance-compositions-rmuc2027.md), including the secondary-fixture comparison.
- [Hierarchical source STEP export](cad-hierarchy.md), assembling the reviewed work parts into one named CAD tree.
- [Original articulation design](articulation-design.md), retained as design history. Use the semantic export reference for the implemented contract.

The Markdown files are the source for both GitHub browsing and the documentation site. Dated benchmark reports retain their measured scope and reproduction inputs.

- [Finite patch matching and primitive-fit discovery](cad-patch-fitting.md).

- [Automatic vector geometry and precision-controlled export](cad-vector-ir.md).

- [Source-bound vector component export](cad-vector-component.md).

- [RMUC 2027 native terrain cost and paint investigation](../benchmarks/2026-10-17-terrain-cost/README.md).

- [Road-profile LOD preview and visual-only terrain markings](../benchmarks/2026-10-17-road-lod/README.md).
