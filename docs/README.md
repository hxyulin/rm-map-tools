# Documentation

Start with [Getting started](getting-started.md) to split and validate a STEP file. Use [Exporting](exporting.md) to choose a package or simulator format, then [Simplification](simplification.md) to reduce its size.

## Guides

| Guide | Contents |
| --- | --- |
| [Getting started](getting-started.md) | Install, download, split, and validate |
| [Exporting](exporting.md) | Inputs, JSON jobs, GLB, SDF, URDF, MJCF, and USD |
| [Simplification](simplification.md) | Processing order, artwork conversion, mesh reduction, and checks |
| [Architecture](architecture.md) | Pipeline and code layout |
| [Interactive viewer](viewer.md) | Inspect models and adjust joints in the documentation site |
| [Documentation site](site.md) | Run locally, edit pages, and deploy to GitHub Pages |

## Technical references

- [STEP internals](step-internals.md), [source structure](step-notes.md), and [split proof](split-proof.md).
- [Export presets](export-presets.md), [mesh simplification settings](mesh-simplification.md), and [texture atlas export](texture-atlas.md).
- [Composition and decorations](composition.md), [entity extraction](entity-extraction.md), and [detail audit](detail-optimization.md).
- [Semantic export](semantic-export.md), [reference assets](reference-assets.md), and [articulated formats](articulated-formats.md).

## Mechanisms and evidence

- [Base reconstruction](base-reconstruction.md), [interior audit](base-interior-audit.md), and [dart-target rail](base-dart-target.md).
- [Dart window](dart-window.md) and [Technology Core joints](technology-core-joints.md).
- [Geometry audit](geometry-audit.md), [performance measurements](performance.md), and the [optimization reports](simplification.md#audits-and-experiments).
- [Original articulation design](articulation-design.md), retained as design history. Use the semantic export reference for the implemented contract.

The Markdown files are the source for both GitHub browsing and the documentation site. Dated benchmark reports retain their measured scope and reproduction inputs.
