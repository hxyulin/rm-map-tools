# Export presets and tessellation policy

See [simplification counts](simplification-results.md) for mesh, primitive, vertex, triangle, and file-size measurements across all four tessellation presets and the later simplification passes.


Use `--preset simulation` for the RoboMaster simulator. It is now the default
for `export_field_package.py` and `export_elements.py`. Each export produces
one visual GLB and one collision GLB per asset. These are export-time LODs;
there is no runtime distance-based LOD switching yet.

| Preset | Visual linear / angular | Collision linear / angular | Intended use |
|---|---|---|---|
| `simulation` | 4 mm / 0.5 rad | 6 mm / 0.65 rad | Interactive simulation, with the exceptions below |
| `preview` | 8 mm / 0.8 rad | 10 mm / 0.9 rad | Overview viewers and smaller packages |
| `vision` | 0.5 mm / 0.15 rad | 2 mm / 0.35 rad | Close cameras and optical details |
| `legacy` | 2 mm / 0.35 rad | Reuse visual triangles | Reproduce the previous tessellation settings on the current source geometry |

The simulation preset keeps floor, arena-static, fortress, centre platform and
undulating road at 2 mm / 0.35 rad for both outputs. Rune/outpost use 1 mm /
0.25 rad visuals and 2 mm / 0.35 rad collisions. These are starting settings,
not a certified bound on contact or image error for every asset. The mesher may
refine difficult faces further to preserve them.

The simulation preset also disables collision for the explicitly identified
`centre-logo-sheets` body group, the two missing M letters documented in
`rules/elements-v1.2.0.json`. Their visual triangles remain. No other sheet,
marking, thin part or material color implies a collision exclusion.

Both meshes come from the corrected source bodies and faces. No convex hulls,
voxels, bounding-box substitutions or old collision proxies are used. OCCT's
cached triangulations are cleared before meshing, so a coarser collision request
cannot silently reuse an earlier fine visual mesh. Matching settings reuse one
mesh. Source-face recovery remains enabled. If a coarser collider attempt leaves
missing faces, the exporter reuses the complete visual mesh only when both visual
tolerances are no coarser than the requested collider tolerances. The validation
report records `fallback_to_visual` and `effective_tolerance`. Unresolved visual
faces, or collider failures without a sufficiently fine fallback, fail the export.

## Commands

Print a preset without OCCT:

```sh
python3 python/export_policy.py simulation
```

Export and assemble a new candidate without replacing the installed field:

```sh
ocpenv/bin/python python/export_field_package.py out/v12 v12.npz \
  --equipment ~/dev/RM/assets/rm2026-field --out out/simulation-field \
  --graft out/v20:v20.npz:BREP_220,BREP_192 --preset simulation
ocpenv/bin/python python/export_elements.py out/v12 v12.npz \
  --rules rules/elements-v1.2.0.json --field out/simulation-field \
  --out out/simulation-elements --graft out/v20:v20.npz --preset simulation
python3 python/deploy_field.py --field out/simulation-field \
  --elements out/simulation-elements --out out/simulation-runtime
```

The field exporter copies the animation-ready rune/outpost and equipment input
files; presets do not re-tessellate copied assets. Element exports do tessellate
rune/outpost, but deployment currently retains the animation-ready versions from
the field package. Their runtime savings therefore await the separate articulation
migration. Exporting a new tolerance is not permission to discard their pivots.

Use `--lin`, `--ang`, `--collision-lin`, `--collision-ang` to override the preset.
Units are mm and radians. `--collision-mode visual` explicitly reuses the final
visual triangles; `--collision-mode separate` enables independent settings.
`legacy` defaults to visual mode, so request separate mode when overriding its
collision tolerances.

## Exact asset and part overrides

Pass `--policy rules/export-simulation.example.json` to both exporters. The JSON
schema accepts partial overrides; omitted values inherit. Unknown field names,
nonfinite/nonpositive tolerances, and angles greater than pi fail before export.

