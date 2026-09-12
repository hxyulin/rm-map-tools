# 入门

[文档](index.md) · [导出](exporting.md) · [English](../getting-started.md)

命令均在仓库根目录运行。源 CAD 和生成的资源包是本地文件，不包含在 Git 中。

## 下载与拆分

按 [README 快速开始](../../README.zh-CN.md#快速开始)构建 Rust CLI、下载 RMUC V2.0.0 并完成拆分。下载脚本需要 Python 3；CLI 需要 Rust 1.88+。

下载的文件存放在 `source/`。校验已有下载：

```sh
python3 source/download.py verify RMUC2026_V2.0.0.stp
```

`inspect` 接受 STEP 文件或 `.p21idx` 索引。可按检查报告中的产品 ID 用 `split --products <product-id>` 选择子集。各命令选项见 `--help`。

拆分资源包含 `parts/*.stp` 和 `parts.json`，记录来源归属、包围盒、面数和颜色。原始 STEP 与其索引请一并保留。

## 安装 CAD 环境

记录的工作流使用 Python 3.12 与 `cadquery-ocp` 8.0.1。安装 `uv` 后：

```sh
uv venv ocpenv --python 3.12
uv pip install --python ocpenv/bin/python cadquery-ocp==8.0.1 numpy scipy vtk pillow
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/validate_parts.py out/v20 --mesh
```

校验逐件检查面数、包围盒和颜色，然后进行网格化。结果写入 `validation.json`；该命令不生成仿真器资源包。

简化和仿真器格式还有其他依赖，见各自指南。

## 后续步骤

- [导出](exporting.md)说明如何生成资源包并选择输出格式。
- [简化](simplification.md)介绍几何缩减与图案转换。
- [参考资源](../reference-assets.md)涵盖语义资源包与关节预览。
- [预览](../previews.md)介绍源网格查看器和平面图。

完整场地示例还需要 V1.2.0 源文件和已有设备资源包，仅下载 V2.0.0 并不包含这些输入。

## 开发检查与生成文件

```sh
cargo test --workspace --locked
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python -m unittest discover -s python -p 'test_*.py'
```

`out/` 存放一次性索引、拆分资源包和中间渲染。保留的报告与预览存放在 `docs/` 和 `benchmarks/`。删除暂存文件前，请先另行保存最终模型包。
