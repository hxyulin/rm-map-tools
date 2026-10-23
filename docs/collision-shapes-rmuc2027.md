# Parameterized field collision export

Use a small, checksummed collision sidecar alongside retained GLB geometry for rm-simulator. It can represent simple pieces with centers, poses, radii and lengths while leaving complex surfaces as meshes. Export SDF for portable inspection. The current prototype writes both formats, but the simulator does not yet load them; installed assets are unchanged.

This is separate from the older assembly-workbench `collision.json` (`python/assembly_collision.py`). That file already uses named link-local mesh, convex and box parts. The field prototype uses its own explicit schema ID so an existing assembly reader cannot mistake it for a compatible package.

## Format choices

| Format | Parameterized collisions | Fit for this project |
| --- | --- | --- |
| JSON sidecar + GLB | Explicit cylinder parameters plus retained mesh and source/node provenance | Recommended rm-simulator contract: lightweight, preserves source selectors and exact fallback geometry. Requires a new runtime loader. |
| SDF | Cylinder radius/length and poses, multiple collision elements, mesh remainder | Best first portable export. Prototype adapter supplied for one unplaced static asset. |
| URDF | Cylinder/box/sphere collision geometry, multiple collision elements per link | Useful for equipment/robotics interoperability. The existing articulated exporter currently writes mesh geometry; it would need a primitive adapter. |
| MJCF | Native cylinder and capsule geoms, including endpoint-based placement | Useful for MuJoCo. The current mesh export uses convex mesh contacts, so a whole concave field remainder must not be silently exported as one collision mesh/hull. |
| USD Physics | Cylinder geometry with CollisionAPI, plus meshes | Useful for USD/Isaac workflows. More dependencies; runtime support varies. Existing USD export currently writes meshes. |
| STL / ordinary GLB geometry | Triangles | Useful fallback/preview; a cylinder-looking mesh remains a triangle mesh in the current field loader. |

