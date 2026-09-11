# Interactive model viewer

Choose a mechanism to load its CAD model, then use the sliders to move individual entities. Drag the view to orbit and scroll to zoom. **Focus** frames the geometry controlled by a particular joint; **Fit view** shows the whole mechanism.

<ModelViewer />

| Mechanism | Movable entities |
| --- | --- |
| Base | Three protective shields and the rail-mounted dart target |
| Power Rune | Front and rear rotors |
| Outpost | Rotor and its attached hardware |
| Dart station | Sliding window and carriage |
| Technology Core | Base yaw, shoulder, elbow, two wrist axes, and tool roll |

The catalog loads models on demand, so opening this page does not download the whole field. The meshes and joint bindings come from the reference package. The Core uses the existing CAD display rig with schematic bearings; its exported reference model still contains fixed joint frames.

On GitHub, run the [documentation site](site.md) to use the viewer. The catalog needs the generated model bundle described there. Files opened through the local file controls stay in your browser and are not uploaded.

## Drag the Technology Core tool

Select Technology Core and click **Drag tool**. Drag an arrow to move along one world axis, or a plane square to move in two axes. The handle starts at the tool assembly's bounding-box center. The six-joint solver moves that point toward the target and updates the sliders. Click **Stop dragging tool** to hide the handle.

This is position-only inverse kinematics on the CAD display rig. Tool orientation can change; tool roll remains available through its slider. The ±1.2 rad joint ranges, about ±68.8°, are preview guards, not measured mechanical limits. A target outside those ranges can remain unreached, and the viewer reports the remaining distance. Reset restores the rest pose and recenters the handle. Sliders also recenter it.

The solver uses bounded iterations and a 0.5 mm position threshold. It can stop at a local solution, especially near a singular pose. There is no collision avoidance, calibrated tool-center point, or physical controller. The reference export still contains fixed joint frames; see [Technology Core joints](technology-core-joints.md).

## Open your exports

Choose a GLB file, or choose a folder containing exported URDF or SDF equipment and its meshes. If a folder contains several models, select the one you want from the model list. The viewer resolves relative mesh paths and ROS `package://` paths within the selected folder. Missing or ambiguous files produce an error.

| Input | What the viewer supports |
| --- | --- |
| GLB | Meshes, materials, orbit controls, and a timeline for embedded animation clips |
| URDF | Visual meshes, fixed/revolute/continuous/prismatic joints, limits, and joint sliders |
| SDF | The single-model equipment subset written by `export_articulated.py`, including model-relative link poses and child-relative joint frames |

The built-in catalog supplies semantic bindings with each model. For an arbitrary local GLB, export the reference package to URDF or SDF to expose joints; local file loading does not automatically interpret a separate `articulation.json`.

SDF worlds, nested models, plugins, arbitrary frame graphs, and multi-axis joints are not supported by this viewer. Unsupported SDF constructs are rejected rather than silently displayed with incorrect transforms. Use the target simulator to inspect complete SDF scenes. Collision simulation and controllers are outside the viewer's scope.

The controls use metres for sliding joints and radians for rotary joints. Continuous joints show one full turn in either direction. Reset restores all joints and animation to zero; Fit view frames the model at its current pose.
