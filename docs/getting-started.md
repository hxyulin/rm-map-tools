# Getting started

[Documentation](README.md) · [Exporting](exporting.md) · [简体中文](zh/getting-started.md)

Run commands from the repository root. Source CAD and generated packages are local files, excluded from Git.

## Download and split

Follow the [README quick start](../README.md#quick-start) to build the Rust CLI, download RMUC V2.0.0, and split it. The source downloader needs Python 3; the CLI requires Rust 1.88+.

The downloader stores files in `source/`. To check an existing download:

```sh
python3 source/download.py verify RMUC2026_V2.0.0.stp
```

`inspect` accepts either a STEP file or a `.p21idx` index. Use the product IDs in the inspection report to select a subset with `split --products <product-id>`. See each command's `--help` for options.

The split package contains `parts/*.stp` and `parts.json`, with source ownership, bounds, face counts, and colors. Keep the original STEP alongside its index.

## Install the CAD environment

The recorded workflow uses Python 3.12 and `cadquery-ocp` 8.0.1. With `uv` installed:

```sh
uv venv ocpenv --python 3.12
uv pip install --python ocpenv/bin/python cadquery-ocp==8.0.1 numpy scipy vtk pillow
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/validate_parts.py out/v20 --mesh
```

Validation checks per-part face counts, bounds, and colors, then tessellates the parts. Results go to `validation.json`; this command does not create a simulator package.

Simplification and simulator formats have additional dependencies listed in their guides.

## Next steps

- [Exporting](exporting.md) explains how to build packages and choose an output format.
- [Simplification](simplification.md) covers geometry reduction and artwork conversion.
- [Reference assets](reference-assets.md) covers semantic packages and joint previews.
- [Previews](previews.md) covers source mesh viewers and plan images.

The full field examples also require a V1.2.0 source and an existing equipment package. Downloading V2.0.0 alone does not supply those inputs.

## Development checks and generated files

```sh
cargo test --workspace --locked
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python -m unittest discover -s python -p 'test_*.py'
```

`out/` holds disposable indexes, split packages, and intermediate renders. Retained reports and previews live in `docs/` and `benchmarks/`. Keep final model packages separately before deleting staging files.
