# Text and markings audit

This study measured the previous locked-border default. The subsequent
[unlocked export](../2026-09-11-unlocked-mesh/README.md) is now deployed.

The deployed simplified package contains 3,018,741 placed visual triangles.
The selected text, logo and painted-line candidates contain 39,829 triangles,
1.32% of that total. Textures remain a useful representation for artwork, but
this selection would make only a small dent in the current triangle count.

| Selection | Placed visual triangles | Matching collider-file triangles |
| --- | ---: | ---: |
| Floor lettering and white markings | 31,824 | 31,824 |
| Coloured boundary candidates | 1,380 | 1,380 |
| Centre lettering | 4,645 | 4,352 |
| Base logo and wordmark, two bases | 1,048 | 1,048 |
| Dart gate logo, two stations | 824 | 824 |
| Rune R artwork, both faces | 108 | 108 |
| Total | 39,829 | 39,536 |

Counts include existing backing and edge triangles where they belong to the
selected lettering. Replacement geometry has not been subtracted. The rune's
black backing disks are excluded. Its light channels and target geometry are
also excluded. Centre logo sheets already absent from collision explain the
293-triangle visual/collider difference.

Collider-file counts are not a measurement of live physics contacts or the
simulator's static hierarchy filter. In particular, the rune is articulated.
No startup, frame-time or physics speedup was measured for a texture conversion.
No textures were deployed and no existing assets or export settings changed.

## Captures and coverage

Open the local gallery at `out/markings-audit/index.html`. It contains an artwork
overview and 57 contact sheets covering all 1,083 placed mesh sections across
the ten asset files. Each section is labelled with its node index, primitive
index and triangle count. `out/markings-audit/report.json` contains the inventory,
PCA bounds, selectors, placements and source checksums. Captures stay local
because they depict the CAD assets.

Every exported section was inventoried and captured. This does **not** establish
that every text fragment has been isolated. Large assemblies contain merged
hardware and can hide small lettering or engraved patterns. Contact sheets
show the major high-cost sections as mechanical assemblies, but cannot certify
that they contain no artwork. Thinness and colour alone do not establish that
geometry can be removed from physics. The coloured boundary set is explicitly
a candidate set, and the white floor set includes paint shapes as well as text.

The initial geometric scan used a 3 mm PCA thickness threshold. Final selections
came from visual inspection, existing logo names and the source mesh structure;
coloured boundary candidates use a 6 mm threshold. Neither threshold changes
the exported geometry. Artwork across different planes can fail a whole-mesh
thinness test, which is why the complete inventory is captured too.

The selected set spans 389 mesh sections before outer asset placements. Combining
artwork into a few textures might reduce render submissions as well as triangles,
but these sections are not measured GPU draw calls. Texture resolution, alpha
filtering and atlas grouping still need an actual prototype and benchmark.

## Larger remaining costs

These individual mixed mechanical sections alone total 1,511,086 placed triangles,
50.1% of the scene. Their counts are not estimates of removable geometry.

| Section | Per asset | Placed count |
| --- | ---: | ---: |
| Resource zone, node 1 primitive 1 | 335,459 | 670,918 |
| Dart station, node 1 primitive 5 | 168,320 | 336,640 |
| Base, node 1 primitive 1 | 154,049 | 308,098 |
| Dart station, node 2 primitive 0 | 97,715 | 195,430 |

For startup work, identifying dispensable internal mechanical detail in these
assemblies looks more promising than replacing the currently isolated artwork.

## Reproduce

Run from the map-tools repository with the existing geometry environment:

```sh
ocpenv/bin/python benchmarks/2026-09-11-markings-audit/audit.py ../rm-simulator/local-assets/field out/markings-audit
```

`baseline.json` pins the inspected visual and collider files. The audit refuses
changed inputs because its reviewed selectors must be checked again against new
geometry. Counts traverse the selected glTF scene, excluding unused meshes, and
apply the manifest's arena placements. Arena-static and floor have empty placement
lists and are loaded once. Collider matches use node name and material name;
ambiguous matches fail rather than silently reusing visual triangle indices.

Validation: the visual inventory reconciles exactly to the previous deployed
baseline of 3,018,741 triangles. All contact sheets were generated successfully;
major sections, representative small sections and the artwork overview were
visually inspected. Python compilation and whitespace checks passed.
