# Wall and elevated decoration layer

The reviewed centre-platform wordmarks, dart gate logos and rune face logos
now carry `decoration` layer metadata. Lettering has `kind: text`; symbols have
`kind: logo`. The two elevated circle-and-slash deck markings have
`kind: symbol`. The visual vertex coordinates, triangle indices, materials and
transforms are unchanged. The layer is an exported primitive classification
and sidecar inventory, not a new simulator UI toggle.

| Asset | Collider triangles removed per asset | Placements | Placed removal |
| --- | ---: | ---: | ---: |
| Centre platform | 4,928 | 1 | 4,928 |
| Dart station | 43 | 2 | 86 |
| Rune | 33 | 1 | 33 |
| Total | | | 5,047 |

The current dart and rune colliders were already simplified. Their remaining
geometry is preserved exactly; no second simplification pass runs. Centre logo
sheets already absent from collision are explicitly recorded and checked.
The multi-plane logo sheets stay as their original visual geometry.

The follow-up screenshot exposed a missed primitive in the centre platform
main mesh. Its white primitive contains both circle-and-slash deck markings,
148 triangles total. An isolated render confirmed the selection. The backing correction below
removes the remaining collision outlines.

The package classifier uses exact node and material names from the earlier
markings audit, checked against the current package. It rejects missing,
ambiguous and duplicate selections. Existing floor/base texture extraction is
unchanged. No height or colour heuristic removes geometry.

Validation compares the complete visual triangle set against the input with
exact equality. Collider triangles outside the explicit removal and deck
repair are also identical.
Manifest hashes and all semantic bindings pass. The simulator's
`inspect_assets` accepts the candidate. All 24 focused classifier, collision,
semantic and simplification tests pass.

Build with the command in the root README, then validate with:

```sh
PYTHONPATH=python ocpenv/bin/python benchmarks/2026-09-11-decoration-layer/validate.py SOURCE OUTPUT
../rm-simulator/target/debug/examples/inspect_assets OUTPUT
```

## Symbol backing correction

The first symbol pass removed white caps but missed 288 grey sidewall triangles
inside the main platform primitive. The old deck triangulation also retained
the circle-and-slash outlines. The final repair partitions the sidewalls into a
visible decoration child and removes them from collision. It fills the symbol
footprints at the original 0.4 m deck height and replaces 156 imprinted deck
triangles with 16 triangles following the deck boundary. Real boundary holes
remain. This removes another 428 collider triangles, 5,047 total for the layer.

The repair pins the sidewall, cap and deck geometry hashes, and uses reviewed
triangle ranges for the sidewalls. Boundary vertices are welded at 1 micrometre.
It checks closed boundaries, nonmanifold edges, triangulation success and area.
Tests cover disappearing internal edges, retained physical holes and rejection
of duplicate faces. A 50,851-point deck coverage comparison found no changes
against the original deck plus flattened symbol footprints. An isolated
before/after collider render confirms that the symbol outlines are gone.
The simulator collision loader reports 578,031 ground triangles, down from
578,459 before the backing correction.
