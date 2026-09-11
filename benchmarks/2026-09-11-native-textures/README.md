# Strip artwork, simplify backing, attach native textures

The candidate is at `out/native-texture-candidate`. The installed simulator
package was not changed. Both modified GLBs contain PNG images, UV coordinates,
materials and textured quads, and render without reading the atlas sidecars.

| Placed visual geometry | Installed | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Arena | 108,268 | 10,329 | 97,939 |
| Two bases | 352,310 | 156,332 | 195,978 |
| Complete scene | 1,172,056 | 878,139 | 293,917, or 25.08% |

Counts include all native replacement quads and instance placements. The other
visual assets and every collision file are unchanged. This measures the atlas
pipeline together with relaxed visual simplification settings. It does not
attribute all savings to deleting text or establish a rendering-time speedup.

## Order and settings

1. Extract the 243 selected arena sections and the planar base wordmark from
   source geometry into atlases. Remove their original visual primitives.
2. Simplify the stripped backing meshes. Arena uses a 4 mm metric, 12 mm sampled
   limit and 4,096 samples per direction, with unlocked borders. Remaining planar
   primitives up to 6 mm thick are preserved. The installed preset disabled this
   arena pass. Base uses the same 4 mm / 12 mm settings, replacing its previous
   0.5 mm / 2 mm settings, and starts from the archived unsimplified base visual.
3. Attach 77 arena patches and one base patch using native glTF textures. The
   two base instances share that asset. PNGs are embedded in each GLB. Materials
   use alpha masking, linear filtering and no mipmaps. JSON sidecars remain as
   provenance and bake reports, not required rendering inputs.

The arena's largest sampled backing deviation is 8.924 mm. Base reaches
11.795 mm. These sampled distances are not certified maximum errors against
CAD. Coarser backing geometry is visible in close-ups.

Arena paint has inconsistent source face winding. `normal_hint: [0,0,1]` selects
upward-facing patch normals. Patches sit at the frontmost source artwork depth
and receive a 0.5 mm normal offset. This fixes clipped paint from downward offsets
and from using the mean depth of grouped sheets. Base retains its source facing.

## Validation

- Both modified GLBs pass the Khronos glTF validator with zero errors and warnings.
- VTK's standard glTF importer rendered the embedded textures without the sidecars.
  Base close-ups and arena overviews were inspected against the installed assets.
- None of 7,004 sampled opaque base artwork texels were occluded by nearby backing
  geometry. Its maximum sampled protrusion is 0.296 mm, below the 0.5 mm offset.
- Asset hashes, semantic bindings and articulation sidecar hashes pass checks.
  All collision files are byte-identical to their installed counterparts.
- The 25 focused Python tests pass. A degenerate-component regression found by
  the glTF validator now ensures the simplifier emits unit normals even for
  retained zero-area triangles. No triangles were dropped by that fix.

Local renders: `base-before.png`, `base-after.png`, `arena-before.png` and
`arena-after.png` in the candidate directory. Per-file validator reports and
`comparison.json` are alongside them. Geometry and artwork remain local.

## Reproduce

Run from the repository root with the OCP environment. `build.py` requires a new
candidate directory and the installed package plus `out/tolerance-source`.
The grouped arena selectors come from `out/texture-atlas-grouped-preview/rules.json`.

```sh
PYTHONPATH=python ocpenv/bin/python benchmarks/2026-09-11-native-textures/build.py
PYTHONPATH=python ocpenv/bin/python benchmarks/2026-09-11-native-textures/validate.py
```

The emitted `arena-atlas-rules.json` and `base-atlas-rules.json` record the actual
selection and simplification settings. General exporter usage is documented in
[texture atlas export](../../docs/texture-atlas.md).
