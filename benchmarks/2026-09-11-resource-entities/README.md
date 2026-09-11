# Resource-zone entity extraction, 2026-09-11

## Standalone STEP correction

The initial extraction below incorrectly included inserted support shafts and
turquoise socket faces. The corrected build returns 981 visual and 981 collision
triangles per zone to the hub. Six hollow units now share one visual mesh and one
collider derived from `UTF-8__能量单元.stp`. All twelve placements preserve the
original centers and orient the shared mesh along the six radial mounting axes.

The standalone unit is 150 mm long and has a 95 mm maximum diameter. Its fine
reference tessellation has 18,646 triangles. Simplifying with a 0.25 mm error
setting produces 4,157 triangles, with 0.607 mm maximum sampled deviation from
the reference tessellation, below the 0.75 mm limit. This is a sampled check,
not a certified bound against the analytic STEP. The STEP colors are retained.

The corrected resource-zone mesh contains 160,836 visual and 159,088 collision
triangles, including its shafts. With six reference units, those totals become
185,778 visual and 184,030 collision triangles per zone. This increases triangles
over the initial coarse units in exchange for faithful standalone geometry.
All units reuse the same loaded mesh and material assets.

`build_reference_units.py` takes the original pre-extraction package, audited
selection JSON, standalone STEP, and a new output directory. It verifies triangle
conservation after correcting ownership, then substitutes the standalone units.
`energy-unit-reference.json` in the output records the source checksum, settings,
error measurements and the corrected partition validation. All four distinct
changed GLBs pass glTF validation without errors or warnings.

The corrected preview is `out/resource-unit-audit/reference-exploded.png`; it
shows the rods staying on the hub. The output is `out/resource-reference-candidate`.

## Initial extraction, superseded by the correction


Six energy units were extracted per resource zone, giving twelve placed entities
across the field. Each has a separate visual GLB, collision GLB, and local origin.
The existing simulator static-asset path loads them without a code change. They
remain static; individual dynamic rigid bodies are deferred by user request.

| Geometry per zone | Before | Remaining zone | Separate units |
|---|---:|---:|---:|
| Visual triangles | 167,914 | 159,855 | 8,059 |
| Collision triangles | 168,125 | 158,107 | 10,018 |

This is a partition, so total visual and collision counts do not change. Units
range from 1,319 to 1,366 visual triangles and 1,647 to 1,697 collision triangles.
They retain their own tessellations rather than approximating all six with one
unit mesh. Their differing triangle counts come from the prior simplification.

## Selection and validation

Whole connected components were audited in the current visual and collision
GLBs independently. The six radial assemblies include end caps, beige bodies,
inner caps and fittings. The central hub and its sockets remain in the zone.
An exploded preview confirms complete units and the exposed sockets. The local
selection record contains exact input SHA-256 pins and explicit triangle ranges;
no geometric heuristic runs in the production extractor.

Local artifacts, excluded from Git because they contain derived CAD:

- `out/resource-unit-audit/rules.json`: audited selections.
- `out/resource-unit-audit/exploded.png`: assembled and separated preview.
- `out/resource-entities-candidate/`: complete output package.
- `out/resource-unit-audit/inspect.log`: simulator asset inspection.

Rebuild with the original package or the installation backup as input:

```sh
ocpenv/bin/python python/extract_entities.py INPUT_PACKAGE \
  --rules out/resource-unit-audit/rules.json --out NEW_OUTPUT_PACKAGE
ocpenv/bin/python benchmarks/2026-09-11-resource-entities/validate.py \
  INPUT_PACKAGE NEW_OUTPUT_PACKAGE
```

`validation.json` records triangle/material multiset equality, preserving winding
and duplicate counts. Coordinates match to ten decimal places after restoring
entity origins. Both field placements match matrix composition to 1e-12 metres.
All fourteen changed GLBs pass Khronos glTF Validator with zero errors and
warnings. The simulator inspector accepts the package and retains the previous
828,829 total physics triangles. Four extraction tests exercise shared meshes,
transforms, partial selection, invalid ranges, overlap, checksum failure and
package placement. Export-job tests cover the optional `entities` stage.

## Further simplification candidates

Current placed visual costs before this partition:

| Asset | Triangles per asset | Instances | Placed triangles |
|---|---:|---:|---:|
| Resource zone | 167,914 | 2 | 335,828 |
| Dart station | 90,904 | 2 | 181,808 |
| Base | 78,166 | 2 | 156,332 |

The resource-zone rear region, triangles entirely beyond local x = 0.7 m,
contains 65,388 triangles per zone. Many are connectors, electronics and internal
mechanical details behind the enclosure. This is a spatial inventory, not an
occlusion proof or an estimate of removable triangles. Audit enclosure visibility
and service openings before deleting any of it.

The resource-zone silver assembly group alone contains 115,176 triangles. Its
parts need semantic separation before applying different detail policies. The
protected yellow logo housing has another 10,412 triangles; removing its embossed
artwork into a texture would require separating that artwork from the housing.

The base's largest silver assembly group contains 35,660 of its 78,166 triangles.
It is the next base-specific audit target. Moving shields and target surfaces
must retain their current semantic membership. No additional base geometry was
removed in this pass, and no unverified concealed surfaces were deleted.
