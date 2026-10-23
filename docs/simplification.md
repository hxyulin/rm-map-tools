# Simplification

[Documentation](README.md) · [Exporting](exporting.md) · [简体中文](zh/simplification.md)


Reduction happens at several stages. STEP splitting preserves source geometry; tessellation approximates CAD surfaces; later mesh simplification is lossy. Not every optimization belongs in every package, and the JSON export runner does not run all the steps below automatically.

For source-first discovery without changing geometry, start with
[read-only CAD optimization passes](cad-optimization-passes.md). These inventory
existing assembly reuse and exact body-graph duplicates before any tessellation.

## Processing order

1. **Split and validate the source.** Keep the original STEP, split manifest, and source hashes. Resolve missing faces and ownership errors before reducing detail. See [Getting started](getting-started.md) and [Geometry audit](geometry-audit.md).
2. **Choose tessellation settings.** Generate visual and collision meshes independently. The default `simulation` preset has per-asset exceptions for terrain and mechanisms. See [Export presets](export-presets.md).
3. **Apply reviewed composition and extraction rules.** Remove the duplicate road wordmarks where applicable, classify decorations, and extract separate scene units. These operations depend on source-specific selections. See [Composition](composition.md) and [Entity extraction](entity-extraction.md).
4. **Bind semantics and joints.** Apply checksum-pinned node, primitive, and triangle selectors before simplification changes triangle numbering. See [Semantic export](semantic-export.md).
5. **Extract texture artwork if needed.** Select exact planar node/material pairs and remove the selected artwork triangles. Keep the patches separate while processing the backing. See [Texture atlases](texture-atlas.md).
6. **Simplify the remaining meshes.** Collapse edges within existing primitives, preserve protected geometry and connected components, and check sampled deviation independently for visuals and colliders. Use the package simplifier or the atlas pipeline's backing simplifier, according to the package being built.
7. **Attach native texture patches last.** Embed the PNGs and textured quads after backing simplification. The sidecar mode instead needs a consumer that draws its patches. Texture quads do not become colliders.
8. **Check and assemble the result.** Review geometry, joint motion, counts, sampled errors, manifests, and collision contracts. Retain texture pages and sidecars. Atlas assets are not automatically carried through every composition or deployment tool.

Do not chain both simplification paths on the same geometry. Restart from the unsimplified source when changing settings. The production package simplifier rejects already simplified assets.

## Mesh reduction

Install the optional dependencies, copy [the simulation configuration](../rules/simplify-simulation.example.json), and set its input/output paths before running:

```sh
uv pip install --python ocpenv/bin/python -r python/requirements-simplification.txt
ocpenv/bin/python python/simplify_package.py rules/simplify-simulation.example.json
```

Paths are relative to the configuration file. The output must be new. Defaults and per-asset overrides control visual and collision error metrics, sampled limits, border locking, and exact primitive preservation. [Mesh simplification](mesh-simplification.md) is the settings and implementation reference.

The simplifier welds exactly equal positions and works within material primitives. Missing connected components are retried at tighter error settings, for up to twelve refinements; irreducible components retain their original triangles. Joint hierarchy, node transforms, semantic metadata, and protected optical surfaces remain intact.

The simulation settings use unlocked borders to reduce CAD seams and small openings. This does not classify every hole or guarantee a hole-size cutoff. Sampled distances measure change against the input mesh, which already contains tessellation error. They are not a certified maximum distance from STEP.

## Artwork and collision cleanup

[Composition and decorations](composition.md) covers the two duplicate road wordmarks and reviewed wall/deck decorations. Classification keeps visual artwork and removes only its explicitly selected collision geometry, with backing repairs where configured.

[Texture atlas export](texture-atlas.md) converts selected planar artwork to raster patches. Its optional `simplify` block reduces visual backing between extraction and attachment. `collision_simplify` separately removes matching collider artwork and can simplify the remaining collider. Visual triangle ordinals must never be reused as collision selectors.

## Audits and experiments

These reports explain the development of the pipeline. They are dated results, not additional default stages.

| Work | Status and evidence |
| --- | --- |
| Coarser tessellation | Preset comparison |
| Small surfaces and relaxed angular tolerances | [Detail audit](detail-optimization.md); automatic CAD hole/fillet removal is not enabled |
| Locked and unlocked edge collapse | Initial pass, boundary study, unlocked output |
| Component preservation refinements | Component refinement, implemented in the simplifier |
| Artwork conversion and collider backing | Atlas simplification, native textures, collision artwork |
| Shared geometry and distribution compression | Geometry sharing, grouped sheet prototype, deduplication exploration |
| Game-oriented road strips and separate equipment colliders | RMUC 2027 trial; source spline boundaries shared with caps, rigid material batching, 3/6 mm collision variants |
| Source-profile collision parts | Energy and Dart; complete meridians, window-preserving panel slabs and dense local remainder guards |
| Dense material-local equipment LOD | Dart and Outpost; every triangle/corner checked per material, exact optical patches, per-member contact choices and preserved port rings |
| Compact game-detail omission and fitted housings | Equipment shells; same-rigid backing checks, explicit engraved-cap envelopes and assembled optical-retention refinement |
| Experimental visual budget palette | Ultra-low LOD trials; independently generated shared-mesh levels, matched views and explicit rejection of severe panel/topology damage; visual only |
| Selective Low visual repair | Low repair candidates; raise budgets only for qualified pieces, preserve closed shells and boundary anchors, and select correct original hard-edge normals |
| Repeated simplification against an original-source guard | Recursive trials; review GLBs only, not a production default |

Use [Performance](performance.md) for measured startup and memory results. Fewer triangles alone do not establish a frame-rate or physics speedup.
