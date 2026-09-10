# Field articulation and semantic export names

Review date: 2026-09-11. Status: initial export infrastructure implemented;
source-face classification and consumer migration remain in progress. See
[semantic export usage and limits](semantic-export.md). Reviewed the current Python exporters, sibling `rm-simulator`, deployed
`../assets/rm2026-field` GLBs, and the supplied RMUC 2026 University Championship
Rule Manual V2.1.0, dated 2026-07-17. Page numbers below are printed pages.

## Recommendation

Make rm-map-tools own geometry grouping, joint frames, part names, target frames,
and authored appearance assets. Keep match state, motion timing, scoring, and
randomness in the simulator. Generate a hierarchical GLB and `articulation.json`
from one versioned definition. Put stable IDs and roles in glTF node `extras`;
the sidecar supplies joint semantics and references the exported node indices.
Do not maintain two independent sets of pivot coordinates.

Core glTF node transforms can represent rigid articulation. Skin joints are
for skeletal deformation and are unnecessary here. Application-specific joint
data can live in `extras`, but ordinary glTF viewers will not interpret it as
physics. References: [glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html).

## What exists today

| Path or asset | Finding | Consequence |
|---|---|---|
| `python/export_field_package.py`, `GlbWriter.write` | One root with mesh children; equipment is copied from an existing extraction. | This does not author mechanical groups. |
| `python/export_elements.py` | Element boundaries and exact placements are preserved, with source mesh nodes in a flat asset. | Useful geometric partition, not yet a motion hierarchy. |
| `python/export_elements.py`, `read_glb_nodes` | Reads mesh accessors without traversing scene transforms. | Must support accumulated transforms before hierarchical assets pass through this reader. |
| `python/export_sim.py`, `Asset` | Groups visuals across the whole asset by color; emits static simulator scenery. | Would erase moving-link boundaries even after the GLB gains joints. |
| `python/deploy_field.py` | Takes rune/outpost from the legacy field package and other elements from the new export. | The deployed package currently mixes two equipment representations. |
| Deployed rune | Root, two translated face pivots, five blades and a hub per face, plus static geometry. | Reasonable coarse motion split; optical surfaces and center caps need explicit roles. |
| Deployed outpost | Root, translated rotor, three armor children and carrier, plus static geometry. | Reasonable coarse motion split. Export its axis and target frames explicitly. |
| Deployed base / dart station | Flat trees with 68 / 192 total nodes respectively. | Need moving-part identification before articulation. |

The simulator duplicates rune face pivots in
`crates/rm-simulator-server/src/layout.rs::RUNE_FACE_PIVOTS_M`. Its renderer
finds nodes by names such as `face_0` and `rotor`, hides imported armor meshes,
and recognizes rune center-cap primitives by a geometric envelope before
counter-rotating them. These are asset facts that belong in the export.

The new element origins are footprint-centered, Z-up local frames. The older
equipment uses a different frame convention. Do not copy legacy numeric pivots
onto newly exported elements without transforming and validating them.

The separate outpost footing is intentional: the element rules record a
3.607-degree mismatch between one body and its footing. Keep their exact
placements. An assembly wrapper may group them for selection, but must not
force both into one inferred rigid placement.

## Mechanisms to model

