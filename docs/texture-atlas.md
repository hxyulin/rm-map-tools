# Texture atlas export

Pass `--texture-atlas path/to/artwork.json` to `export_field_package.py` or
`export_elements.py`. Export jobs accept `"texture_atlas": "artwork.json"` on
field and elements stages, resolved relative to the job file.

Use this option on the last geometry export stage. In the default `sidecar`
mode, consumers must load `texture-atlas.json` and draw its patches. A GLB viewer
alone will show the selected artwork removed. Use `render_mode: "embedded"`
for native glTF rendering, as described below.

```json
{
  "schema_version": 1,
  "pixels_per_metre": 1024,
  "atlas_size": 2048,
  "planarity_tolerance_m": 0.006,
  "merge_distance_m": 0.15,
  "files": {
    "arena-static.glb": [
      {"node": "source_13267048_BREP_161_1", "material": "colour_1.0000,1.0000,1.0000"}
    ]
  }
}
```

Selectors must match exactly one primitive by node and material name. Review
these names against the actual export. Thin geometry alone is not a reliable
artwork selector. Nonplanar selections, duplicates, missing names and oversized
tiles fail the export. Split artwork spanning multiple planes before selecting
it. The earlier audit's numeric primitive indices are not stable export rules.

The exporter groups coplanar selections within `merge_distance_m`, default 0.15 m,
when they share a parent node and material. Set this to zero to keep separate
patches. Grouping respects source spacing, uses shared coordinate axes and stops
before a patch exceeds the atlas tile limit. It does not recognize words; nearby
paint can join a lettering patch too.

Each merged patch has a new anchor under the shared parent, and its `sources`
list identifies the original node/material selections. Independent assembly
parents are never fused. One patch needs one quad. Multiple quads can share a
draw call when the consumer batches compatible atlas materials. Atlas use alone
does not force the consumer to batch. Larger patches may increase texture area
because they include the transparent space between letters.

The exporter projects each patch onto its best-fit plane, rasterizes its
source triangles with 4x supersampling, and packs the result into transparent
RGBA PNG pages. It retains holes and uses the source sRGB colour. Each patch
has a two-pixel transparent gutter. Density is in pixels per node-local metre.
The input exporters use metre coordinates and rigid node transforms.

The JSON sidecar lists page filenames and checksums, pixel rectangles, UV
corners and matching `corners_node_m`. Draw each patch as two triangles using
corner indices `[0, 1, 2, 0, 2, 3]`. Apply the named node's hierarchy and the
asset's manifest placement, including any animated ancestor transforms. UVs
use the PNG top-left origin. Use straight alpha blending and respect
`double_sided`. The plane has no extra depth offset; a consumer can apply its
usual decal depth bias. Mipmaps need a gutter-aware strategy to avoid bleeding.

Selected primitives and their vertex/index buffers are removed from the visual
GLB. Nodes remain as placement anchors. Other geometry and collision files
remain unchanged. Manifest visual checksums, byte counts and triangle counts
are updated. Validation reports describe the original CAD tessellation; the
sidecar records how many triangles were subsequently removed.

Files are selected independently. If using `full-map.glb`, include its own
selectors too. The atlas is not automatically propagated through subsequent
composition, deployment or simplification tools. Retain the PNGs and sidecar
with the converted package. Carried equipment with a separate manifest needs
its own export. Existing textures, skinning and glTF extensions are unsupported.

This is a raster bake of geometry, not OCR or font recovery. It still tessellates
artwork during export; consumers no longer need that tessellated artwork.

## Simplify backing, then embed native textures

Set `"render_mode": "embedded"` to write standard glTF textured quads with UVs,
materials and embedded PNG images. No renderer-specific sidecar loader is needed.
The JSON remains an extraction and simplification report. The default `sidecar`
mode retains the earlier export behavior.

Add a `simplify` object keyed by GLB filename to run backing simplification after
artwork removal and before patch attachment. For example:

```json
"render_mode": "embedded",
"simplify": {
  "arena-static.glb": {
    "error_mm": 4,
    "sampled_limit_mm": 12,
    "deviation_samples": 4096,
    "lock_borders": false,
    "preserve_planar_m": 0.006
  }
}
```

`preserve_planar_m` protects remaining thin planar primitives, including artwork
outside the extraction selection. Omit it when that protection is unnecessary.
Other settings are `simplify_glb` parameters; `preserve` accepts explicit node
and primitive selectors in the stripped geometry. Never simplify an already
simplified input; restore the original source visual before changing tolerances.
Collision files are unchanged by this visual-only pipeline.

Use [the base example](../rules/texture-base.example.json) against a newly created
equipment package containing its unsimplified base visual. Existing field and
element exporters accept these rules through `--texture-atlas`. A prepared copy
of a package can also be processed with:

```sh
ocpenv/bin/python python/texture_atlas.py NEW_PACKAGE rules/texture-base.example.json
```

For a package already stripped and simplified using separate steps, finalize it
with `python/attach_texture_atlas.py PACKAGE`. Do not render both embedded patches
and the sidecar patches, which would duplicate the artwork. The manifest records
`texture_atlas.embedded` and `render_sidecar_required: false`.

Native patches use alpha masking at 0.5, standard PBR materials and linear texture
filtering without mipmaps. `offset_m`, default 0.0005 m, moves patches along their
normal to avoid coplanar depth conflicts. This offset does not conform a patch to
a warped backing panel; inspect the result when relaxing simplification. Large
or distant textures may alias without mipmaps. Atlas-aware mip generation remains
future work. Different patch nodes are not automatically merged into one draw.

Native textures must be attached last. The pipeline does not rebuild backing
surfaces with lettering cut into them, and it fails if extraction invalidates a
bound semantic surface. Semantic node anchors are retained and file hashes are
updated. Run the exporter on a new output package so failed validation cannot
leave an installed package partially modified.

For paint known to face upward, set `"normal_hint": [0, 0, 1]`. Source CAD sheet
winding can point downward even for visible floor paint. The hint chooses the
plane's facing direction; it does not flatten tilted artwork. Its coordinates
are node-local for unmerged selections and parent-local for merged selections.
Patches sit at the frontmost depth of their source artwork, so thickness does
not place them inside the original painted surface.

## Collision artwork removal

Collision cleanup is explicit. Set `collision_simplify` in the atlas rules,
keyed by the visual filename:

```json
"collision_simplify": {
  "arena-static.glb": {
    "error_mm": 4,
    "sampled_limit_mm": 8,
    "deviation_samples": 4096,
    "lock_borders": false
  }
}
```

The exporter resolves the asset's separate collision file, matches the selected
artwork by node and material names, checks planarity, removes those collider
primitives and simplifies the remaining geometry. Visual primitive indices are
never reused as collider indices. A `null` settings value removes the artwork
without further simplification. Missing, duplicate or ambiguous matches fail.
Other collider surfaces remain; no texture quad is added to physics.

Use an unsimplified source collider, even if the visual already has a suitable
export. The exporter refuses to simplify a previously simplified collider again.
The current strict simulator contract expects both visual and collision
simplification metadata, so provide the visual `simplify` block too when building
a new package. Collision methods, checksums, counts and semantic file pins are
updated. Each asset's `collision_artwork_removed` report records the selections,
removed triangles, original checksum and sampled simplification results.
