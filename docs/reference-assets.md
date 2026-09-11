# Reference assets and motion

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

Inspect the package in the [interactive viewer](viewer.md), or export it with the [articulated exporter](articulated-formats.md) to adjust the bound joints. The viewer reads local files in your browser.

The reference includes Rune and Outpost rotation, Base shields and rail target, and the Dart window. The Technology Core has six joint frames whose CAD geometry remains unbound. Its preview rig is separate from the exported equipment model.

## Motion verification

Run `ocpenv/bin/python python/verify_reference_motion.py` to compare all visual
and collision source triangles/materials at rest against the pinned source and test
the moving groups. The check uses NumPy and SciPy. The recorded result is
[previews/motion-verification.json](previews/motion-verification.json).

The rune center matrices remain unchanged under a quarter-turn while the arms
and surrounding hubs move. The outpost's 1,168 fastener triangles retain their
pose relative to the rotor. At full closure, the dart carriage's
lowest point is 205mm above the asset reference floor, at the pictured platform level. At full base opening,
all three shield assemblies remain inside the base's convex XY footprint with
at least 2.89mm clearance. The shield slide uses 170mm outward and
45mm downward travel. The labelled
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

The retained [Core rig helper](technology-core-joints.md#rule-based-translation-demo) evaluates the 100 mm post-insertion translation and a separate pose-tour trajectory. See [Dart window travel](dart-window.md) for the corrected lower stop.