| Mechanism | Proposed grouping | Evidence and remaining work |
|---|---|---|
| Outpost middle armor | Continuous revolute rotor carrying three armor modules and carrier; tower and upper dart target remain fixed. | Sections 4.3.2.3 and 5.5.1, Figure 4-34, p. 105. Fit the pivot/axis from CAD and retain the authored initial orientation. |
| Power Rune | Two face rotors, each with five arms and target frames, on a common axis; separate face appearances and center-logo surfaces. | Sections 4.3.2.2 and 5.5.2, Figures 4-31 to 4-33, pp. 57-58 and 105-106. Represent shared-axis/alignment information explicitly; do not infer independent physical motors from two rendered face nodes. |
| Base dart target | One prismatic carriage containing detection module and guiding light. | Section 5.6.5, pp. 124-125: motion parallel to field width, limits -0.280 to +0.280 m from the initial position; relative module/light locations remain fixed. |
| Base protective armor | Separate shield groups with closed/expanded configurations. | Section 4.2.2, Figures 4-11 and 4-12, pp. 40-41. The drawings establish endpoint configurations, not enough to assert one slider for the whole shield. Verify guides/linkages in CAD before choosing prismatic, revolute, or coupled joints. |
| Dart station gate | Prismatic gate relative to the enclosure, subject to CAD confirmation of guide direction. | Section 4.2.3, Figure 4-14, p. 43; section 5.6.5, p. 124 specifies approximately seven seconds to open. Fit guide axis and stroke; do not assume world vertical or derive stroke from opening duration. |
| Dart gliding platform | Separate prismatic platform relative to enclosure. | Figures 4-15 and 4-16, p. 44. The 1000 mm platform dimension is not automatically the joint stroke. This is a setup mechanism, not necessarily a match-driven actuator. |

The outpost's rule behavior is more detailed than the sibling digest: it reaches
0.8*pi rad/s within five seconds, stops under several conditions including the
three-minute mark, and when alive returns to its initial position within ten
seconds. Store the initial geometry in the package; keep those policies in the
world/referee code. This review does not change simulator rules.

## Proposed hierarchy and naming

```text
outpost
  static
    tower
    dart_target
  rotor_joint
    rotor
      carrier
      armor_0
      armor_1
      armor_2

rune
  static
  face_0_joint
    face_0
      arm_0 ... arm_4
        housing / light_surface / target_frame
  face_1_joint
    face_1
      arm_0 ... arm_4
        housing / light_surface / target_frame
  center_logo_0 / center_logo_1

base
  static
  dart_target_slide
    carriage
      detection_module / guiding_light / target_frame
  shield groups, pending CAD identification

dart_station
  static
  gate_slide
    gate
  platform_slide
    platform
```

These are semantic groups, not a claim that every named group is one STEP
product. Preserve each source mesh below its assigned group. Fixed center logos
are the proposed representation of the simulator's existing upright-logo
behavior; verify the source geometry before moving those primitives out of hubs.

Use stable machine IDs such as `outpost.rotor.armor.0`, readable node names such
as `outpost/rotor/armor_0`, and separate optional Chinese/English display labels.
Number repeated arms/armor by a documented angular order in the asset's rest
frame, starting at a specified reference direction, not by tessellation order.
Team ownership belongs to an instance or face assignment, not a reusable part name.

Keep source checksum, release, product ID/name, occurrence path, and body or
face identifiers in provenance. V1.2.0 has opaque names after its IGES round
trip; use the named V2.0.0 occurrences as evidence, not as proof of identical
geometry. Unknown parts should have a name such as `unclassified/source_1234`.
Renaming during export must not rewrite source STEP identity or merge same-named
occurrences. Keep explicit aliases for legacy simulator names during migration.

## Joint contract

Each definition needs:

- Stable joint ID, type, parent link ID and child link ID.
- Joint origin and rest orientation relative to the parent; normalized axis in
  that joint frame. Units are metres and radians, quaternion order is XYZW.
- Rest coordinate, limits where known, named configurations, and optional
  coupling references. Unknown limits stay unknown, never silently zero.
- Source evidence for geometry fits and rule-derived values, with verification
  status. Do not invent masses, inertias, damping or motor gains from the CAD.
- Visual and collision membership plus target frames and optical-surface IDs.
- Exported node bindings, asset checksum, schema version and coordinate convention.

Use a fixed origin node followed by a motion node. At coordinate zero the
original CAD pose must be reproduced exactly. Rotation or translation happens
in the declared joint frame; child geometry is rebased with the inverse bind
transform. The placement remains outside the equipment hierarchy. Apply the
Z-up to glTF Y-up conversion once at a documented boundary, and keep sidecar
coordinates consistent with their named frame.

Publish `articulation.json` beside the meshes and hash it in the package manifest.
Generate `extras.rm` stable IDs and node bindings in the same export pass. Node
indices are only valid for that exact hashed GLB. Names are for people and
legacy compatibility, not the sole identity contract.

