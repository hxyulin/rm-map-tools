<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# Source CAD components

`python/cad_components.py` divides a source document into editable work selections
without changing geometry. Assembly definitions retain their child occurrences;
each original body becomes a stable component leaf in its product context.
Manual groups organize those leaves. Geometry and full source styles remain
attached to their original identities, independently of group names.

The RMUC 2027 V1.0.0 policy is
[rules/components-rmuc2027.json](../rules/components-rmuc2027.json), pinned to
source SHA `a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0`.
It names all 49 products using source occurrence labels and preserves all 426
body definitions and 644 placed body occurrences. Whole-body layer groups add
annotations to 16 leaves; layers never determine whether a body is retained.

## Initial manual divisions

| Selector | Body definitions | Placed bodies | Grouping basis |
| --- | ---: | ---: | --- |
| `base` | 27 | 54 | Complete source product |
| `base/shields` | 3 | 6 | Three independent `shield-0`, `shield-1`, `shield-2` groups |
| `base/armor-screens` | 3 | 6 | Existing detector-screen source body IDs |
| `base/fixed-other` | 21 | 42 | Other fixed bodies in the reviewed adapter |
| `outpost` | 43 | 86 | Complete source product |
| `outpost/rotor` | 15 | 30 | Three `module-0/1/2` groups of five bodies each |
| `outpost/fixed` | 28 | 56 | Lower (4), column (3), upper (20) and spanning surface-model (1) groups |
| `rune` | 160 | 160 | Ten arm candidates (100), hub clusters (39), spanning surface-model (1), other bodies (20) |
| `dart-station` | 65 | 130 | Original body leaves; internal functions not assigned |
| `resource-area` | 45 | 90 | Original body leaves, retaining combined structure/artwork |
| `floor` | 4 | 4 | Original floor body leaves |
| `centre-platform` | 212 | 260 | Complete source assembly subtree, including nested equipment |

These rows overlap: a subtree contains its nested selections. Counts must not be
added. Whole-body component boundaries do not split screen printing or internal
detail that the CAD fused into a body. `fixed-other` describes the current
simulator motion partition, not proof of complete mechanical immobility.

The catalog has 25 explicit groups. Base and outpost rotor groups use
whole-body IDs from the reviewed simulator bindings. New outpost fixed-region
and rune groups are labeled `spatial-candidate`, not reviewed functional roles.
The pinned region plan must reproduce their exact body memberships before the
catalog accepts them. The three outpost module groups follow the three contiguous five-body
sets around the existing screen bodies #2200540, #2302471 and #2404428; source
part bounds corroborate their separate locations. All share `outpost.spin`.
The base shields retain distinct motion owners. No runtime bindings, collision
exclusions, light masks or artwork policies are changed. See
[non-base spatial candidates](non-base-components-rmuc2027.md) for shell-level
ambiguity and the limits of the mechanical-only arm/module selections.

## Generate a catalog or selection

Run from `rm-map-tools` with the CAD Python environment:

```sh
ocpenv/bin/python python/cad_components.py source/RMUC2027_V1.0.0.stp \
  --policy rules/components-rmuc2027.json \
  --motion-profile rules/reviewed-motion-rmuc2027.json \
  --out out/cad-components/rmuc2027/catalog.json
```

The existing original-source `.npz` parser cache may replace the STEP path. A
catalog records all definitions, original occurrence labels, parent/child
placements, complete occurrence paths, source units and product-to-world
matrices. The RMUC source length unit is millimetres; no normalization, transform
baking or recentering is performed. The policy also pins its product-local region plan by SHA-256; the CLI loads it
relative to the policy file and verifies the pin. Producer, policy and profile hashes identify
the generating code and grouping decisions. Output paths must be new.

Add `--select base/shields/shield-0` to write only that work selection. Valid
selectors are unique product/assembly names, manual group paths/prefixes, or
stable leaf IDs such as `p4774244.b4314593`. Grouping a leaf differently does not
change its ID. Selecting an assembly filters original occurrence ancestry, so
shared definitions placed outside that subtree are not accidentally included.
Selecting a component/group retains all its placed instances.

For a standalone offline inspection page:

```sh
ocpenv/bin/python python/cad_component_browser.py \
  out/cad-components/rmuc2027/catalog.json \
  --out out/cad-components/rmuc2027/catalog.html --initial outpost
```

The page filters by assembly, group, body ID and motion, and shows stable export
selectors and original occurrence paths. It embeds metadata only, not meshes.

## Export an isolated CAD work item

```sh
ocpenv/bin/python python/cad_components.py source/RMUC2027_V1.0.0.stp \
  --policy rules/components-rmuc2027.json \
  --motion-profile rules/reviewed-motion-rmuc2027.json \
  --select base/shields/shield-0 --export-step \
  --out out/cad-components/rmuc2027/base-shield-0
```

This writes `source.step` and `selection.json`. The STEP contains the selected
original bodies in their original product frame, including the source styles.
Its two team placements remain in the sidecar, rather than baking duplicate
geometry into the work item. The sidecar records original source identity,
exported STEP checksum, component IDs, occurrence paths, matrices and units.
A multi-product subtree can be selected as metadata, but STEP work export
requires one product frame; choose a narrower group or leaf for that operation.

The exporter filters representation/layer lists, reparses the result and checks
that the body set is exact, all references resolve, and forward geometry/style
records are byte-identical to their source. It does not import/heal shapes or
approximate surfaces. Importing a work STEP into another CAD kernel is a
separate boundary that may perform healing; source IDs and original STEP remain
authoritative. The original file and installed runtime package are untouched.
Generate work STEP files on demand; do not duplicate the entire source into
hundreds of per-body exports.

## Continue manual separation

Edit `groups` in the pinned policy to give a product's bodies a `path`, explicit
`body_ids`, and `evidence`. Unassigned bodies remain under `other-bodies`; they
are never dropped. Bodies cannot overlap between manual groups, leave their
owning product, or appear in duplicate/prefix-conflicting group paths. Missing
products, invalid source hashes, unresolved placements and incomplete placed
coverage fail the catalog build.

Use the catalog's original occurrence labels and body IDs to review unknown
leaves. Keep uncertain names numeric, as done for two opaque dart-station part
products. Separate bodies into functional groups only when supported by CAD
inspection, existing bindings or an explicit review. Face-level separation of
paint, lighting or fused components needs another reviewed policy and is not
part of this whole-body split.

Tests cover complete coverage, group reorganization without identity/placement
changes, invalid policies, assembly selection of shared definitions, exact STEP
geometry/style preservation, and prevention of accidental output replacement.


Source surface models can contain independently referenced shells, rather than
fused solid geometry. `python/audit_component_regions.py` inventories those
shells and compares their vertex bounds to manual regions. Shell candidates are
not automatically attached to body groups, assigned motion or exported by this
whole-body workflow. Overlaps and straddling shells remain explicit review work.

For complete Rune/Outpost models including surface-container detail, use
[complete CAD partitions](cad-partitions.md). The library exporter also accepts
`shell_ids_by_body` for an explicit source-shell subset and an optional reusable
`Splitter`; it verifies the filtered wrapper plus unchanged shell geometry and
parent/face styles. The ordinary body-only CLI remains unchanged.
