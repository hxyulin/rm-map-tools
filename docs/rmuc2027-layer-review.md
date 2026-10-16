<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!-- Copyright (c) 2026 hxyulin <hxyulin@proton.me> -->
# RMUC 2027 layer qualification review

This is a source/evidence review, not an applied export policy. It changes no
geometry, face styles, runtime bindings or collisions. Source SHA-256:
`a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0`.

## First reviewed qualifications

| Selection | Evidence | Qualification |
| --- | --- | --- |
| `ARMOR_LIGHT_GUIDE_STRIP-V1_1`, its suffix variant and LED names | One shared group spans 42 outpost bodies: 15 moving module bodies and 27 fixed bodies in the existing adapter | Reject as individual light masks and as one rigid batch. Retain names as provenance. |
| `LIGHT_ARMOR_BACK_SHELL` | 733 faces of base body #4774151, which has 4,555 faces total; one additional styled-item reference | Candidate partial face selector. It is not a standalone shell body. Appearance control, surface function and collision exclusion remain unqualified. |
| `COLOR132` | 19 faces within the same base body; one effective RGB value | Candidate color-region selector only. No evidence that it is paint, lighting or collision-free. |
| `COLOR72` | 24 faces within the same base body; one effective RGB value | Same limitation as `COLOR132`; retain the source face selection for later visual review. |
| `COLOR61_2` | 65 dart-station bodies with multiple effective RGB values | Reject as a single material/color mask or component selector. Motion remains unknown. |
| Complete single-body groups | 16 distinct lists completely cover one source body each | Qualify the geometric scope as a component selector. Function, motion and appearance control are separate questions. |
| Occurrence names containing `带丝印` | Floor, central-highland deck, red/blue trapezoidal highlands and resource-area assemblies combine structure and artwork | Keep as mixed assembly candidates. The label does not identify removable artwork faces. |

Across 259 exact membership groups: 98 span multiple bodies, 145 select partial
single bodies and 16 cover complete single bodies. Seven groups cross the
reviewed fixed/moving boundary. Of 109 `COLOR…` layers, 96 include multiple
known effective RGB values. The other 13 are not thereby proven material masks.
RGB diagnostics use the typed model's four-decimal colors and body/shell fallback;
original full style records remain authoritative. Unknown colors are counted
separately, not treated as matching colors.

## Reviewed motion context

[rules/reviewed-motion-rmuc2027.json](../rules/reviewed-motion-rmuc2027.json)
records explicit product/body IDs, source SHA and evidence from the already
reviewed simulator adapter `scripts/bind-rmuc2027-structures.py`. The evidence
includes that script's hash. This is independent simulation knowledge, not STEP
kinematics or a claim of complete mechanical motion support.

- Outpost product #2603236: 15 bodies under `outpost.spin`, 28 fixed bodies.
- Base product #4774244: three shield bodies under independent
  `base.armor.0/1/2` owners, 24 fixed bodies.
- All other motion remains unknown in this initial profile.

Assignments apply to every occurrence of the specified product in the existing
adapter. Source occurrence paths still distinguish placed instances; a matching
motion-owner name is not permission to merge different placed entities. The
reviewer rejects wrong source hashes, unknown owners, duplicate/conflicting
body assignments and missing evidence. No motion or collision policy is inferred
from a missing assignment.

## Useful component selectors to review next

Whole-body coverage provides useful candidates even where layer names are opaque:

| Source body | Assembly occurrence label | Next review |
| --- | --- | --- |
| #1781935 | 中央高地_地面带丝印 | Separate structural faces from artwork candidates within this body. |
| #2643575 / #3776011 | 梯形高地带丝印_红方 / 蓝方 | Compare red/blue structure and painted faces; preserve side-specific appearance. |
| #1791020 / #1800009 | 中央高地_侧边隧道挡边 / 红 | Confirm structural scope and any face-level paint. |
| #2615732 / #2624811 | 高地下风机铁网 / 隧道旁风机铁网 | Inspect grille geometry without deleting it or assuming an artwork role. |
| #2717086 | 风机 | Confirm which internal parts, if any, should move; the source grouping alone cannot decide. |
| #4069550 | 基地_底座 | Inspect structural scope independently of the base equipment motion partition. |

Start visual review with the base's two small color regions and rear-shell
selection, then one screen-printed deck. Rendering a complete body is insufficient
for accepting a partial-face mask: preserve source face identity through targeted
tessellation or an explicit correspondence before generating those overlays.

## Reproduce

From the producer repository:

```sh
ocpenv/bin/python python/review_cad_layers.py \
  source/RMUC2027_V1.0.0.stp \
  --profile rules/reviewed-motion-rmuc2027.json \
  --out out/cad-audit/rmuc2027-layer-review.json
```

An optional original-source parser cache may replace the STEP path. Output paths
must be new. The report includes all original layer names/IDs, exact source body
coverage, occurrence labels, motion-owner counts, color diagnostics, evidence
profile and producer hashes. It verifies the original source hash after analysis.

Tests cover partial versus complete face coverage, unknown motion, mixed moving
and fixed bodies, misleading color names and stale/conflicting review profiles.
