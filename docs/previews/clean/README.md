# Clean mechanism previews

These clips use a black background, camera-relative studio lighting, and a full perspective camera orbit. Titles, counters, and joint-axis markers are omitted. Text and logos that belong to the CAD geometry remain intact. MP4 is the preferred demo format; GIF copies provide quick looping previews.

The motion and geometry caveats from the inspection previews still apply: shield travel is illustrative, the base interior is reconstructed with reused armor modules, the rail's sinusoidal timing is demo-only, and the Technology Core uses a preview-only rig with schematic bearings for its rulebook-inspired 100 mm translation. These clips do not change exported geometry or simulator behavior.

| Assembly | Video | Loop |
| --- | --- | --- |
| Base | [MP4](base-joints-orbit.mp4) | [GIF](base-joints-orbit.gif) |
| Technology Core | [MP4](tech-core-demo-orbit.mp4) | [GIF](tech-core-demo-orbit.gif) |
| Rune | [MP4](rune-joints-orbit.mp4) | [GIF](rune-joints-orbit.gif) |
| Outpost | [MP4](outpost-joints-orbit.mp4) | [GIF](outpost-joints-orbit.gif) |
| Dart station | [MP4](dart-station-joints-orbit.mp4) | [GIF](dart-station-joints-orbit.gif) |

Reproduce from the reference package:

```sh
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/preview/render_joints.py ../assets/rm2026-reference/equipment --asset base --presentation --seconds 8 --out docs/previews/clean
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/preview/render_joints.py ../assets/rm2026-reference/equipment --asset tech-core --tech-core-demo --core-motion pose-tour --presentation --seconds 14 --out docs/previews/clean
# For outpost, rune, and dart-station, use ../assets/rm2026-reference.
```

The renderer samples moving geometry to fit the camera around its full travel. The Core pose tour uses fourteen seconds; the other clips use eight seconds. The orbit loops with the joint sweep; eight seconds also contains two complete four-second rail demo cycles. JSON reports retain provenance and motion descriptions outside the image.

`out/` is disposable staging: on 2026-09-11 its accumulated conversion caches, audits, and intermediate renders (about 10 GB) were removed. Original CAD and exported reference packages live in `../assets/`; retained reports and previews live under `docs/`. Rebuild individual intermediates with the commands in the relevant documentation. Clean previews are written here directly, so generating them does not repopulate `out/`. Other concurrent work may create new staging files after cleanup.