## Armor, LED and color metadata

Export semantic metadata alongside joint metadata, generated from the same
release-specific mappings. Bind assembly roles to nodes, and surface roles to
individual mesh primitives or explicitly split surface nodes. A material alone
cannot identify a target: unrelated parts can share the same CAD color.

The current simulator represents these facts in code:

- `rm-simulator-render/src/cad.rs` recognizes `rotor/armor_*` by name and hides
  the imported meshes. `outpost.rs` creates replacement housing, face artwork
  and two light bars per armor, tagged `OutpostArmor` and `OutpostArmorLight`.
- `rm-simulator-render/src/rune.rs` generates target, activated-arm and progress
  overlays, tagged `RuneTargetLight`, `RuneActiveLight`, `RuneActivatedLight`
  and `RuneProgressLight`. Their roles are not read from CAD metadata.
- `TeamColor` in the render crate supplies red/blue display and emission colors.
  The app maps world team ownership into that enum. These rendering colors are
  distinct from the original STEP material colors.
- `rm-simulator-world/src/outpost.rs` supplies fitted housing, optical dimensions
  and detection dimensions as separate constants. `projectile.rs::TargetFace`
  represents scoring geometry. `rune.rs::RuneKind` represents Small/Big Rune
  behavior. There is no general exported armor-size classification consumed by
  this path today.

Proposed fields in the versioned `extras.rm` / sidecar contract:

| Field | Meaning |
|---|---|
| `roles` | Multiple applicable roles, such as `armor_module`, `armor_housing`, `led_surface`, `rune_target`, `dart_detector`, `guiding_light`, `status_indicator`, or `protective_shield`. A protective shield is not automatically a scoring armor module. |
| `module_id` | Owning semantic module for child surfaces, so its housing, artwork, LEDs and detector can be associated without matching names. |
| `armor.family` | `robot`, `outpost`, `base`, `dart_detection`, or `unknown`; equipment-specific modules must not be forced into robot armor categories. |
| `armor.size_class` | `small`, `large`, `custom`, or `unknown`. Normalize the informal armor size "big" to `large`; include explicit dimensions and evidence rather than inferring size from a bounding box alone. |
| `geometry` | Separately identified housing dimensions, optical dimensions, and target-frame reference. Each dimension record declares its frame and units. |
| `detection` | Optional shape/mask and rule-profile reference, with provenance. Mark unresolved detection data explicitly. An absent detector is not permission to score the entire mesh. |
| `led.function` | For example `armor_bar`, `rune_target`, `rune_activated_outline`, `rune_progress`, `center_logo`, `dart_guidance`, or `status`. Only assign `led_surface` when that surface is identified as luminous. |
| `led.channel` | Stable independently controllable light-group ID; optional segment index for progress lights. Several primitives may share a channel. |
| `color.mode` | `team`, `fixed`, or `source_material`. Team mode references a particular instance/face owner; fixed mode carries an explicit color; source mode retains CAD appearance. |
| `color.fixed_srgb` | RGB values in [0,1] for a fixed appearance, when applicable. Keep original STEP sRGB separately in provenance/material metadata. glTF material factors use their required linear representation. |
| `appearance_profile` | Optional reference to authored masks/materials and supported visual states. This describes available looks, not current match state. |

Do not overload `size_class` with rune mode. A rune asset can declare
`supported_modes: ["small", "big"]`; its current mode belongs to runtime state
and does not change the physical size of its target. Likewise `team` is resolved
per placed instance or per rune face, while fixed green dart-guidance lights
remain green regardless of team. Source paint, team ownership, LED emission
color and current light state are separate properties.

Illustrative records below demonstrate the contract, not verified source-part
assignments. Unknown classifications remain explicit until the CAD/rule mapping
is reviewed. A real export also supplies the provenance and node bindings
described above.

