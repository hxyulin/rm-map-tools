# Collision artwork removal and backing simplification

The installed native-texture package now also omits the selected artwork from
physics. Visual GLBs are byte-identical to the preceding native-texture package.

| Actual simulator static collider triangles | Before | After |
| --- | ---: | ---: |
| Ground | 673,660 | 575,589 |
| Fixtures | 43,780 | 43,780 |
| Equipment | 209,588 | 209,460 |
| Total | 927,028 | 828,829 |

This removes 98,199 static collider triangles, 10.59%. The source arena collider
falls from 108,268 to 10,197 triangles. Base falls from 85,583 to 85,519 per
instance. The base's lettering was already heavily simplified in collision.

The 243 extracted arena selections match 16,210 collider triangles; the base
wordmark matches 524 unsimplified source triangles. Matching uses node and
material names independently of visual primitive indices. All matches were
unique and planar within 6 mm. Source nodes and semantic bindings remain.

Arena starts from its unsimplified collider, including the earlier road-wordmark
composition. Base starts from the pinned original collider in
`out/tolerance-source`, avoiding cumulative simplification. Both use a 4 mm
metric, 8 mm sampled limit, 4,096 samples per direction and unlocked borders.
Remaining planar arena primitives up to 6 mm thick are preserved.

A 19,400-ray ground probe compares stripped arena geometry with its simplified
result. There are no hit/miss changes; 11,754 rays hit both. The maximum sampled
height difference is 4.978 mm and the 99th percentile is 1.486 mm. This isolates
simplification from the intentional deletion of artwork surfaces, which can
otherwise create apparent ground hits. These samples are not a maximum-error
certificate. The simulator's asset inspector accepts the new checksums,
semantic sidecars and collision simplification contracts.

The exporter accepts an optional `collision_simplify` block in texture-atlas
rules. It removes only explicitly selected artwork and never inserts texture
quads in physics. See [texture atlas export](../../docs/texture-atlas.md).
The 29 focused Python tests pass, including shared-mesh isolation, solid
rejection, selector ambiguity and combined visual/collision export ordering.
No physics step-time improvement has been measured.

`build.py` produces `out/collision-artwork-candidate` from the installed
native-texture package and archived source; its output must be new. `validate.py`
compares that candidate with the pre-installation package. After installation,
point its `before` path at the retained package backup to reproduce the check.
Run both with `PYTHONPATH=python ocpenv/bin/python` from the repository root.
