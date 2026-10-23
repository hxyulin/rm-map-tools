<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 source baseline

Restart decision, 2026-10-24: use the **stage-one hierarchical source STEP** as
the CAD authority. Earlier simplified meshes and manual approximations remain
historical experiments, not inputs to this baseline. Installed simulator assets
remain unchanged and can serve as a separate runtime comparison.

## Baseline

- Original: `source/RMUC2027_V1.0.0.stp`.
- Original SHA-256: `a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0`.
- Local CAD: `out/rmuc2027-hierarchy/field.step`.
- Identity and preservation evidence: `out/rmuc2027-hierarchy/hierarchy.json`.
- Native read-back evidence: `out/rmuc2027-hierarchy/native-validation.json`.

The source hash and package payload checksums were rechecked on 2026-10-24.
The saved native check reports one root assembly and 214,794 placed faces.
It was not rerun for this cleanup. The package retains 110,586 unique source
face definitions across 116 work-part definitions, with 644 placed source bodies.
CAD faces are trimmed analytic surfaces, not triangle counts.

## What the pipeline actually does

1. **Parse/index the original STEP.** Read entity records, references, products,
   appearances and placements. An index is a lookup cache, not a mesh.
2. **Organize reviewed bodies/shells into named work parts.**
   `python/cad_hierarchy.py` writes a new STEP assembly. Geometry and topology
   records retain their original IDs and exact bytes. Wrappers, product names
   and assembly structure change intentionally; original world placements and
   appearance records are checked. No healing, Boolean operations, hole closure,
   curve fitting or tessellation occurs in the writer.
3. **Optionally inspect/share exact data.** Read-only audits change nothing;
   exact interning/sharing targets storage and reuse, not shape detail. Additional
   value/style-sharing rewrites are not applied to the stage-one package.
4. **Tessellate for runtime.** Analytic CAD becomes triangles. This introduces
   approximation controlled by linear/angular meshing settings and the CAD
   importer. OCCT may heal/split imported geometry; native face ordinals are not
   original STEP face IDs. Source appearance preservation does not guarantee
   complete color/material recovery by every importer.
5. **Apply optional runtime simplifications.** Edge collapse, detail deletion,
   hole filling, texture substitution and fitted collision primitives can change
   shape or appearance. Their error checks and approvals are separate from
   stage-one preservation. They are excluded from this starting point.

The hierarchy is organizational, not a complete articulated simulator model.
Joints, contact roles, lights and scoring bindings still need explicit handling.
The existing runtime exporters consume original STEP and their own policies;
there is not yet a complete hierarchy-to-runtime adapter. Do not assume exporting
an old runtime configuration automatically starts from this clean hierarchy.

## Next work boundary

Use one reproducible, unsimplified tessellation of this source as the visual
reference, with recorded meshing settings and source correspondence. Compare
imported appearance against the CAD before accepting that mesh reference.
Derive visual and collision candidates independently from the reference, rather
than repeatedly simplifying previous candidates. Keep geometry-changing passes
explicit and off by default while establishing the reference.

See [hierarchy implementation and reproduction](cad-hierarchy.md) and
[the separate runtime simplification stages](simplification.md).

## Motion-prepared successor

The next accepted preparation step is [source motion ownership](cad-source-motion.md),
which now runs before hierarchy construction. Its separate output is
`out/rmuc2027-hierarchy-motion-reviewed/field.step`. It preserves the original
face geometry and placements while correcting work groups. Outpost body #2101579
is split into original open face patches with private wrappers; no new faces
or shape approximation are introduced. The earlier package above is retained.

The successor has passed full native read-back: 124 component definitions,
185 placed component uses, 110,586 unique source faces and 214,794 placed faces,
with unchanged field bounds. Use it for the next source-hierarchy stage; retain
this document's original package as the pre-motion comparison.
