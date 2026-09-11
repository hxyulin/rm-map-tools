# Component refinement, 2026-09-11

The previous simplifier restored every original triangle of a disconnected
component when meshoptimizer collapsed it completely. One shared material can
contain large structures and tiny fittings, so retrying the whole material at a
single tighter tolerance still leaves many small parts at full tessellation.

The revised safeguard retries only missing components, halving the error each
time, for up to twelve passes. Components that remain irreducible retain their
original triangles. It preserves the same error limit and border policy, with no
size filtering, hidden-face deletion, new vertex positions or collision proxies.
The existing sampled-deviation checks still run after component refinement.

Both assets were rebuilt from the unsimplified `out/tolerance-source` package.
The resource-zone energy units were removed before simplification, with the
shafts and sockets kept on the hub. The standalone unit meshes were copied
unchanged from the installed package. Base artwork was removed before mesh
simplification and reattached as the same native texture afterward.

| Asset, per instance | Previous visual | New visual | Previous collision | New collision |
|---|---:|---:|---:|---:|
| Resource zone | 160,836 | 112,591 | 159,088 | 149,571 |
| Base | 78,166 | 60,434 | 85,519 | 69,560 |

Across two instances of each asset, this removes 131,954 visual triangles and
50,952 collision triangles. Resource visual reduction is 30.0%; base visual
reduction is 22.7%. Collision reductions are 6.0% and 18.7%, respectively.
The colliders use the tighter sampled-deviation limit, so they retain more detail.
Counts cover the complete GLBs, including geometry the simulator may distribute
between fixed scenery and mechanism bodies.

## Validation

`validation.json` records the before/after counts and component checks. All 2,888
resource-zone source components and 2,110 base components remain represented in
both visual and collision output. Every output position comes from the source;
no output triangle bridges originally disconnected components.

The 4 mm simplification setting is unchanged. Maximum sampled deviations are
11.930 mm and 11.795 mm for resource/base visuals, below the existing 12 mm limit,
and 7.886 mm and 7.924 mm for their colliders, below the existing 8 mm limit.
These are sampled point-to-triangle checks, not certified Hausdorff bounds.

All four GLBs pass Khronos glTF Validator without errors or warnings. Thirty-four
focused tests pass, including a regression with disconnected fittings at three
scales. The simulator asset inspector accepts the semantic bindings and collision
contracts. Fixed-camera comparisons and a native-texture close-up preserve the
base wordmark and the resource-zone housing artwork.

## Reproduction

From the map-tools repository root, with the unsimplified source and the previous
installed field package available:

```sh
ocpenv/bin/python benchmarks/2026-09-11-component-refinement/build.py
ocpenv/bin/python benchmarks/2026-09-11-component-refinement/validate.py
```

The builder requires a new `out/component-refinement-candidate` directory. It
checks source manifest hashes, generates audited whole-component selections,
and records explicit ranges and hashes in `resource-source-partition.json`.
`select_resource_units.py` is the selection generator for this particular source
assembly; it is not an automatic classifier in the exporter.

Local previews are in `out/component-refinement/resource-comparison.png`,
`out/component-refinement/base-comparison.png`, and
`out/component-refinement-candidate/base-after.png`. CAD and derived images remain
outside Git. The separate standalone units were committed in `4c8a382`; this
benchmark records the subsequent simplifier change.
