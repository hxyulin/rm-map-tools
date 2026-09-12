# Simplify bound meshes for faster startup

See [simplification counts](simplification-results.md) for mesh, primitive, vertex, triangle, and file-size measurements across all four tessellation presets and the later simplification passes.

## Contents

- [Settings](#settings)
- [Geometry, boundaries and semantics](#geometry-boundaries-and-semantics)
- [Collider contracts and limits](#collider-contracts-and-limits)

The simulator's default export uses checked edge-collapse simplification with
open boundaries unlocked. Visual and collider settings are independent and live
in JSON, so the command stays short:

```sh
uv pip install --python ocpenv/bin/python -r python/requirements-simplification.txt
ocpenv/bin/python python/simplify_package.py rules/simplify-simulation.example.json
```

Paths resolve relative to the configuration file. Use a new output directory and
an unsimplified input package. The retained simulation source is at
`../assets/rm2026-simulation-source`. It combines archived unsimplified equipment
with the unchanged deployed terrain. It is separate from the semantic reference
package being developed for other consumers. The exporter verifies input hashes,
stages the result, then installs it only after processing succeeds. It refuses
to simplify an already simplified asset because repeated passes accumulate error.

## Settings

`defaults` applies to all enabled assets. `assets` overrides settings by exact
asset name. An asset can set `enabled: false`.

| Setting | Simulation preset |
| --- | ---: |
| `visual_error_mm` | 4 |
| `collision_error_mm` | 4 |
| `visual_sampled_limit_mm` | 12 |
| `collision_sampled_limit_mm` | 8 |
| `deviation_samples` | 4096 |
| `visual_lock_borders` | false |
| `collision_lock_borders` | false |

Error settings are meshoptimizer metrics. Sampled limits are a separate
point-to-triangle acceptance check. They are not interchangeable. Border settings
must be JSON booleans. If omitted, borders remain locked for backwards
compatibility. Visual and collider settings need not be equal.

`deviation_samples` is the number of triangles selected per primitive in each
direction, from 96 to 16,384. Each contributes a vertex, an edge midpoint and a
centroid. Locked borders default to 96; unlocked borders default to 1,024 and
reject explicit values below 1,024. The preset uses up to 24,576 sample locations
per changed primitive. Small meshes are sampled more completely than large ones.

`visual_preserve` and `collision_preserve` accept exact node names and primitive
indices. For example:

```json
{"visual_preserve": [{"node": "source_13267588_001_1_1", "primitive": 5}]}
```

An unknown or ambiguous node name, or absent primitive, fails the export. A
selected primitive retains its original geometry in all shared-mesh instances.
The preset preserves the identified base wordmark, dart-gate logo, rune R artwork
and resource-zone logo housing. Terrain, centre-platform lettering and outpost
footings remain unchanged. The base visual uses a tighter 0.5 mm metric and 2 mm sampled limit to keep its backing panel from covering the wordmark. Its collider keeps the default settings. Review selectors when replacing the source package.

## Geometry, boundaries and semantics

Meshoptimizer 0.2.30a0 collapses edges within each existing glTF primitive.
Exactly equal positions are welded; nearby positions are not rounded together.
Materials and primitive order remain unchanged. Components that would disappear entirely are retried independently at tighter
settings for up to twelve refinements. Irreducible components retain their original triangles. There is no blanket size filter that deletes fasteners,
small parts or faces. Normals are rebuilt as flat triangle normals.

Unlocked borders can lose subdivisions, move and collapse within the accepted
sampled-distance checks. This permits simplification of CAD face seams and small
openings that the previous locked-border pass retained. For this simulation,
openings smaller than the 17 mm projectile are allowed to disappear. The exporter
does not explicitly classify and remove every sub-17 mm hole; this is a fidelity
choice, not a guaranteed hole-diameter cutoff. A 17 mm hole diameter is not a
17 mm global surface-error budget.

The unlocked pass tries up to six error settings, halving the requested metric
at each step, and keeps the smallest accepted result. Coarser is not always
smaller: aggressive collapses can trigger whole-component restoration. Locked
mode retains its previous four attempts with a factor of four and first accepted
result. If no attempt passes, the original primitive is kept.

Node indices, hierarchy, names, transforms, joint records and semantic metadata
remain unchanged. LED, rune-target, dart-detector and guiding-light roles, plus
`markings` and `lights` layers, protect their geometry. Node protection applies
to descendants and every use of a shared mesh. Extra vertex attributes preserve
a primitive rather than dropping UVs or colours. Skins, animations and unsupported
extensions remain rejected.

Unused meshes and accessors are compacted. GLB hashes, articulation file hashes
and manifest sidecar hashes are refreshed. Historical semantic provenance remains
unchanged. `mesh-simplification.json` records input hashes, settings, per-primitive
counts, refinements, preservation reasons and sampled errors.

## Collider contracts and limits

Locked output declares `meshopt-simplification-v1`; unlocked output declares
`meshopt-boundary-simplification-v1`. Each visual/collider record names its own
method. The asset's collision method must match its collider record. The updated
simulator checks hashes, error metadata, exact welding, the matching border flag
and a sufficient sampling budget for unlocked output. Invalid declarations fail.
Old simulators do not recognize the new method and may fall back to visuals, so
use the updated app and server together.

Distance checks are sampled, not a Hausdorff proof or a certified bound against
STEP. The source tessellation already has error. They do not certify preservation
of every opening, thin wall or contact. Only explicitly protected optical geometry
is exact. Broad terrain and procedural scoring bodies remain unchanged; equipment
surfaces may be coarser. Use tighter settings for close-range CAD or vision work.

The [unlocked export benchmark](../benchmarks/2026-09-11-unlocked-mesh/README.md)
contains the deployed counts, startup measurements, source records and visual
comparisons. Earlier [locked-border results](../benchmarks/2026-09-11-mesh-simplification/README.md)
and the [boundary study](../benchmarks/2026-09-11-aggressive-mesh/README.md) explain
why increasing STEP linear tolerance alone gave smaller savings.