```json
{
  "schema_version": 1,
  "modules": [
    {
      "id": "outpost.rotor.armor.0",
      "roles": ["armor_module"],
      "armor": {"family": "outpost", "size_class": "unknown"},
      "target_frame": "outpost.rotor.armor.0.target",
      "appearance_profile": "outpost_armor"
    }
  ],
  "surfaces": [
    {
      "id": "outpost.rotor.armor.0.led.left",
      "module_id": "outpost.rotor.armor.0",
      "roles": ["led_surface"],
      "led": {
        "function": "armor_bar",
        "channel": "outpost.rotor.armor.0.lights"
      },
      "color": {"mode": "team", "owner_ref": "instance.team"}
    },
    {
      "id": "base.dart_target.guiding_light",
      "module_id": "base.dart_target",
      "roles": ["led_surface", "guiding_light"],
      "led": {"function": "dart_guidance", "channel": "base.dart_guidance"},
      "color": {"mode": "fixed", "fixed_srgb": [0.0, 1.0, 0.0]}
    }
  ]
}
```

The example green RGB is an authored rendering choice, not a calibrated
conversion of the manual's 520 nm guiding-light specification. Emissive strength
also needs an explicit rendering profile; a CAD color cannot supply it.

Roles do not automatically propagate from an assembly to every descendant.
An `armor_module` contains housing and lights, but only designated surfaces are
luminous and only its separately defined detector scores hits. Splitting mixed
primitives for classification must preserve triangles, source face provenance
and original colors. Reused mesh instances may have different owners; consumers
must not recolor every instance by mutating one shared material.

Validate all module/frame/channel references and primitive bindings, allowed
size classes, RGB ranges, and required owner references. Report unclassified
parts and unresolved detection profiles. Consumer migration should replace name
and color heuristics with these bindings, retaining a legacy fallback only for
older packages. Validate independently controlled armor LEDs and opposing rune
face colors in addition to the articulation checks below.

## Rune appearances

Export separate housing, light-arm, target/ring and center-logo surfaces with
stable roles. Preserve the original STEP colors as the default. Optional
authored masks and materials can provide inactive, active, hit and team-colored
appearances. Match state chooses which surfaces are lit; flash duration and
animation timing remain simulator settings unless sourced to a rule.

If "shades" means material looks, optional
[KHR_materials_variants](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_materials_variants/README.md)
can package preset appearances. Its variants select material mappings; independent
per-arm runtime states still need semantic surface bindings. If it means shaders,
export masks/material inputs and roles, with engine-specific shader code in the
renderer. Neither requires duplicating the complete rune geometry per state.

## Implementation order and acceptance checks

1. Add release-specific semantic mappings and an audit of matched, ambiguous and
   unclassified source occurrences. Inspect the moving groups before naming
   them as verified mechanisms.
2. Make the GLB reader traverse scene roots and accumulate matrix/TRS transforms.
   Test nested rotations/translations and shared mesh instances using synthetic
   geometry with independently calculated expected coordinates.
3. Extend the writer with hierarchy, provenance and joint bindings. Compare
   rebased rest-pose world triangles against the current export, preserving
   source membership and colors. Bounding boxes alone are insufficient.
4. Start with outpost and rune pivots, then base dart carriage, gate/platform,
   and finally verified shield motion. Check pivot invariance, axis direction,
   limits, both field placements and visual/collision agreement at sampled poses.
5. Update simulator formats to preserve links before grouping by color. Until
   joint support exists, explicitly export a named static pose or reject an
   articulated input; do not silently discard joints.
6. Migrate rm-simulator to sidecar frames and stable IDs, removing hard-coded
   pivots and geometry-based cap detection only after visual and collision checks.
   Regenerate/deploy the package after consumer compatibility is established.

The initial implementation exports metadata, visibility layers and joint nodes,
with checksum-pinned mappings for the existing rune/outpost hierarchy. Base shield and dart gate bindings now support explicitly illustrative
travel. Actual linkage/stroke calibration and remaining surface identification
still require CAD/mechanism work; the rulebook alone cannot supply them. Text and logo classification
and collision removal are deferred; only layer infrastructure is included.
Production assets have not been replaced.
