# Reference assets and joint previews

The local reference bundle is `../assets/rm2026-reference`, recorded with
checksums in [source/REFERENCE_ASSETS.json](../source/REFERENCE_ASSETS.json).
It combines the field and equipment semantic exports in one directory. The
original `rm2026-field` simulator installation remains unchanged.

Rebuild from the pinned input package:

```sh
ocpenv/bin/python python/update_reference_assets.py
```

Use `--replace` to update an existing reference, retaining a dated backup. The
updater validates input GLBs and both output manifests, builds in a staging
directory, and records the rules, source-manifest and output-manifest hashes.
It checks the nested equipment manifest as part of the reference. Mesh files
remain external and ignored by Git; only the index, rules and tooling are
committed.

The reference currently includes three authored rotation joints: the outpost
rotor and two rune faces. Base shield and dart gate joints now have explicitly illustrative travel.
Actual actuator/linkage calibration and LED surfaces inside mixed primitives
remain pending. Text/logo assignments are deferred. Layer
infrastructure is present, but no markings have been removed from collisions.

The current rm-simulator still drives legacy nodes by name. It needs to consume
the new sidecar's motion-node bindings before this reference replaces its active
package. See [semantic export](semantic-export.md) for the coordinate contract.

## Motion previews

| Mechanism | GIF | MP4 |
|---|---|---|
| Outpost rotor | [View GIF](previews/outpost-joints.gif) | [Play video](previews/outpost-joints.mp4) |
| Rune faces | [View GIF](previews/rune-joints.gif) | [Play video](previews/rune-joints.mp4) |
| Dart gate, illustrative | [View GIF](previews/dart-station-joints.gif) | [Play video](previews/dart-station-joints.mp4) |
| Base shields, illustrative | [View GIF](previews/base-joints.gif) | [Play video](previews/base-joints.mp4) |

Each clip lasts six seconds with a fixed camera. Rune/outpost rotate through
360 degrees; base/dart traverse their illustrative limits and return.
The original CAD meshes follow the exported sidecar's motion nodes; gold lines
mark the fixed axes. The angle label is the applied joint coordinate. These
clips demonstrate transforms, not rulebook motor timing or runtime LED effects.
The rune's central R artwork, backing disks and shaft-end cylinders stay
stationary with the existing static shaft/support geometry. The surrounding
hubs and arms rotate. Eight small fastener meshes that the legacy outpost
export left static now follow their carrier arm; no geometry was removed.

Generate both formats using Python with NumPy, VTK and Pillow, plus `ffmpeg`
on PATH. These packages are available in the local `ocpenv` environment.

```sh
ocpenv/bin/python python/preview/render_joints.py ../assets/rm2026-reference --asset outpost
ocpenv/bin/python python/preview/render_joints.py ../assets/rm2026-reference --asset rune
ocpenv/bin/python python/preview/render_joints.py ../assets/rm2026-reference --asset dart-station
ocpenv/bin/python python/preview/render_joints.py ../assets/rm2026-reference/equipment --asset base
```

Outputs go to `out/joint-previews` by default. MP4 is 960 x 720 at 20 fps;
GIF is 720 x 540 at 15 fps and loops continuously. JSON records beside the
clips identify the source GLB/sidecar hashes, joint IDs and output checksums.
The renderer validates its input hashes before rendering. It also writes
0-, 90- and 180-degree PNGs for visual inspection. The reviewed GIF/MP4 files
and their JSON records are copied into `docs/previews/` for repository browsing.

### Motion verification

Run `ocpenv/bin/python python/verify_reference_motion.py` to compare all visual
and collision source triangles/materials at rest against the pinned source and test
the moving groups. The check uses NumPy and SciPy. The recorded result is
[previews/motion-verification.json](previews/motion-verification.json).

The rune center matrices remain unchanged under a quarter-turn while the arms
and surrounding hubs move. The outpost's 1,168 fastener triangles retain their
pose relative to the rotor. At illustrative full closure, the dart carriage's
lowest point is 205mm above the asset reference floor, at the pictured platform level. At full base opening,
all three shield assemblies remain inside the base's convex XY footprint with
at least 2.89mm clearance. The shield slide illustrates 170mm outward and
45mm downward travel; it does not claim the physical linkage. The labelled
[reconstructed interior](base-reconstruction.md) stays fixed, and its reused
lower armor modules are visible through the gaps between fully expanded covers. The dart platform remains
fixed. Source triangles and materials match at rest to 1 micrometre; nothing
was removed from collisions.

The [Technology Core](technology-core-joints.md) exports six serial joint frames.
Its CAD geometry remains unbound pending a verified rigid-body partition.

The [base dart-target carriage](base-dart-target.md) and guiding light move
along a fixed rail with the rulebook's ±280mm range. A four-second sinusoidal
sweep is preview-only when no target mode is selected. The reference exports
rail/joint metadata and rule summaries; match-mode control remains unimplemented.

A separate [Technology Core translation demo](previews/tech-core-demo.gif)
illustrates the rulebook's 100mm post-insertion movement with fixed tool
orientation. It uses a disposable CAD-link rig with schematic bearings; see
[the demo details](technology-core-joints.md#rule-based-translation-demo).

The [clean Core pose tour](previews/clean/tech-core-demo-orbit.mp4) adds lifting,
lateral sweeps, and changing tool orientation around that insertion segment.
See [Dart window travel](dart-window.md) for the corrected lower stop.
