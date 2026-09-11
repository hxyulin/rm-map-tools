# Field composition and decorations

[Documentation](README.md) · [Simplification](simplification.md)

These operations use reviewed source selections. Run them on the matching package before geometry changes invalidate those selections.

## Grafted road wordmarks

`python/compose_road_markings.py SOURCE OUTPUT` composes the V1.2.0 field with
its grafted V2 bumpy roads by omitting two reviewed duplicate ROBOMASTER
wordmarks beneath the roads. It retains the other wordmarks and all terrain.
The same 30 exact source nodes are omitted from the visual and collision
scenes, with updated checksums and a `road-marking-composition.json` report.
The source is retained and the output directory must not exist. This is a
composition decision based on RMUC 2026 V2.1.0 Figure 4-36, not a change to the
source CAD or an automatic removal of thin/coloured geometry.

```sh
ocpenv/bin/python python/compose_road_markings.py SOURCE OUTPUT
PYTHONPATH=python ocpenv/bin/python -m unittest test_compose_road_markings
```

## Wall and elevated decorations

Wall-mounted and elevated lettering can be classified with the reviewed V1.2.0
rules. This keeps the original visual primitives, tags them with
`extras.rm.layer = "decoration"` and `kind = "text"`, `"logo"` or `"symbol"`, and removes
their matching collider primitives. The centre deck repair also separates the
symbol sidewalls and restores flat collision backing at the original deck
height, removing the symbol outlines from its triangulation. The layer is
visible by default and listed in `decoration-layer.json`. It does not depend on elevation, orientation
or material colour alone. The simulator reads the resulting collision files;
this export does not add an in-app visibility control.

```sh
PYTHONPATH=python ocpenv/bin/python python/classify_decorations.py SOURCE OUTPUT --rules rules/decorations-v1.2.0.json
PYTHONPATH=python ocpenv/bin/python -m unittest test_classify_decorations test_collision_artwork
```

The rules cover both centre-platform wall wordmarks and circle-and-slash deck
markings, the dart gate logos and the rune face logos. They retain walls, platforms and logo backing disks.
Output must be a new directory; source packages remain intact.
