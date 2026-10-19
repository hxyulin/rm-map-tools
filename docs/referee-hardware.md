<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Referee hardware prototypes

The user-supplied DJI / RoboMaster STEP files now have a source-derived visual
prototype pipeline. This is separate from the arena exporters and from robot
mechanical descriptions. It does not alter either simulator field package.

| Module | Source triangles | Rough triangles |
| --- | ---: | ---: |
| AM02 small armor | 38,524 | 114 |
| AM12 large armor | 37,774 | 174 |
| VT03 transmitter, cables omitted | 177,410 | 147 |
| LI01 light bar and brackets | 200,815 | 190 |
| SM01 speed sensor, cables omitted | 82,990 | 822 |
| FI02 field interaction | 13,844 | 66 |
| Total | 551,357 | 1,513 |

The rough GLBs together occupy 158,832 bytes in the cable-free export.
Triangle count falls 99.73%. A second, finer `coarse` tier totals 16,078 triangles.
Counts are placed mesh triangles for one of each module, not an assembled robot.

## Rebuild

Use the existing CAD Python environment. Place the supplied files at the names
below under `source/referee-hardware/`; source SHA-256 values are pinned in
[`rules/referee-hardware.json`](../rules/referee-hardware.json).

```text
AM02.step  AM12.step  VT03.step  LI01.step  SM01.step  FI02.step
```

```sh
ocpenv/bin/python python/referee_hardware.py \
  --sources source/referee-hardware --out out/referee-hardware
ocpenv/bin/python python/preview_referee_hardware.py out/referee-hardware
ocpenv/bin/python -m unittest discover -s python -p test_referee_hardware.py
```

Export requires a new output directory and refuses a source checksum mismatch.
The review renderer uses the existing depth rasterizer (requires `clang++` or
`g++`), Pillow and VTK. Outputs include `*-source.glb`, `*-coarse.glb`,
`*-rough.glb`, regenerable NPZ geometry, a manifest, CAD ownership notice,
five matched source/candidate views per model, `review/gallery.html` with model,
view and detail controls, an overview and validation report.
Original STEP and all generated geometry stay outside Git.

## Approximation and appearance

- `source`: native faces tessellated at 0.25 mm / 0.35 rad, with XCAF color
  inheritance. This is a reference mesh, not an exact analytic STEP export.
- `coarse`: planar mounting openings up to 8 mm world-axis span are capped.
  Large planar surfaces remain on their planes while their edges simplify at
  0.5 mm meshoptimizer error. Other detail simplifies at 1.5 mm.
- `rough`: fit convex envelopes to individual native solids, simplify detail,
  omit visual components under 12 mm maximum source-axis span and remove fitted
  components fully enclosed by another fitted envelope. Recesses, bores and
  bracket perforations may deliberately disappear. Non-solid source surfaces
  retain mesh simplification rather than receiving a convex envelope.
- The two SM01 open-housing solids retain source topology rather than becoming
  convex envelopes. VT03 housing-side connector solids retain source topology.
- Both candidate tiers omit the attached cables and cable-end plugs on VT03,
  LI01 and SM01 using explicit `omit_cable_solids` selectors. Housing sockets
  remain. The source reference stays complete. These native solid ordinals are
  scoped to pinned source checksums; they are not STEP entity IDs or a generic
  semantic classifier.
- Rough meshes keep separate nodes for retained native solids, carrying the
  hardware identity, source checksum and native solid ordinal. Roles are
  explicitly unclassified; LED, optical, mounting and detector frames require
  later reviewed bindings. Triangle ranges preserve provenance in the manifest.
- AM02, AM12 and FI02 provide source colors. VT03, LI01 and SM01 are unstyled
  and remain neutral gray. Rough material assignment
  uses the nearest source triangle centroid within the same solid; it does not
  invent a palette, team paint, artwork, transparency or emission.

The error settings are meshoptimizer metrics for particular passes, **not a
whole-model Hausdorff bound**. Filling recesses and removing details intentionally
introduce larger differences. Cable omission also causes large distances from
the complete source reference; those distances are intentional and do not measure
housing fidelity alone. Five-view silhouette differences are recorded in
`review/validation.json`; these are sampled diagnostics, not certification.

## Frames and intended use