```json
{
  "schema_version": 1,
  "assets": {
    "resource-zone": {
      "visual": {"linear_deflection_mm": 4, "angular_deflection_rad": 0.5},
      "collision": {"linear_deflection_mm": 6, "angular_deflection_rad": 0.65}
    }
  },
  "parts": {
    "centre-logo-sheets": {"collision_enabled": false}
  }
}
```

Names match exactly. Assets use element names such as `base` and `resource-zone`.
Parts use source product names or explicit body-group names, not generated glTF
node names. A part override applies to all occurrences of that source part.
Precedence, from lowest to highest, is preset defaults, preset asset overrides,
preset part overrides, JSON defaults, CLI tolerances/mode, JSON asset overrides,
then JSON part overrides. `collision_enabled` is independent of collision mode.
Explicitly set it to true to restore a preset-excluded part.

The manifest's `export_policy` records the preset, requested overrides and every
resolved part setting. Per-asset `tessellation` records its part settings too.
Copied assets retain their input metadata. Inspect resolved settings to verify
that an exact-name selector matched the intended source part.

## Deployment and simulator compatibility

Newly tessellated assets declare `collision_method: "source-tessellation-v1"`.
Deployment preserves their checksummed collision files. Unmarked legacy assets
continue to get a collision copy of their visual geometry. The updated simulator
selects a separate collider only for this explicit contract, otherwise it loads
the visual GLB as before. Missing checksums, corrupt files and a declared source
collider without a file are errors.

The contract permits only source tessellation and explicit policy exclusions.
It is a producer declaration plus integrity checking, not a geometric proof.
Rule-driven scoring shapes remain separate from scenery collision meshes.

## Text, layers and articulation

Decorative lettering should remain in visuals while explicitly identified text
can be excluded from physics. `collision_enabled: false` retains an empty named
collision node as a binding anchor. It does not remove the visual mesh, rename
nodes, regroup bodies, or modify joint frames.

The parallel semantic/layer exporter owns classification, stable IDs, and pivots.
This policy does not infer text from thickness or hide the semantic `markings`
layer. A new preset changes GLB checksums; regenerate and verify semantic input
pins for that export rather than reusing rules pinned to another LOD. Once that classification is complete, a layer can provide a convenient
selection of explicit collision exclusions. It must not erase physical lettering
or covers that need contact. Converting text to decals/textures or merging
coplanar geometry is not implemented by these presets. Any later merging must
stay within material, source-provenance and moving-link boundaries.

## Evidence

The [refreshed baseline](../benchmarks/2026-09-11-simulator-baseline/README.md)
contains 9.74 million scene triangles and 8.43 million static collider triangles.
In three large source-part samples, simulation settings reduced visual triangles
by 30–35% and collision triangles by 43–49% relative to 2 mm / 0.35 rad. These are
part samples, not whole-map speedups. The underlying samples are recorded in
`benchmarks/2026-09-11-tessellation-presets/samples.json`.

Tests cover policy precedence and validation, retaining independent collider
files during deployment, coarsening after an existing fine OCCT mesh, cylindrical
chord error and caps, explicit text exclusion, and simulator rejection/fallback
for unmarked legacy colliders.

The [complete simulation candidate](../benchmarks/2026-09-11-tessellation-presets/README.md)
passed export validation and runtime loading: 24.7% fewer scene triangles and
41.5% fewer static collider triangles. It is available locally at
`out/simulation-runtime`; it has not replaced the installed field. Timing
samples did not establish a tick-speed or FPS improvement.

## Detail audit and configured pipelines

Use a [JSON export job](detail-optimization.md) to keep package paths, grafts and
stages out of a long CLI command. Policy files can also select their base preset
with `"preset": "simulation"`. The geometry audit ranks small-radius surfaces,
hole candidates and fragmented source bodies before any detail removal.
