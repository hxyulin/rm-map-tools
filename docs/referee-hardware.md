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
