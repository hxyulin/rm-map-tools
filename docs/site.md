# Documentation site

[Documentation](README.md) · [Interactive viewer](viewer.md)

The site uses VitePress. Guides remain ordinary Markdown in `docs/`, readable on GitHub, with a Vue component for interactive model inspection. There is no separate copy of the documentation to maintain. The lockfile pins VitePress 1.6.4 with a Vite 6.4.3 override to use the patched development server.

## Run locally

Install Node.js 22 or later, then run from the repository root:

```sh
npm ci
npm run docs:models
npm run docs:dev
```

Open the address printed by VitePress, under `/rm-map-tools/`. To check and build:

```sh
npm run docs:check
npm run docs:test
npm run docs:build
npm run docs:check -- --built
npm run docs:preview
```

The build goes to `docs/.vitepress/dist/`. Dependencies and build output are ignored by Git. Python and Rust are not needed to run the viewer; the link checker uses Python 3.

## Publish to GitHub Pages

In repository Settings → Pages, select **GitHub Actions** as the build source. The documentation workflow builds pull requests and publishes pushes to `main`, or a manual workflow run. The expected project URL is `https://hxyulin.github.io/rm-map-tools/` once the workflow has deployed successfully.

For a fork, change the repository links and `base` in `docs/.vitepress/config.mjs`. The base must match the GitHub Pages repository path. See [VitePress deployment](https://vitepress.dev/guide/deploy).

## Edit the docs

Keep the README focused on what the project does and how to start. Put procedures in the main guides, settings in technical references, and measured results in dated benchmark reports. Add new guides to the documentation index and sidebar.

Repository links outside `docs/` are rewritten to GitHub when building the site. Markdown keeps its original relative paths for repository browsing. The viewer component is registered by the theme; a page can embed it with `<ModelViewer />`. It mounts only in the browser, keeping static builds independent of WebGL.

## Models and motion

The viewer uses Three.js and URDFLoader. Its SDF adapter accepts the equipment structure emitted by this repository's articulated exporter. It does not implement a simulator or replace SDF frame semantics generally.

The catalog contains Base, Power Rune, Outpost, Dart station, and Technology Core CAD models, with controls for every bound movable entity. Generate it from the existing reference package:

```sh
npm run docs:models
npm run docs:test-models
```

This uses the `ocpenv` Python environment and `../assets/rm2026-reference`. A different source can be supplied to `scripts/prepare_viewer_models.py --source PATH`. The output is `docs/public/models/`, which must not already exist. To rebuild, remove that generated directory or choose a fresh output with `--out`.

The builder verifies each source GLB against its semantic sidecar, preserves the motion-node hierarchy, and creates a separate Core display rig using the existing rig helper. It writes gzip-compressed GLBs and a catalog of names, joint ranges, source hashes, and output hashes. The browser verifies the decompressed model hash before binding joints. The bundle is about 60 MB; each model downloads only when selected.

Models stay outside Git. To supply the same bundle to GitHub Pages, create an archive and host it at a downloadable artifact URL:

```sh
mkdir -p out
python3 -m zipfile -c out/docs-viewer-models.zip docs/public/models
```

Set the repository Actions variable `DOCS_MODELS_URL` to that archive URL. The documentation workflow downloads it into `docs/public/`, tests all five models, and includes it in the Pages artifact. Publishing requires the bundle; the workflow will not deploy a viewer with missing catalog models. Pull requests can still build the Markdown without the bundle. The generated archive retains DJI / RoboMaster geometry ownership and terms.

Recorded GIF/MP4 files and standalone frame/video capture scripts have been removed. Numerical motion verification, source audit reports, and reusable joint/rig helpers remain available. Existing static geometry comparison images are retained as evidence.
