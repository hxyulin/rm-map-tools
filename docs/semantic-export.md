# Semantic equipment export

`python/export_semantics.py` annotates existing field-package GLBs without
re-tessellation. It preserves original vertex buffers, triangle membership, materials,
external placements and rest-pose transforms. Run it with the OCP environment's
Python, or another Python with NumPy. It does not import OCP.

```sh
ocpenv/bin/python python/export_semantics.py ../assets/rm2026-field --catalog /tmp/field-catalog.json
ocpenv/bin/python python/export_semantics.py ../assets/rm2026-field \
  --rules rules/semantics-legacy-field.json --out out/semantic-field
```

The output directory must be new and outside the source package. Export stages
into a temporary directory and installs the result only after validation.
`articulation.json` contains joint descriptions, node/surface bindings, unknown
classifications, pending work and hashes of the annotated files. The manifest
hashes the sidecar. Rules pin each input GLB hash to prevent applying a part
mapping to a different release or tessellation. Regenerate the catalog and
review selectors before updating a hash.

## Authoring rules

A rules file has `schema_version: 1`, optional `source_sha256`, and `assets`
keyed by manifest asset name. Each asset has an `id`, `input_sha256` for visual
and collision GLBs, and these optional lists:

- `nodes`: exact `select: {name: ...}`, optional zero-based `occurrence` for
  duplicate names, optional new `name`, `metadata`, and `evidence`.
- `surfaces`: `node_id`, zero-based `primitive`, `metadata`, and `evidence`.
  Bind the owning node first. Shared mesh JSON is copied before annotating a
  surface, preserving independent instance classifications and common buffers.
- `joints`: stable `id`, `type`, semantic `parent`, semantic `children`,
  `origin_m`, optional `rotation_xyzw`, normalized `axis`, optional `limits`
  and required `evidence`. Children must be direct children of the parent.
- `pending`: descriptions of parts or mechanisms requiring source review.

Joint types are `continuous`, `revolute`, and `prismatic`. Origins are in the
parent's local frame; axes are in the joint frame. Limits are radians or metres,
respectively. Zero is the original CAD coordinate, so finite limits must include
zero. The exporter inserts a fixed origin node and an identity motion node,
then rebases children without changing their rest-world transforms. The Python
`apply_pose` function evaluates coordinates on a copy and enforces known limits.
Unknown travel limits are omitted, not encoded as zero.

Each metadata record has a stable `id` and a nonempty `roles` list. Supported
roles include armor modules/housings, LEDs, rune targets, dart detectors, guiding
lights, shields, rotors, arms, gates, platforms, decoration and unclassified
geometry. `armor.family` and `armor.size_class` are separate. Size classes are
`small`, `large`, `custom`, `unknown`; rune `supported_modes` are `small`, `big`.

`color.mode` is `source_material`, `fixed`, or `team`. Fixed colors require
`fixed_srgb`; team colors require an `owner_ref` resolved by the consumer.
An LED record requires `function` and `channel`, plus the `led_surface` role.
`module_id` and `target_frame` references must resolve to an authored ID.
See [the design](articulation-design.md) for distinctions between housing,
optical dimensions, scoring geometry and runtime match state.

Unmatched mesh nodes receive `unclassified` metadata with their input hash,
node name and index. These generated IDs identify that specific source export;
they are not cross-release semantic identities. The exporter does not infer
armor, LEDs, or moving membership from color, thickness or bounding boxes.

## Layers

Layers are visibility categories independent of mechanical parentage and semantic
roles. A light still follows its armor's joint when its visual layer is hidden.
The sidecar publishes these layer definitions:

| Layer | Default visibility | Intended contents |
|---|---|---|
| `geometry` | Visible | Physical parts, housings, structures and shields. Default when no layer is specified. |
| `markings` | Visible | Text, logos, paint sheets and decals. Enables optional clean visual views. |
| `lights` | Visible | Individually controlled luminous surfaces. Brightness/state comes from runtime channels. |
| `collision` | Hidden | Optional authored collision helpers shown during collision inspection. |
| `debug` | Hidden | Authored joint-axis markers, target-frame markers and diagnostic geometry. |

Layer defaults describe consumer behavior; the exporter does not change glTF
visibility or materials. Standard glTF viewers show the scene as authored unless
an application interprets this metadata. Consumers should apply surface layers
at primitive granularity, not hide an entire armor assembly for one LED.

Assigning `layer: markings` does **not** remove collision. An explicit
`collision: false` on verified `decoration` is the separate opt-in filter.
It removes the node's mesh or selected primitive from the collision scene while
retaining it in the visual scene. The node transform and any children remain.
Only the directly tagged geometry is excluded; the role does not propagate to
all descendants. The sidecar records exclusions and revised primitive indices.
Buffers may retain unused bytes; scene-reachable collision triangles are removed.

No shipped mapping removes text/logos or assigns them to a layer yet. This is
infrastructure for later classification. Thin physical parts remain untouched.

## Current limits and consumer migration

The exporter requires rigid triangle meshes and rejects existing skins or
animations. It does not infer missing joint membership or semantic faces, or generate
engine-specific shaders and calibrated emission. Explicit geometry partitions
can split a primitive by checksum-pinned triangle ordinals.
Joint grouping can wrap existing direct children; nested multi-joint authoring
must follow the input hierarchy. Surface bindings are per primitive. Use explicit geometry partitions to
separate mixed geometry before assigning its surface roles.

The full-map GLB remains an explicitly labeled static source snapshot. Use
component assets to obtain articulation and collision filtering. Existing
`validation.json` remains the source export's geometric audit; the sidecar is
this pass's binding/exclusion audit.

