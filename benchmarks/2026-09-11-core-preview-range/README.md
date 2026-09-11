# Technology Core display range update

All six exported documentation display-rig joints now use ±1.2 radians, about
±68.8°, instead of the reference diagnostic range of ±8°. The Python trajectory
solver already used ±1.2 radians; the helper and catalog builder now share that
constant. The display GLB's joint preview metadata and catalog limits agree.

Physical limits remain unknown. The simulator archive still exports six fixed
Core frames. This update changes the movable display rig, not its CAD geometry,
collision, or simulator articulation contract.

[Validation](validation.json) records the old and replacement archive hashes and
checks. Compared with the downloaded release, all GLB binary data and the other
four models are unchanged. The Core scene JSON differs only in its six preview
ranges and their explanatory source strings. Catalog changes are confined to
Core limits, preview labels, notes, and its refreshed file hash/size.

Six model tests cover bound motion/reset, positive and negative range endpoints,
clamping beyond those endpoints, IK beyond the old range, and unreachable targets.
Five viewer tests, three Python trajectory tests, four articulated-export tests,
the site build, and source/built link checks also pass. The packaged ZIP was
extracted and its models passed the same model tests before upload.

In the browser, a larger upward tool drag reached its target with a displayed
0.5 mm residual, with the elbow at 0.623 radians. Reset restored all six axes to
zero. This is a display-motion check, not collision-free or calibrated hardware
validation.

Rebuild a fresh candidate and test it from the repository root:

```sh
ocpenv/bin/python scripts/prepare_viewer_models.py --out out/core-wide-models
VIEWER_MODELS_DIR=out/core-wide-models npm run docs:test-models
ocpenv/bin/python -m unittest discover -s python -p 'test_tech_core_demo.py'
ocpenv/bin/python -m unittest discover -s python -p 'test_export_articulated.py'
npm run docs:test
npm run docs:build
npm run docs:check -- --built
```

The existing asset release is updated with `docs-viewer-models.zip`, refreshed
`SHA256SUMS.txt`, and an amended `validation-summary.json`. The other archives
retain their previous checksums. The previous viewer archive and metadata are
retained locally in `out/core-release-backup`.
