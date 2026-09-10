# Getting started / 使用指南

[English README](../README.md) · [中文 README](../README.zh-CN.md)

Run commands from the repository root. The Rust-only workflow can be used without Python CAD dependencies. Later stages require the source files and packages named in their configuration; they are not bundled with the repository.

从仓库根目录执行。仅使用 Rust 拆分时无需安装 Python CAD 依赖。后续步骤需要配置中指定的源文件和资源包，仓库不附带这些模型。

## Split and inspect / 拆分与检查

```sh
cargo build --release --locked
python3 source/download.py fetch RMUC2026_V2.0.0.stp
python3 source/download.py verify RMUC2026_V2.0.0.stp
mkdir -p out

target/release/rm-map-tools index source/RMUC2026_V2.0.0.stp -o out/v20.p21idx
target/release/rm-map-tools inspect out/v20.p21idx --json out/v20-inspection.json
target/release/rm-map-tools split out/v20.p21idx -o out/v20
```

Use `split --products <product-id>` for a subset. Inspect accepts a source STEP or its index sidecar. `source/download.py` downloads into `source/`, resumes transfers, and verifies the recorded checksums.

只处理指定产品可用 `split --products <product-id>`。Inspect 支持直接读取 STEP 或其索引。下载脚本将文件放入 `source/`，支持续传并校验记录的哈希。

## CAD and preview environment / CAD 与预览环境

The recorded CAD workflow uses Python 3.12 and `cadquery-ocp` 8.0.1. These commands use `uv`; ffmpeg must also be installed for video output.

已记录的 CAD 流程使用 Python 3.12 与 `cadquery-ocp` 8.0.1。下面使用 `uv` 管理环境；输出视频还需安装 ffmpeg。

```sh
uv venv ocpenv --python 3.12
uv pip install --python ocpenv/bin/python cadquery-ocp==8.0.1 numpy scipy vtk pillow
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/validate_parts.py out/v20 --mesh
```

This validates the per-part face counts, bounds, and colors, then tessellates them. It writes `validation.json`; it does not create a simulator package.

该步骤校验逐件面数、包围盒及颜色，并生成网格，结果写入 `validation.json`，不会直接生成仿真器资源包。

## Configure exports / 配置导出

Python geometry exporters use a `.npz` source index in addition to the split package. Build indexes for the releases your job references, for example:

Python 几何导出器除拆分包外还使用 `.npz` 源索引。为任务引用的版本建立索引，例如：

```sh
ocpenv/bin/python python/p21index.py source/RMUC2026_V2.0.0.stp v20.npz
ocpenv/bin/python python/export_job.py rules/export-job.example.json --dry-run
```

Edit a copy of the example job before running it without `--dry-run`. The example also needs a V1.2.0 split/index and an existing equipment package. Paths resolve relative to the job file. Select fresh output directories. The [export job guide](detail-optimization.md), [presets](export-presets.md), and [geometry audit](geometry-audit.md) describe those inputs and checks.

正式执行前先复制并修改任务文件。示例还依赖 V1.2.0 拆分包与索引，以及现有设备资源包。路径相对于任务文件，输出目录应选择新目录。输入和检查规则见[导出任务](detail-optimization.md)、[预设](export-presets.md)及[几何审计](geometry-audit.md)。

Optional simplification / 可选简化：

```sh
uv pip install --python ocpenv/bin/python -r python/requirements-simplification.txt
# Configure input/output paths first / 先配置输入输出路径
ocpenv/bin/python python/simplify_package.py rules/simplify-simulation.example.json
```

See the [simplification contract](mesh-simplification.md) before choosing error tolerances. Never apply semantic triangle selectors to an already simplified mesh.

设置误差前请阅读[简化约定](mesh-simplification.md)。不要将基于原始三角形编号的语义选择规则应用到已简化的网格上。

## Reference assets and animations / 参考资源与动画

These commands assume the checksum-pinned source packages already exist under `../assets/rm2026-field`, including `equipment/`. `--replace` keeps an existing reference as a dated backup. It does not deploy into the active simulator directory.

以下命令要求固定哈希的源资源包已位于 `../assets/rm2026-field`，包括 `equipment/`。`--replace` 将已有参考包保存为带时间标记的备份，不会部署到仿真器当前目录。

```sh
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/update_reference_assets.py --replace
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/verify_reference_motion.py

OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/preview/render_joints.py \
  ../assets/rm2026-reference/equipment --asset base \
  --presentation --seconds 8 --out out/demos

OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/preview/render_joints.py \
  ../assets/rm2026-reference/equipment --asset tech-core --tech-core-demo \
  --core-motion pose-tour --presentation --seconds 14 --out out/demos
```

Use `../assets/rm2026-reference` with `--asset rune`, `outpost`, or `dart-station`. Omit `--presentation` for a fixed-camera inspection with labels and joint markers. The [gallery](demos.md) includes both formats; [reference asset documentation](reference-assets.md) describes the underlying bindings.

`rune`、`outpost` 和 `dart-station` 使用 `../assets/rm2026-reference`。省略 `--presentation` 可生成固定视角、带说明和关节标记的检查动画。[画廊](demos.md)包含两种形式，[参考资源文档](reference-assets.md)说明具体绑定。

## Articulated equipment / 关节设备

Export existing joint bindings to SDF, URDF, and USD with the [articulated exporter](articulated-formats.md). It preserves rigid links, visual/collision membership, axes, and known travel. These are kinematic assets without calibrated dynamics or match controllers.

使用[关节导出器](articulated-formats.md)将现有关节绑定导出为 SDF、URDF 和 USD，保留连杆、可视与碰撞归属、轴及已知行程。输出为运动学资源，不包含标定动力学参数或比赛控制器。

```sh
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/export_articulated.py \
  ../assets/rm2026-reference --out out/articulated-models
```

## Static simulator scenes / 静态仿真场景

`python/export_sim.py` converts an element package to SDF, MJCF, and USD. USD generation requires `usd-core`; verification/rendering uses the corresponding runtime libraries, including MuJoCo. Articulated inputs require `--static-rest-pose`, which explicitly bakes the source rest pose rather than exporting match controllers.

`python/export_sim.py` 将元素资源包转换为 SDF、MJCF 和 USD。USD 生成需要 `usd-core`，验证与渲染使用对应运行库，包括 MuJoCo。带关节的输入需显式指定 `--static-rest-pose`，以烘焙源静止姿态，不会导出比赛控制逻辑。

```sh
ocpenv/bin/python python/export_sim.py ../assets/rm2026-field-elements \
  --out out/sim-scenes --static-rest-pose
ocpenv/bin/python python/export_sim.py ../assets/rm2026-field-elements \
  --out out/sim-scenes --static-rest-pose verify
```

## Checks and generated files / 检查与生成文件

```sh
cargo test --workspace --locked
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python -m unittest discover -s python -p 'test_*.py'
```

`out/` holds disposable caches, split packages, and intermediate renders. Retained reports and previews live under `docs/` and `benchmarks/`; actual CAD and GLB packages remain local and ignored by Git. Check that a final package is retained elsewhere before deleting its staging copy.

`out/` 存放可重新生成的缓存、拆分包和中间渲染。保留的报告与预览位于 `docs/` 和 `benchmarks/`，CAD 与 GLB 资源包留在本地并被 Git 忽略。删除中间副本前，应确认最终资源包已保存在其他位置。
