# Articulated equipment

[Documentation](README.md) · [Exporting](exporting.md) · [简体中文](zh/articulated-formats.md)

`python/export_articulated.py` exports the existing semantic equipment to SDF,
URDF, and USD. It uses the authored motion-node hierarchy to split rigid links,
rebase meshes into each link's frame, and preserve joint axes and travel limits.
It does not re-tessellate the CAD or invent a second set of joint definitions.

```sh
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/export_articulated.py \
  ../assets/rm2026-reference --out out/articulated-models

# Select equipment or formats
ocpenv/bin/python python/export_articulated.py \
  ../assets/rm2026-reference --asset base --asset dart-station \
  --formats sdf urdf --out out/shield-models
```

The destination must be new. Exports are staged and published only after all
selected writers succeed. NumPy and SciPy are required; USD also requires
`usd-core`. The reference equipment subpackage is discovered automatically.
This command exports individual equipment models. Static field geometry and
world assembly remain the responsibility of the existing scene exporter and
simulator. No new glTF animation, MJCF, or SRDF export is added.

## Output

Each equipment directory contains `model.sdf`, `model.urdf`, `model.usdc`,
`semantics.json`, and STL meshes for the XML formats. USD embeds its meshes.
`model.config` makes the SDF directory a model package. The root manifest records
file hashes. The generated ROS 2 package is named `rm_map_equipment`; copy the
output into a ROS workspace's `src/`, build with `colcon build`, and source the
workspace to resolve its `package://rm_map_equipment/...` mesh URIs.
Only one generated package with that name should be installed at a time.

| Format | Representation | Intended use |
|---|---|---|
| SDF 1.11 | Native revolute/prismatic joints; kinematic links with gravity disabled | A consumer supplies link poses or an engine-specific controller |
| URDF | Native continuous/revolute/prismatic tree, per-link visual and collision meshes | ROS description and joint-state visualization |
| USD | UsdPhysics joints and kinematic rigid bodies; arbitrary axes represented by oriented local joint frames | USD/Isaac asset import and prescribed motion |

All files retain the source asset coordinates. Some extracted equipment has
local Y as its vertical axis, so do not infer placement from a viewer's up-axis
setting. `semantics.json` carries the original asset-to-arena placement matrices;
apply a placement once when assembling the field. USD stages declare Z-up for
the arena convention, without silently rotating the asset vertices.

## What is preserved

The sidecar retains the full original visual/collision semantic bindings,
including armor size/family, LED channels, team colors, layers, rule evidence,
and demo motion descriptions. It also maps semantic joint IDs to exported link
names. Visual and collision meshes follow their respective source bindings;
independently tessellated collision meshes need not share visual node indices.
USD embeds node metadata and joint definitions as custom data as well.
Materials retain base colors; textures and other PBR properties are not converted.
Original glTF node indices in the sidecar refer to the source files, not USD or XML
nodes; use the exported mesh records and link-name map for those formats.

## Kinematics, not calibrated dynamics

Mass, inertia, motor effort, and speed limits are not available for these CAD
assemblies. No inertial properties or actuators are authored. URDF requires
numeric effort and velocity fields, so these are explicitly zero compatibility
sentinels, not measured limits. This supports joint-state visualization, but
requires real properties and control configuration before dynamic simulation or
motion planning. SDF/USD engine defaults must not be treated as measured mass.
The root link is a model anchor; the simulator chooses how to attach the model
to its world.

The reference package exports eight moving joints: two Rune rotors, one Outpost
rotor, three Base shields, one Base rail target, and one Dart window. Travel
constants and their sources remain in the original evidence. The Technology
Core's six `frames_only` axes export as fixed reference frames; their unverified
source joint definitions remain in metadata. Preview angles do not become
mechanical limits, and the preview arm rig is not promoted to a physics model.

No match controller or animation is generated. Consumers can evaluate coordinates
with `articulated_scene.link_poses(graph, coordinates)` using the sidecar graph.
It returns asset-local link poses in metres and radians and rejects unknown,
out-of-range, or nonzero frames-only coordinates. Existing preview scripts remain
responsible for sinusoidal rail motion and shield sweeps.

## Validation and specifications

Tests compare exported transforms against the original semantic GLB at nonzero
joint coordinates, including rotated parent frames and serial chains. They also
check USD's arbitrary-axis joint frames and collision separation. The five local
reference models were parsed with `check_urdf`, libsdformat 15, and OpenUSD.
The [reference validation report](articulated-validation.json) records source hashes
and a maximum STL coordinate error below 4.3e-8 m at rest and at nonzero joint
coordinates. All 79 Python tests passed. These checks cover model structure and
geometry export, not Gazebo or Isaac controller behavior. A ROS workspace build
was not run here.

The adapters follow the official [SDF kinematics specification](https://sdformat.org/tutorials/specification/spec_model_kinematics/),
[ROS URDF joint documentation](https://docs.ros.org/en/humble/Tutorials/URDF/Building-a-Movable-Robot-Model-with-URDF.html),
and [USD Physics schema](https://openusd.org/release/api/usd_physics_page_front.html).
