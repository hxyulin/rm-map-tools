# Atlas removal followed by simplification

Compared against the installed `../rm-simulator/local-assets/field` package,
including its removal of two obsolete road wordmarks. This uses the 243 selected
planar arena artwork sections from the grouped atlas preview, not every marking
in the equipment assets.

| Placed visual triangles | Count |
| --- | ---: |
| Currently installed | 1,172,056 |
| Atlas removal followed by the installed simplifier preset | 1,155,846 |
| Texture replacement quads, 77 patches | 154 |
| Combined candidate rendering geometry | 1,156,000 |
| Net reduction | 16,056, or 1.37% |

The full simplifier was rerun from the installed run's unsimplified source.
Input hashes for every simplified visual and collider matched the archived
installed run. Pass-through terrain files were copied from the current package
to include the recent road-wordmark composition. Atlas removal ran before
simplification. The installed preset disables simplification for arena-static,
so this selection adds no further edge-collapse savings.

All other visual GLBs and all collision GLBs are byte-identical to the installed
package. Atlas sidecar and PNG checksums were verified after simplification.
The 16,210 removed artwork triangles become 154 quad triangles. Counts include
asset placements and selected-scene traversal, not GPU culling or draw calls.
The simulator package was not changed and no runtime speedup was measured.

`comparison.json` records asset counts and checksums. `run.log` records the full
simplifier output. Local candidate: `out/atlas-simplification-comparison/simplified`.
`compare.py` reproduces the run from the repository root with `PYTHONPATH=python`
and `ocpenv/bin/python`; its output directory must be absent. It depends on the
local grouped atlas rules and archived source named in the installed report.