Primary references: [SDF 1.11 geometry](https://sdformat.org/spec/1.11/geometry/), [MuJoCo geom XML](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-geom), [USD Physics cylinder descriptors](https://openusd.org/release/api/usd_physics_page_front.html), and [urdfdom geometry parser](https://github.com/ros/urdfdom/blob/master/urdf_parser/src/link.cpp). The recommendation to use JSON internally and SDF for interchange is a project design choice, not a requirement from those standards.

## Concrete prototype exports

`python/collision_shape_export.py` writes:

- `collision-shapes.json`: native cylinders with radius, full length and pose, source GLB hash, node index/name/ancestry, component ownership, units and quaternion convention.
- `remainder.glb`: original geometry with only explicitly replaced mesh-node occurrences removed. Other arrays, materials and transforms remain exact. The original source mesh and native primitive must not both collide.
- `model.sdf` and `remainder.stl`: the equivalent single-asset static rest-pose model for interchange inspection. STL is flattened only for this adapter; the JSON/GLB path retains node ownership. These files do not describe source mechanical joints or field placements.

The prototype JSON schema is `rm-map-tools.collision-shapes.prototype-1`. Coordinates are in the source GLB active scene, metres; shape poses use quaternion **xyzw**, cylinders run along local **+Z**, and `length_m` is the full length. The exporter transforms mesh-local reviewed parameters through the selected node's world transform exactly once. Proper rigid transforms and uniform scales are supported; nonuniform scale, shear and reflection fail rather than becoming an incorrect circular cylinder. Axis vectors must be finite unit vectors. Native cylinder primitives are solid; open/hollow profiles remain meshes unless filling the void is an explicit selected approximation.

This is a hybrid asset recipe, not a full field package. Runtime motion channels, floor offset, manifest placements, collision filters and contact materials remain the consumer's responsibility. Cylinder parts retain their source part ownership; do not combine independently moving owners. The whole assembly-workbench collision policy must not be copied into field dynamics.

The initial single-cylinder selection is `rules/collision-shapes-tech-core-trial.json`. The better-shaped three-cylinder trial is `rules/collision-shapes-tech-core-compound-trial.json`: a main barrel, perpendicular branch and short end collar replace installed Core collision node 22. Each rule pins the exact installed GLB hash and node name. `review_status` remains prototype/not contact approved.

```sh
ocpenv/bin/python python/collision_shape_export.py \
  out/rmuc2027-installed-reference-review/reference/collision/tech-core.glb \
  --selection rules/collision-shapes-tech-core-compound-trial.json \
  --out out/rmuc2027-core-native-shapes/compound
```

For one Core unit, this exports **65,301 retained mesh triangles + three native cylinder descriptions**, replacing a 3,187-triangle joint. The native cylinders have no exported surface triangles. The diagnostic GLB preview tessellates them at 24 segments (288 triangles total); it is not the physics representation and its overlapping internal surfaces must not be installed as a mesh replacement.

The three-cylinder outline follows the barrel/branch structure more closely than one enclosing cylinder in the matched views. It intentionally fills the hollow housing and omits local grooves/rims. Of 22,309 source vertices/centroids/edge-midpoint samples, 3,754 are more than 1 mm outside the solid union; maximum is **2.514 mm**. This forward sampling check quantifies omitted source protrusions, not clearance safety, a continuous bound or reverse silhouette equivalence. It remains a collision prototype requiring assembled contact review; it is not adopted by exporting it.

## Simulator integration required

Current local sources:

1. `rm-sim-assets/src/collision_mesh.rs` loads GLB surfaces into `CollisionMesh`; `arena.rs` stores ground, fixtures and equipment as meshes. Add an explicit hybrid asset path that retains ownership and omits replaced source nodes. Keep ground/ramp support surfaces on the established mesh path initially.
2. `rm-sim-engine/src/model/body.rs::ShapeDescription` has ball, cuboid, mesh, convex hull and compound variants, but no cylinder. Add a validated cylinder description and cook it in `rm-sim-physics/src/cooking/body.rs`. Rapier's native cylinder axis/half-height convention must be adapted explicitly from the export's +Z/full length; the engine pose convention is wxyz, whereas the export is xyzw.
3. `rm-sim-physics/src/cooking/body.rs` rejects triangle-surface children inside compounds. A hybrid retained mesh and native primitive compound need separate collider shapes on the correct rigid owner, or an intentional cooking-contract extension. Primitive children can be grouped by owner; do not create one rigid body per CAD screw. Existing compound descriptions have an eight-level/256-expanded-node limit.
4. `rm-sim-physics/src/geometry.rs::StaticGeometrySnapshot::into_triangles` explicitly handles mesh/ball/cuboid/hull and skips other types. Extend this and audit its sensor/navigation/projectile consumers so native cylinders do not disappear from downstream queries. Keep exact native shapes for direct physics queries and generate a diagnostic/derived surface only where a consumer requires triangles.
5. Apply the same checked asset placement and CAD-to-FLU/floor conversion to native centers/axes as to the mesh. Preserve filter policies, moving selectors and detectors. Test contacts/rays/sweeps and relevant poses, then benchmark the actual workload. Fewer triangles alone does not establish faster ticks; changing the number/grouping of colliders also matters.

No simulator code was edited and no Rust compilation was needed for this investigation.

## Verification

Seven new exporter tests cover rotated/scaled primitive poses, axis conventions, invalid/hollow dimensions, unsupported transforms, exact replacement of one shared mesh instance, multiple cylinders replacing one node only once, hash/name mismatch, and XML dimension/pose round trips. Three existing assembly-collision tests also pass. Real bundles are reopened and counted; retained STL world geometry matches the GLB, replacement node 22 has no remaining mesh, and all installed GLB/manifests/bindings remain hash-exact.

SDF has been checked structurally and numerically, not loaded by Gazebo/libsdformat: those bindings are not installed in the current Python environment. MuJoCo and USD bindings are also absent; their adapters were researched, not implemented or runtime-tested here. Export does not prove simulation or sensor equivalence.

```sh
ocpenv/bin/python -m unittest discover -s python -p test_collision_shape_export.py
ocpenv/bin/python -m unittest discover -s python -p test_assembly_collision.py
ocpenv/bin/python benchmarks/2026-10-23-native-collision-format/verify_bundle.py
```

Reproduction of the fitted three-cylinder selection and matched collision renders is recorded in `benchmarks/2026-10-23-native-collision-format/README.md`.