Simulator scene export requires `--static-rest-pose` for semantic assets. This
explicitly bakes their original CAD pose and uses their filtered collision GLBs.
Dynamic SDF/MJCF/USD joints and rm-simulator sidecar loading are separate consumer
work. Do not replace the deployed package until its consumer can interpret the
new joint motion nodes. Legacy visual node names alone no longer define where
the consumer must write a joint transform.

## Shipped mappings and verification

`rules/semantics-legacy-field.json` binds the existing extracted outpost rotor
and both rune face pivots, preserving their original mesh names for inspection.
It classifies the outpost armor modules as small and records Small/Big Rune
mode support separately. It does not label mixed armor primitives as LEDs.
`rules/semantics-legacy-equipment.json` records the base as an assembly and
reports its unclassified parts. Export it against the `equipment` subpackage:

```sh
ocpenv/bin/python python/export_semantics.py ../assets/rm2026-field/equipment \
  --rules rules/semantics-legacy-equipment.json --out out/semantic-equipment
```

The initial local export was checked against the pinned inputs. Visual and
collision buffers were byte-identical; every triangle and world-space vertex
at rest matched exactly. Each of the three rotary joints moved actual mesh
vertices under a quarter-turn. No text or logo geometry was excluded.

| Asset | Visual triangles | Exported joints | Unclassified mesh nodes |
|---|---:|---:|---:|
| Outpost | 433,511 | 1 | 0 |
| Rune | 983,603 | 2 | 0 |
| Dart station | 891,322 | 0 | 191 |
| Base | 894,899 | 0 | 67 |

Zero unclassified mesh nodes means the coarse assemblies are identified, not
that every primitive has armor/LED/optical metadata. Pending surface work is
listed in the sidecar. The updated profiles include base-shield and dart-gate travel. They do not classify arbitrary text
or fabricate LED bindings.

## Explicit geometry partitions

`geometry_groups` operates before node metadata and joint creation. Each group
has an input-node `select`, a destination-node `parent`, a unique `name`,
`metadata`, required `evidence`, and `parts`. Each part selects a `primitive`
and optionally half-open `triangle_ranges`, such as `[[10, 20], [30, 40]]`.
Omitting ranges selects the whole primitive. Ranges refer to the original input
GLB, whose checksum the rule already pins. Groups must not overlap.

The exporter creates a new node at the source geometry's original world pose,
reparents it, and removes exactly those triangles from its former mesh. It
retains all vertex attributes and materials, appending index buffers for partial
selections. The new node records original node/primitive/range provenance. No
triangle is deleted from the visual or collision scene by this operation.
Surface selectors are evaluated after partitioning, so author their primitive
indices against the partitioned mesh when combining the two features.

The reference mappings use this for stationary rune logo disks/R artwork and
shaft-end cylinders, eight outpost carrier fasteners previously left static,
and the dart gate/carriage separated from its two stationary guide rails.

The base shields move 170 mm outward and 45 mm down, following the arrangement in Figures 4-11/4-12. The dart window follows its 15-degree CAD guides and closes at the 205 mm platform height from Figure 4-16, giving approximately 1.16448 m of travel. See [Base reconstruction](base-reconstruction.md) and [Dart window](dart-window.md) for the geometry and checks.

### Authored serial frames

`frames` adds empty nodes before joints are inserted. Declare parents before
children. Each frame requires `parent`, `metadata` with a unique semantic ID,
and `evidence`. Optional `name`, `translation_m` and `rotation_xyzw` describe
its rest transform relative to its parent; the defaults are identity.

These frames can represent a serial joint chain before merged CAD geometry has
a verified rigid-body partition. They do not reparent source meshes or change
collision membership. Such joints must be labelled `geometry_binding:
"frames_only"`; consumers must not assume the surrounding CAD moves with them.
The Technology Core reference demonstrates this case.

A joint's optional `preview_range: [lower, upper]` sets diagnostic sweep
coordinates independently of its mechanical `limits`. If limits exist, the
preview must lie within them. Omitting limits on a revolute joint means the
stops are unknown, not that the joint is continuous. Frame-only references use
this to display small inspection sweeps without inventing mechanical limits.

### Reconstructed geometry and reused parts

`geometry_additions` appends geometry after source partitions and before semantic
annotation. Every addition requires a unique `name`, an input-node `parent`
selector, `metadata` on the `reconstruction` layer, and `evidence`. The exporter
adds `geometry_origin: reconstruction` and detailed provenance automatically.
Original source nodes and triangles remain intact.

Two addition types are supported:

- `tapered_prism`: a closed solid described by `profile.sides`, `radius_m`
  at its lower and upper ends, `z_range_m`, `center_xy_m`, and optional
  `vertex_phase_rad`, plus a glTF `material`.
- `copy_mesh`: a rigid, untextured donor mesh selected by `source.file`,
  `source.sha256` and `source.select`. Repeated donors share their appended
  mesh buffers. The optional column-major `matrix` maps donor mesh-local
  coordinates into the target parent's frame; donor ancestors are not copied.
  No scaling is allowed. Optional `surfaces` use primitive indices to attach
  armor/LED metadata to the new instance.

Both types accept a rigid `matrix`. Donor paths must stay within the explicit
`--geometry-source-root`, which defaults to the input package. The reference
builder uses the original field package as its read-only donor root.

The reconstruction layer is visible by default and can be hidden as a group.
It is intended for approximate housings, missing interiors and deliberately
reused parts whose placement is inferred. It never implies manufacturer CAD
accuracy. Layer membership alone does not remove collision; reconstructed
collision must carry the same approximation provenance as its visual mesh.
