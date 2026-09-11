# Exporting

[Documentation](README.md) · [Getting started](getting-started.md) · [Simplification](simplification.md)

Choose the output by how you plan to use it. All commands below run from the repository root with the Python environment from [Getting started](getting-started.md).

## Supported outputs

| Output | Exporter | Use and limits |
| --- | --- | --- |
| STEP `.stp` + `parts.json` | Rust `split` | Standalone source products; preserves geometry entities |
| Visual/collision `.glb` + `manifest.json` | `export_field_package.py`, `export_elements.py` | Placed field assets with colors and separate collision geometry |
| GLB metadata + `articulation.json` | `export_semantics.py` | Joints, armor, LEDs, team colors, and layers |
| Static SDF, MJCF, USD | `export_sim.py` | Field scenes; articulated inputs require an explicit rest-pose bake |
| Articulated SDF, URDF, USD | `export_articulated.py` | Individual equipment models using existing joint bindings |
| PNG texture atlases, sidecar or embedded in GLB | `texture_atlas.py` or exporter option | Rasterized artwork; see [texture atlas export](texture-atlas.md) |

URDF is an equipment export, and MJCF is a static scene export. Articulated XML models use STL mesh files; USD embeds its meshes. The articulated adapter retains base colors but does not convert textures or other PBR properties.

## Prepare the inputs

For a single STEP split, use the [quick start](../README.md#quick-start). Field generation additionally needs the Python source index:

```sh
ocpenv/bin/python python/p21index.py source/RMUC2026_V2.0.0.stp v20.npz
```

The [example field job](../rules/export-job.example.json) combines releases. Before running it, prepare:

| Input | Example location | How to obtain it |
| --- | --- | --- |
| V1.2.0 split package | `out/v12` | Download `RMUC2026_V1.2.0.stp`, then index and split as in the quick start |
| V1.2.0 Python index | `v12.npz` | Run `p21index.py` on the V1.2.0 STEP |
| V2.0.0 split and Python index | `out/v20`, `v20.npz` | Quick start plus the command above; supplies grafted roads |
| Existing equipment package | `../assets/rm2026-field` | Supply the local package referenced by the job; it is not bundled or created by the quick start |
| Ownership and tolerance rules | `rules/` | Review the supplied JSON files against your source release |

The equipment dependency means this example is not a complete field rebuild from a fresh clone alone. Source files, split packages, and prebuilt GLB equipment are different inputs.

## Configure a complete export

Use a JSON job for input paths, grafts, output directories and export stages:

```sh
ocpenv/bin/python python/export_job.py rules/export-job.example.json --dry-run
ocpenv/bin/python python/export_job.py rules/export-job.example.json
```

Paths resolve relative to the JSON file, regardless of the current directory.
The runner validates the complete job structure and shared policy before
starting. It uses the current Python interpreter, invokes scripts without a
shell and stops at the first failed stage. Output directories must be new and
must not overlap. Completed stages remain available if a later stage fails;
there is no automatic rollback or resume. Input geometry and semantic checks
still run in the individual exporters.

A stage's `type` is `field`, `elements`, `entities`, `semantics`, or `deploy`. Parameters use
snake_case names. `package` and `index` replace the positional CLI arguments.
Grafts use structured `package`, `index` and, for the field exporter, `products`
fields. The example shows a full field/elements/deploy pipeline. Add a semantic
stage with `package`, `rules` and `out` after reviewing the new export's catalog.
Semantic rules are checksum-pinned; this runner does not rewrite their pins.

The shared `policy` file controls tessellation and exact-name overrides. It can
now contain `"preset": "simulation"`, so the preset lives in configuration too.
An explicit CLI `--preset` takes precedence. See [export presets](export-presets.md)
for tolerance precedence and collision exclusions.

## Build and inspect a GLB package

Copy `rules/export-job.example.json` to `rules/export-job.local.json`, edit its input and output paths, then run:

```sh
ocpenv/bin/python python/export_job.py rules/export-job.local.json --dry-run
ocpenv/bin/python python/export_job.py rules/export-job.local.json
```

The example runs field export, element export, and runtime assembly. Its `deploy` stage writes the configured output directory. To add semantic bindings, review the new GLB catalog and checksum-pinned rules, then add a `semantics` stage. See [semantic export](semantic-export.md). Separate scene units can be created with an `entities` stage before binding; see [entity extraction](entity-extraction.md).

The default tessellation preset is `simulation`. Use [Export presets](export-presets.md) for the tolerance table, exact-name overrides, and direct exporter commands. Mesh reduction and decoration cleanup are separate operations described in [Simplification](simplification.md).

Before using a package, inspect `manifest.json`, its file hashes and collision declarations, and the exporters' validation reports. Review geometry and motion for any changed source selectors. Keep a copy of the source package and choose a new directory for each candidate.

## Export a static simulator scene

Install the optional USD and MuJoCo dependencies into the same environment:

```sh
uv pip install --python ocpenv/bin/python usd-core mujoco
ocpenv/bin/python python/export_sim.py out/configured-elements \
  --out out/sim-scenes --static-rest-pose
ocpenv/bin/python python/export_sim.py out/configured-elements \
  --out out/sim-scenes --static-rest-pose verify
```

This writes SDF, MJCF, and USD scene assets. `--static-rest-pose` permits inputs with joints by baking their source rest pose. Omit it for purely static input. Use `--no-isaac` to skip USD; otherwise USD is skipped if `usd-core` is unavailable. The export command also runs verification. Runtime-specific verification needs the corresponding libraries.

## Export jointed equipment

First prepare the pinned semantic package described in [Reference assets](reference-assets.md). With NumPy, SciPy, and `usd-core` installed:

```sh
ocpenv/bin/python python/export_articulated.py \
  ../assets/rm2026-reference --out out/articulated-models
```

Select equipment and formats with repeated `--asset` flags and `--formats sdf urdf`. The output directory must be new. The exporter discovers the nested equipment package automatically.

These models preserve joint bindings and known travel. They do not include mass, inertia, actuators, or match controllers. The Core's six frames export as fixed reference frames. See [Articulated formats](articulated-formats.md) for ROS package installation, coordinates, material support, and validation.

## Inspect the result

Open the [interactive viewer](viewer.md) to inspect a local GLB or an exported URDF/SDF equipment folder. Use orbit controls and joint sliders to inspect the geometry at different coordinates.
