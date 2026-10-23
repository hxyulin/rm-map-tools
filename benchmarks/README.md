# Benchmark tools

Old reports, result JSON, logs and obsolete local trial directories have been
removed. Historical result artifacts are intentionally excluded from repository history.

`2026-10-24-source-motion/` is the active source-motion review and qualification
workflow. The canonical pass and ownership policy live in `python/cad_motion.py`
and `rules/source-motion-rmuc2027.json`.

Remaining older Python/Rust/C++ files are executable experiment tools, including
helpers imported by regression tests and render utilities. They are retained as
source code; cached experiment outputs are not retained.
