<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 source appearance and complete equipment compositions

This review uses the original `RMUC2027_V1.0.0.stp`, SHA-256
`a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0`.
Strange colors are not sufficient evidence that an exporter lost a style.

## Which colors actually come from CAD?

The Technology Core product #1751926, body #1751911, has 4,892 source faces,
**all with explicit face-level surface colors**. The source palette includes dark
gray, copper/brown, green, pale green, teal, purple, gold, white and red. The native
STEP reader and GLB reproduce that palette; these colors are not generated debug
colors. No absent parent assembly color explains them.

The source styles target faces, solids, shells and curves. No `STYLED_ITEM` in
this file targets an assembly product, representation or occurrence. Thus there
is no missing assembly-parent surface color to inherit in this source. Face
colors still override shell and solid colors, which are used where present.
This is a finding about this particular CAD release, not a claim about all STEP.

| Product | Surface appearance evidence |
| --- | --- |
| Technology Core #1751926 | 4,892 explicitly colored faces, no fallback |
| Fan frame 1 #2650147 | Nine faces inherit near-black from body #2650124; two are explicitly cyan |
| Fan frame 2 #4070010 | Ten faces inherit near-black from body #4069987; one is explicitly cyan |
| Fan #2717102 | All 1,607 faces lack surface fill color; neutral gray fallback |
| Base footing #4069592 | 183 of 243 faces lack surface fill color; the other 60 have original colors |

The black/cyan structures are original fan frames (`1号风机框`, `2号风机框`),
not procedural markers. Frame 1 belongs to each high-point assembly; frame 2
is placed directly under the arena root. Their surface colors are CAD authoring
colors, which need not represent the equipment's real finish. Fans, grilles,
drone pads and isolated Outpost/Base footings also appeared separately in the
previous terrain-only overview because the main equipment was excluded there.
Drone pads are #1754789, Outpost footings #1800898 and Base footings #4069592.
These identities do not establish a gameplay buff or RFID role.

The GLB exporter now explicitly records `step_colour_origin: source|fallback`.
An unstyled fallback has `step_colour_srgb: null`; its visible neutral gray still
lives in the normal glTF base-color factor. Explicit source gray remains a
separate material, even if it looks identical. Preview lighting is illustrative;
these previews do not add emissive LED materials or reconstruct real finishes.

## Complete export boundaries

The [composition policy](../rules/compositions-rmuc2027.json) adds ten reproducible
compositions, retaining exact original product geometry, styles and placements:

- Red/blue Dart stations use original parents #3757401 / #3782100: mechanism,
  timber walls/roof and both ancillary products.
- Red/blue high points use parents #2717147 / #3782015: lower/upper terrain,
  fan frame 1 and two fans.
- Each Base is explicitly paired with its underlying footing. These are root
  siblings, not an existing source Base assembly. The remote fan frame 2 is
  excluded rather than attached merely because it is another root sibling.
- Each Outpost is paired with its footing, both original central-platform siblings.
- Red/blue resource zones use parents #4056313 / #4056432: resource equipment
  and all six energy units per side.

`python/cad_composition.py` collapses per-body catalog rows into whole-product
occurrences, selects original subtrees or exact occurrence paths, and rejects
missing, ambiguous or duplicate paths. Shared definitions placed elsewhere do
not leak into a subtree selection. The STEP export copies source geometry and
styles with the existing exact closure exporter and appends a synthetic placing
root. This wrapper is an export boundary, not a new mechanical/motion claim.
GLB retains instance nodes, source product IDs and occurrence paths. Both formats
use a translated local origin; only GLB converts millimetres to metres and Z-up
to Y-up. Read-back face counts and STEP/GLB bounds validate composition placement.
The ten reviewed exports differ by less than 0.005 mm at their STEP/GLB bounding
box limits; this is an envelope check, not a surface-deviation measurement.
Base/Outpost recipes additionally require at least 90% of the tower footprint
to overlap the footing and its bottom to lie within 50 mm of the footing top.
This validates selection, not geometry approximation. The Outpost siblings are
listed in opposite orders: positive-x Outpost occurrence #2603254 pairs with
footing #1800903; negative-x #2603241 pairs with #1800916.

## Comparison with secondary fixtures hidden

The comparison removes only these product IDs from the same placed terrain
subset: drone pad #1754789, grilles #2615748 / #2624828, fan frames #2650147 /
#4070010 and fan #2717102. This removes no source data. The inspection selection
is not an official CAD layer, a simplification policy or a collision exclusion.
Footings, walls, roofs, every terrain body and marking remain. Both comparison
images share the same orthographic camera and framing; a third view shows only
what was hidden. A full-field view supplies context for the isolated fixtures.
At the review tessellation the terrain subset has 662,976 placed triangles;
413,444 belong to the hidden fixtures, leaving 249,532 visible. The ten fan
instances alone account for 406,660. These are inspection counts, not a runtime
package change. All 32 whole-product definitions retain their 110,586 source
faces in native read-back.

## Reproduce and clean

From `rm-map-tools`, after installing the usual OCP environment plus Pillow:

```sh
mkdir -p out/terrain-review
ocpenv/bin/python benchmarks/2026-10-17-terrain-separation/inventory.py
ocpenv/bin/python benchmarks/2026-10-17-terrain-separation/appearance-review.py
ocpenv/bin/python benchmarks/2026-10-17-terrain-separation/verify-appearance-review.py
ocpenv/bin/python benchmarks/2026-10-17-terrain-separation/build-review-page.py
```

The second script exports all body-owning product definitions, audits original
face/shell/body styles, builds the ten complete compositions, reads their STEP
files back, and renders the comparisons and close-ups with per-pixel depth.
Its disposable outputs live in `out/appearance-review-v2`. Preserve the original
STEP, scripts and policies; generated STEP/GLB, indexes, images and the local
Python environment can be deleted after visual review. No runtime package changes.