GLBs use metres and retain original STEP axes, translated to the center of the
source tessellation's bounding box. `source_to_model_matrix` records that
translation in metre coordinates. Axis-aligned dimensions in the manifest include
source pose and attached brackets/leads; they are not necessarily the product's
nominal width/height/depth.

The prototypes are for visual review. They declare `collision_eligible: false`
and `sensor_geometry: false`. A filled visual hull must not close the speed
sensor's projectile passage or become an armor detection mask in physics.
There are no inferred masses, collision contracts, camera intrinsics, mounting
poses, articulation, or 2027 sensor dimensions. Old hardware CAD retains its
2019/2020 identity. These bindings belong to the later robot-description work.

Source geometry belongs to DJI / RoboMaster under its original terms. The
exporter software's dual license does not relicense CAD or derived geometry.
No archives or releases are published by these commands.

## Team robot assembly prototype

`benchmarks/2026-10-18-team-robot/` contains a separate source-derived robot
experiment. It combines the Zhongzhou Zhulong 26.5 chassis by 芝士披萨k with
the Zhejiang University Hello World 2026 Omni gimbal by Chenic. Original releases:

- [Zhulong chassis](https://bbs.herkules.dev/articles/01M0Z3C64A3ACBNKZVA1R041AV)
- [Hello World gimbal](https://bbs.herkules.dev/articles/01M1NA853WMDH11GRJBZW6WDRE)

The intended use is noncommercial RoboMaster team-to-team technical exchange,
as confirmed by the user. Original CAD terms remain attached to the geometry.
The gimbal release restricts use to noncommercial RoboMaster team exchange and
requests source credit. GLB asset/node metadata, the manifest and generated
`CAD-NOTICE.md` preserve attribution and source identity; the software license
does not relicense these models.

The recipe pins the STEP identity, cooked visual mesh and exact occurrence audit
for both sources. Raw files remain outside Git. Alias the directly downloaded
chassis STEP to `zhulong-2026-chassis.step`. Extract the `Omni.STEP` variant from
the Hello World ZIP and alias it to `zju-2026-gimbal-1.step`; do not substitute
the Balance variant. STEP hashes are recorded in `recipe.json`.

From this repository's root, set `robot_source_dir` to the directory holding
those two original files and `robot_work_dir` to a new development output path:

```sh
ocpenv/bin/python benchmarks/2026-10-18-team-robot/prepare_source.py \
  --sources "$robot_source_dir" --out "$robot_work_dir" --low-only chassis
ocpenv/bin/python benchmarks/2026-10-18-team-robot/prepare_source.py \
  --sources "$robot_source_dir" --out "$robot_work_dir" --low-only gimbal
ocpenv/bin/python benchmarks/2026-10-18-team-robot/audit_source.py \
  --sources "$robot_source_dir" --out "$robot_work_dir" zhulong-2026-chassis
ocpenv/bin/python benchmarks/2026-10-18-team-robot/audit_source.py \
  --sources "$robot_source_dir" --out "$robot_work_dir" zju-2026-gimbal-1
ocpenv/bin/python benchmarks/2026-10-18-team-robot/assemble.py \
  --sources "$robot_work_dir" --out "$robot_work_dir/assembled"
ocpenv/bin/python benchmarks/2026-10-18-team-robot/validate.py \
  --sources "$robot_work_dir" "$robot_work_dir/assembled"
ocpenv/bin/python benchmarks/2026-10-18-team-robot/review.py \
  "$robot_work_dir/assembled"
```

The source probe uses 0.25 mm / 0.3 rad reference tessellation to recover the
original center, then 1 mm / 0.8 rad tessellation and a 1 mm meshoptimizer metric
within each source-solid/material group. `--low-only` avoids exporting the large
reference GLB/NPZ. The audit recovers definition names, occurrence paths, located
solid membership and source placements. Cooked-input checksum mismatches stop
assembly; inspect differences rather than silently accepting a changed binding.

The resulting robot has 166,009 triangles: 110,875 chassis, 55,086 retained
gimbal, and 48 from four plain integration posts. The duplicate lower gimbal
ammunition/electronics structure is omitted in favor of the chassis structure;
the gimbal bearing, yaw drive, crossbeam and tensioners remain. Source dimensions
are unchanged. Neutral bounds are about 579 × 546 × 577 mm; the reviewed aimed
poses stay below 590 mm tall. The package uses glTF X-left/Y-up/Z-forward,
metres, floor Y=0; FLU coordinates are `[z, x, y]`.

`animated.glb` provides a six-second loop with independent yaw, pitch, motor
crank, counter-rotating connecting rod and four wheel spin axes. The source
parallelogram linkage closes at both pins over 299 checked yaw/pitch samples.
The validator also checks retained source material dictionaries/metadata,
coverage, float32 rest geometry and animation quaternion/channel validity.
`neutral.glb`, `aimed.glb` and `depressed.glb` provide matching static views.

This is a visual fitting prototype. Fixed-part interference and feed-system
compatibility are not certified. Native suspension geometry remains separate at
rest; suspension travel, force calibration, collision masks, scoring, mass and
inertia still need explicit simulator bindings. No simulator runtime asset or
rules are changed by these scripts.


## Complete tunnel Infantry and Hero review candidates

`benchmarks/2026-10-18-team-robot/candidates.json` pins Qingdao University Future's
RM2026 fixed-height tunnel Infantry and Artisans' RM2026 folding tunnel Hero.
Download URLs, source authors, terms and STEP SHA-256 values live in the recipe.
Original geometry remains external and under its original terms. Future's complete
STEP is the `三维图纸/整车装配.STEP` member of its linked release ZIP; the Hero is
a directly attached STEP. The source aliases expected by the commands are
`qingdao-2026-infantry.step` and `artisans-2026-tunnel-hero.step`.

For each recipe key (`tunnel_infantry` or `hero`), run the same source preparation
and source hierarchy audit, then package and render it:

```sh
ocpenv/bin/python benchmarks/2026-10-18-team-robot/prepare_source.py --sources SOURCE_DIR --out SOURCE_DIR --recipe benchmarks/2026-10-18-team-robot/candidates.json --low-only tunnel_infantry
ocpenv/bin/python benchmarks/2026-10-18-team-robot/audit_source.py --sources SOURCE_DIR --out SOURCE_DIR qingdao-2026-infantry
ocpenv/bin/python benchmarks/2026-10-18-team-robot/package_candidates.py --sources SOURCE_DIR tunnel_infantry
ocpenv/bin/python benchmarks/2026-10-18-team-robot/review_candidates.py --sources SOURCE_DIR tunnel_infantry
ocpenv/bin/python benchmarks/2026-10-18-team-robot/review_candidates.py --sources SOURCE_DIR --neutral tunnel_infantry
```

Keep the pinned STEP alongside the generated meshes/hierarchy for packaging
verification. Preparation requires a new `<source_model_id>-pilot/` directory; packaging/review can be rerun.

Results: Future has 1,233 native solids and 190,438 triangles; Artisans has 738
native solids and 206,777 triangles. Both retain the additional non-solid group.
The named source trees have 797 and 216 groups. Packaging adds hierarchy and a
rigid floor-aligned review frame without changing cooked binary mesh payloads.
It verifies single ownership of every mesh node, original material dictionaries
and equal placed triangle counts before writing the manifest. No joints, mass,
collision geometry, tunnel-clearance certification or gameplay bindings are inferred.
The 1 mm meshoptimizer metric is not a certified whole-surface deviation bound.

`package/model.glb` retains source appearance. `package/graphite.glb` overrides
explicitly uncolored materials and the pale blue CAD tint with sRGB
(0.095, 0.10, 0.11), metallic 0.1, roughness 0.45. Original PBR factors remain in
`extras.display_override.original_pbr`; original STEP color metadata stays intact.
This is a user-selected display treatment, without a carbon weave texture.
Unstyled surfaces in `neutral-*` renders use lighter inspection grey, explicitly
separate from source appearance and the graphite display material.

The complete source-pose envelopes are about 663 × 584 × 253 mm (Infantry) and
787 × 835 × 423 mm (Hero), width × length × height. The Infantry report targets
a 250 mm tunnel; its static CAD envelope needs suspension/clearance calibration.
The Hero is published in an unfolded pose. Fit source wheel, armor, camera,
barrel and folding joints before treating either as a playable robot.


## Artisans folding Hero binding

`bind_hero.py` binds the lower folding axis and separate firing pitch of the
Artisans STEP. Lower/upper hinge centres were fitted from the source bearing
assemblies (source Z=122 / 236.47 mm, upper Y=9.1 mm). The source frame is rotated
into glTF X-left/Y-up/Z-forward, with a fixed floor shift. A 127 degree fold and
90 degree/s actuator are simulator assumptions; the upper firing stage
counter-rotates the fold. Wheel-leg actuator motion and flexible feed-chain
motion are not inferred.

Open shells must retain source leaf ownership before binding. Otherwise the
camera shell and unrelated open surfaces share one visual group and remain
behind when the head moves. The additive `--faces` / `--split-shells` options
preserve them without changing the default recipe for the earlier Omni.

```sh
ocpenv/bin/python benchmarks/2026-10-18-team-robot/audit_source.py --sources SOURCE_DIR --out PREPARED_DIR --faces artisans-2026-tunnel-hero
ocpenv/bin/python benchmarks/2026-10-18-team-robot/prepare_source.py --sources SOURCE_DIR --out PREPARED_DIR --recipe benchmarks/2026-10-18-team-robot/candidates.json --split-shells --hierarchy PREPARED_DIR/artisans-2026-tunnel-hero-hierarchy.json --low-only hero
ocpenv/bin/python benchmarks/2026-10-18-team-robot/bind_hero.py --sources SOURCE_DIR --prepared PREPARED_DIR --out BOUND_DIR
ocpenv/bin/python benchmarks/2026-10-18-team-robot/validate_hero.py --prepared PREPARED_DIR BOUND_DIR
ocpenv/bin/python benchmarks/2026-10-18-team-robot/review.py BOUND_DIR --poses neutral mid-fold folded
```

The bound package contains 206,722 triangles across the original 738 solids and
four open-shell leaf groups. It retains every prepared part, original source
appearance and provenance. Named body/yaw/fold/pitch/four-wheel groups preserve
source rest geometry up to float32 rebasing. `manifest.json` pins the source,
prepared inputs, exporter and runtime scene; `CAD-NOTICE.md` retains author terms.
The supplied review poses are not hardware travel or collision certification.
In rm-simulator this is a 2026 Hero practice preset, with effective ray-wheel
suspension and independent approximate collision proxies. The folded source
camera view is occluded by chassis structure; third-person is available.


## Source robot roster expansion (2026-10-19)

`benchmarks/2026-10-18-team-robot/roster.json` records the selected replacement
roster: existing assembled Omni Infantry, Future tunnel Infantry, Artisans Hero
(reference), two Engineer-derived Heavy variants, and a tunnel Sentry. It is an
intake inventory, not a runtime support declaration. The Hero does not stand in
for a 2027 Heavy, and an Engineer CAD donor does not imply 2027 Heavy compliance.

The tunnel Heavy donor is [Capital Normal University PIE / H3's 2026
Engineer](https://bbs.herkules.dev/articles/01M0YXED5X9S8DKY2BBCT220PZ).
Its directly attached ZIP contains the complete
`【RM2026 工程机器人】首都师范大学 PIE战队/工程机器人-分区赛版本.STEP`.
The STEP checksum and archive member are pinned as `tunnel_heavy` in
`candidates.json`. Its report §4.2 describes horizontally folding serial arm
links, a separate image-transmitter lift and a retracting UWB mount; §4.2.8
covers the chassis. Preserve those assemblies rather than folding the entire
arm as one rigid object. Source +Y is up, unlike the earlier source robots;
the review rotation is explicitly identity. Source pose is not tunnel pose.
All source faces are unstyled; graphite remains a presentation choice.

DreamChaser's 2026 Engineer release is selected for the stair Heavy, and EGA's
2026 complete tunnel Sentry for the Sentry. Their public releases link to Baidu
Netdisk rather than a directly attached complete STEP. The user downloaded
these releases on Metis and authorized their transfer. DreamChaser includes
complete STEP assemblies. Both EGA ZIPs were inspected: they contain complete
SolidWorks assemblies but only component STEP files. A complete Sentry STEP
export is pending. Exact source checksums and joint ownership remain pending; do not replace them with an unrelated model or
present their authors' real-robot capability claims as simulated capabilities.
Ambition's directly attached ZIP had no complete neutral-format assembly,
and SaltWave's complete Sentry STEP is an alternate, without verified tunnel
capability. Neither is silently substituted into the chosen roster.

For PIE, audit with `--faces`, then prepare with `--split-shells --hierarchy`
(as for the Hero) using recipe key `tunnel_heavy`. Candidate packaging now
attaches each open-shell mesh to its audited leaf, preserving separate camera,
housing and arm ownership. Solid aliases retain their occurrence paths without
duplicating placed geometry. Unknown/non-leaf shell paths fail packaging.
Use the existing package/review commands with `tunnel_heavy`; original CAD,
prepared meshes and images remain external generated files.

The Metis transfer was verified by SHA-256 for 13 files / 3,497,690,266 bytes.
DreamChaser's complete national-finals single-arm STEP is now pinned as
`stair_heavy`. SaltWave's complete half-swerve/half-omni Sentry is pinned as
`sentry_alternate`, a user-approved temporary option while EGA needs STEP
conversion. SaltWave and DreamChaser both use source +Y up, confirmed by the deck
plate thickness and yaw bearing plane. The
rotations in `candidates.json` record those differences explicitly.

PIE's first complete review package contains 165,541 triangles, 1,694 source
solids and 16 separately owned shell groups. Original binary mesh payloads and
source materials survive packaging exactly. Source-pose extents are about
613 × 851 × 411 mm (width × length × height); this is an unbound arm pose, not
a tunnel-clearance claim. Generate it with recipe key `tunnel_heavy`.

Large unstyled assemblies exposed two avoidable costs. The preparer now hashes
the STEP once per run rather than once per source mesh. Native analysis and
meshing also skip paint lookups when the XCAF color table is empty, which proves
no paint can be found. Colored documents retain the existing resolution path.
Regression fixtures compare full geometry/palette/statistics against the former
empty-table path and check that authored body paint remains present.

The full PIE cook before and after these performance changes produced a
byte-identical 13,528,740-byte `low.glb` (165,541 triangles). Measured cook time
was 636.74 s before and 176.40 s after, about 3.6× faster in this run. This is a
single local measurement, not a cross-machine benchmark. The redundant benchmark
output was removed after recording the hashes and timings.

DreamChaser's cooked package contains 337,237 triangles, 1,396 solids and 22
separate shell groups; SaltWave's contains 218,879 triangles, 4,123 solids and
four shell groups. Packaging preserves mesh binary payloads, source materials
and complete/disjoint source ownership for both. These are source-pose visual
candidates; the DreamChaser wheel linkages still need their drive/climb poses
bound, and SaltWave steering/gimbal motion is unbound. Neither is yet a playable
replacement in rm-simulator.


## Remove CAD reference geometry from robot candidates

`python/robot_reference_geometry.py` applies the reviewed `reference_exclusions`
in `candidates.json` during candidate packaging. Original STEP and `low.glb`
inputs remain intact. The pass selects checksum-scoped native solids or a
specific component/region inside an audited source leaf; it checks occurrence
names and expected triangle counts and fails on drift. A sphere fit or a word
such as “range” is not an automatic removal rule.

The initial cleanup removes:

- PIE: the 70 mm controller exclusion hemisphere; a camera viewing volume and
  overlapping coarse camera proxy (the complete VT03 remains); only the large
  eight-triangle positioning-module viewing cone inside its mixed hardware leaf.
- SaltWave: camera/controller exclusion hemispheres, camera viewing volume,
  the wheel's `地面` CAD reference sheet, and two clearance cones merged into the
  controller solid. The controller board ends at local Y=14 mm; the 92 helper
  triangles extending beyond local Y=15 mm are selected in that source frame.
  This 15 mm cut is an inspected CAD selector, not a competition-rule constant.

PIE is now **165,147 triangles** (394 removed); SaltWave is **217,711 triangles**
(1,168 removed). All actual controller boards, UWB hardware/connectors, cameras
and LiDAR housings remain. In particular, `mid360带范围` contains the physical
LiDAR and is retained; PIE's rounded energy-unit housing also remains. Other
reviewed source models yielded no additional confirmed reference bodies. The
Future part named `26铝柱M3×120×D5` produces a sphere-fit false positive because
its coarse cylindrical vertices lie on a circumsphere; it is a physical post.
DreamChaser's unusual wheel arrangement is its source linkage pose, not a
missing-geometry problem, and is not flattened/scaled by this cleanup.

The packager prunes unused mesh/accessor/buffer resources after exclusion and
verifies exact retained vertex attributes, triangle membership, source materials
and local part poses against the untouched cooked input. Empty source anchors
and exclusion reasons remain in the hierarchy/manifest and generated notice.
Retained attributes keep their exact bytes; the final GLB container is repacked,
so its complete binary payload is intentionally different from the raw cook.
All six candidate robot designs (seven source assemblies, including both
halves of the assembled Omni) were checked for analogous spheres/cones, named helpers and loose reference sheets.

`review_candidates.py` now renders the physical package by default. `--raw`
shows the cooked reference geometry separately in `review-raw/`. Both use the
same source frame and camera bounds, so changes to framing cannot disguise a
geometry change. Re-run packaging before review when changing exclusion rules.

```sh
ocpenv/bin/python -m unittest discover -s python -p 'test_robot*.py'
ocpenv/bin/python benchmarks/2026-10-18-team-robot/package_candidates.py --sources SOURCE_DIR tunnel_heavy
ocpenv/bin/python benchmarks/2026-10-18-team-robot/review_candidates.py --sources SOURCE_DIR --neutral tunnel_heavy
ocpenv/bin/python benchmarks/2026-10-18-team-robot/review_candidates.py --sources SOURCE_DIR --raw --neutral tunnel_heavy
```

### Material-aware candidate appearance

Candidate packaging also produces `materials.glb` and an auditable
`materials.json`. `model.glb` remains the source appearance and `graphite.glb`
remains the earlier uniform display option. `python/robot_materials.py` creates
separate rubber, carbon, aluminum, steel, printed polymer, detector face,
housing and illustrative red diffuser PBR materials. These are inferred visual
choices, not source-authored material identifications or live referee lights.
Original authored paint is preserved; only explicit unstyled fallback and the
reviewed uniform pale CAD tint are eligible. Original materials/PBR metadata
remain in the output, with per-primitive assignment reasons and source paths.

Rules operate on leaf names, not entire wheel or armor assemblies. Carbon-tube
clamps stay metal. Named AM02/AM12 modules use inspected envelope classes to
separate faces, housings, diffusers and hardware. PIE mecanum roller sleeves,
Future omni rollers, Hero tread bodies and SaltWave's named rollers are handled
separately from hubs/side plates. DreamChaser's HEXROLL open shells require
connected-component roller selection: append index subsets, keep every original
triangle exactly once and retain all attributes. These dimensional selectors are
CAD appearance settings, not rulebook dimensions. Unknown parts stay neutral;
unnamed plates are not automatically claimed to be carbon fiber.

The material pass verifies exact per-node triangle multiplicity, attribute
bindings, original buffer bytes, source material/mesh declarations, hierarchy,
poses and animation bindings. It does not add collision or physics behavior.
The five complete raw candidates are reviewed separately; these material variants
have not replaced the existing bound Omni/Hero runtime packages.

```sh
ocpenv/bin/python benchmarks/2026-10-18-team-robot/package_candidates.py --sources SOURCE_DIR stair_heavy
ocpenv/bin/python benchmarks/2026-10-18-team-robot/review_candidates.py --sources SOURCE_DIR --materials stair_heavy
```

`review-materials/` uses the exported PBR base colors with the diagnostic diffuse
rasterizer. It is a color-assignment review, not a metallic/roughness or carbon
weave shading preview. No texture or extra tessellation is generated.

### Source armor mount/replacement pass

`python/robot_armor.py` identifies the face, housing and two diffusers inside
reviewed AM02/AM12 source leaves, fits an outward scoring-face frame, and leaves
separate brackets and fasteners intact. The flattened Zhulong source instead
uses explicit whole-module solids 3/6/81/82, scoped to its pinned STEP identity;
its damaged names are not used for inference. Its face normal is the reviewed
15-degree installation angle. Physical housing dimensions are visual/physics
fits; they do not automatically define an effective detection area.

All five complete candidates now include `armor.json` and `armor-ready.glb`.
The latter omits the selected source surfaces and embeds the fitted mount
contract; a consumer must spawn the simulator modules at those frames. There
are four unique mounts per candidate. SaltWave contains eight module leaves:
four pairs overlap with approximately 1.2–1.3 mm offsets. Explicit primary/alias
paths in `candidates.json` merge the reviewed pairs, checking center distance
under 2 mm and compatible orientation before combining surface selectors. This
is a source-specific alias policy, not a global proximity-based deletion pass.

`bind_armor.py` applies the same pass to existing articulated Omni/Hero packages,
writing to a separate output folder. It retains motion groups, source mounts,
original notices and inferred material assignments. The replacement manifest
contains body-frame FLU poses and housing dimensions. The simulator admits the
contract only when it matches the fitted physics preset, then draws complete
physical modules with the existing armor atlas and caller-owned light states.
Without that contract, legacy packages retain their CAD and receive overlays.

```sh
ocpenv/bin/python benchmarks/2026-10-18-team-robot/bind_armor.py \
  --sources SOURCE_DIR --package SOURCE_DIR/assembled --out SOURCE_DIR/assembled-armored
ocpenv/bin/python benchmarks/2026-10-18-team-robot/bind_armor.py \
  --sources SOURCE_DIR --package SOURCE_DIR/bound-hero --out SOURCE_DIR/bound-hero-armored
ocpenv/bin/python -m unittest discover -s python -p 'test_robot*.py'
```

Validation verifies exact retained primitive/attribute bindings, source
materials, hardware and transforms. The playable packages retain 164,663 source
triangles (Omni) and 201,148 (Hero), before the simulator adds its small fitted
modules. No CAD mesh becomes a detailed collision mesh. The Hero's physical
shell is large, but the simulator intentionally retains its existing 101 × 94 mm
small-detector policy pending a separate AM12 effective-area rules check. The
raw donor candidates remain unbound chassis: mount metadata is not admission.

### DreamChaser source-bound stair linkage

`benchmarks/2026-10-18-team-robot/bind_stairs.py --sources SOURCE_DIR --out PACKAGE`
exports the reviewed donor as `dreamchaser-stair-heavy-v1`. It pins the input
STEP hash, preserves every source triangle before the separately approved armor
surface replacement, and rebases source leaves onto rigid body/front/coupler/
rear/slider/guide/wheel groups. Neutral, mid-climb and deployed GLBs are included.
The manifest's `source_reconstruction_error_m` measures the double-precision
rigid-frame round trip before GLB float32 storage, not a rendered error bound.
Producer, linkage and input mesh hashes identify the reproducible recipe.

`python/stair_linkage.py` contains disjoint reviewed source membership and an
analytic closed planar linkage. Dimensions come from CAD bearings and the
release's technical report Figures 2–3 (130/190/200/320 mm). The source is the
raised-front endpoint; the level travel endpoint is solved from equal wheel
heights. The upper manipulator and auxiliary sensor linkages remain fixed.
The simulator applies caller-owned link frames and individual wheel suspension;
it does not claim calibrated torque or deformable belts. This profile currently
uses 2026 Engineer practice, without admitting RM2027 Heavy gameplay.

```sh
ocpenv/bin/python -m unittest discover -s python -p 'test_stair_linkage.py'
```

### Tunnel donor bindings

`benchmarks/2026-10-18-team-robot/bind_tunnel.py` binds PIE (`--source heavy`,
the default) and Future (`--source infantry`) into schema-4 runtime packages.
Pass `--sources SOURCE_DIR --out PACKAGE --base-config ENGINEER_CONFIG.json`.
The simulator's `robot_tunnel export-base FILE` example produces the baseline.
The manifest pins its hash along with the input GLB, STEP release, producer,
configuration and each output pose. Source material tables and geometry buffers
are retained exactly; only hierarchy transforms, approved armor surfaces and
reviewed motor leads change. Each written GLB verifies unchanged binary payload
and exact retained triangle count. No whole-model scaling is used.

PIE's source cylinder axes and report §4.2 define a 7° shoulder leveling motion,
counter-rotating elbow, 70 mm camera slide along its 45° rail and a 20° UWB hinge
retraction. The shared scalar input is a prescribed simulator stow policy. The
upper arm gets an oriented source envelope; an axis-aligned aggregate falsely
fills space above the stowed arm. Fixed physical groups and fitted armor retain
collision, while open/unclassified shells remain visual-only.

Future's actual tyre leaves, excluding wheel mounts, determine loaded height
(approximately 249 mm). Its source gimbal yaw is neutralized to the barrel
heading. Pitch linkage motion is approximate, not a four-bar closure solution.
The package includes fitted muzzle/camera offsets and four real armor mounts.
The simulator tests these packages in a 250 mm contact fixture; this is not a
certification for arbitrary terrain or elevated gun pitch. PIE remains an
Engineer practice donor pending RM2027 Heavy admission.

```sh
ocpenv/bin/python -m unittest discover -s python -p 'test_tunnel_binding.py'
```

### Source assembly workbench rig

`benchmarks/2026-10-18-team-robot/bind_assembly.py` exports the complete PIE
Engineer, three RMUC2027 Tech Core components and the source Energy Unit as
five independently checksummed GLBs plus `assembly.json`. It is separate from
the scalar tunnel-stow profile. Reproduction and the native equipment cache
prerequisite are described in rm-simulator's `docs/assembly-workbench.md`.

First use `python/audit_joint_axes.py STEP --out AUDIT.json` to obtain the PIE
bearing evidence. The read-only auditor imports source STEP, records analytic
cylinder lines/radii/bounds with OCCT face/shell/solid ordinals, and fingerprints
the original bytes. Those ordinals are not original STEP entity IDs. The binder
pins the PIE release, checks cached Core STEP/GLB pairs, and records input/output
hashes and producer provenance. It audits Core source components automatically.

PIE joints use the J1–J6 bearings and manually assigned source occurrence
subtrees, including moving output shafts separate from fixed bearing outers.
The gripper uses two distinct bearing lines (solids 1671/1670); source solid
1684 is on the same axis as 1670. Core shells partition the six positioning
links. Head shell 1224 supplies Q's front shaft line; cylindrical cam patches in
1589 supply P's transverse line. Shell 1223 and 1430–1595 follow P; 1224–1429
follow Q; the remaining head stays on the positioning flange. These assignments
are explicit source-based hypotheses for moving-pose review. Reference axis
origins can be anywhere on the same bearing line.

Every retained source mesh is included once. Buffer bytes, primitive accessors,
material tables and reference-pose vertices are checked, with no remeshing or
schematic bearing replacement. Only previously approved dangling motor leads
are omitted. The five exports total 540,465 triangles and remain disposable
inspection assets outside Git. Their generated CAD-NOTICE retains PIE's exchange
terms and DJI's equipment ownership.

Joint ranges, grasp clocking and jaw opening are workbench policies. The source
report supports a serial six-axis design and approximately 180° J4 travel, but
it does not calibrate stops relative to the CAD zero. This is not torque,
self-collision, sensor, attachment or competition-compliance validation.

```sh
ocpenv/bin/python -m unittest discover -s python -p 'test_assembly_binding.py'
ocpenv/bin/python -m unittest discover -s python -p 'test_joint_axes.py'
```

The assembly workbench v3 binding fits P from Figure 5-7's 208 mm height,
169 mm post reach and 15 mm hinge offset. The source post establishes E and the
reference normal; P is E − 154 mm along that normal + 208 mm along source up.
The 2026 English V2.1.0 manual (printed p82) and 2027 drawing share these
measurements. Neither a small transverse fastener nor a 150 mm arc is used as
P. The source socket basis is orthonormalized before constructing the rig.
Q still follows shell 1430's carriage spindle as a source-group hypothesis;
rigid membership and mechanical stops require review. The fitted pedestal OXYZ
frame and head convex hull support placement rejection, not collision-free
planning. Source geometry and materials remain unchanged.

The v4 package also fits jaw stops to source TPU-pad triangle sweeps and actual
Energy Unit cross-sections. Long rods have no vertices at the grip height, so
the exporter intersects triangle edges with three axial planes instead of using
vertex-only bounds. The 95 mm caps surround a 64.6 mm mid-body envelope at the
grip; each jaw closes independently to that envelope plus 0.1 mm clearance.
`python/gripper_fit.py` and its synthetic geometry tests cover this fit. The
simulator uses these stops for a prescribed actuator and proximity-gated grasp,
not force-based contact. All mesh and material buffers remain unchanged.
