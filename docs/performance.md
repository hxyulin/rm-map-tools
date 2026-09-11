# Performance and memory / 速度与内存

[English README](../README.md) · [中文 README](../README.zh-CN.md)

The aim is to make field CAD practical on a laptop. The main measurements are elapsed time and peak process memory, with each operation named explicitly.

目标是在笔记本上实际处理场地 CAD。以下主要记录耗时和进程峰值内存，并明确每项数字对应的工作范围。

## Whole-file reference runs / 整文件参考记录

| Software / 软件 | Hardware / 硬件 | Elapsed / 耗时 | Peak RAM / 峰值内存 | Evidence / 来源 |
| --- | --- | ---: | ---: | --- |
| OCCT whole-file conversion / 整文件转换 | M5 Max Mac | 32,229 s, about 8 h 57 min / 约 8 小时 57 分 | ~40 GB / 约 40 GB | [Conversion log / 转换日志](../benchmarks/whole-file-reference/occt-conversion.json); RAM in [project notes / 项目记录](split-proof.md); machine attributed by project owner / 机器由项目作者确认 |
| SolidWorks 2024 | Ryzen 9 9950X3D | 15 h / 15 小时 | ~25 GB / 约 25 GB | Project-owner report, 2026-09-11; no raw timing log / 项目作者提供，未附原始计时日志 |

The OCCT log refers to `RMUC2026_V2.0.0.stp`. It records 25.1 s for file read, 7,834.6 s for XCAF transfer, 21.3 s for meshing, and 24,342.2 s for GLB serialization. Its reported total is 32,229.4 s. The log does not contain machine or RAM fields; those attributions are separate evidence. The SolidWorks report does not separately identify import, rebuild, and export phases, or pin the exact source version/settings.

OCCT 日志对应 `RMUC2026_V2.0.0.stp`：读取 25.1 秒、XCAF 转换 7,834.6 秒、网格生成 21.3 秒、GLB 写出 24,342.2 秒，总计 32,229.4 秒。日志本身未记录机器型号或内存字段，这两项来自单独说明。SolidWorks 的报告未分开记录导入、重建与导出阶段，也未固定源文件版本和设置。

## rm-map-tools on M3 Pro / M3 Pro 上的实测

Apple M3 Pro, 11 cores, 18 GiB RAM. Rust measurements are recorded in the [split proof](split-proof.md); OCCT and source-preservation details are in the [split proof](split-proof.md). These are historical measurements, not a new rerun for this README.

机器为 Apple M3 Pro、11 核、18 GiB 内存。Rust 数字见[拆分证明](split-proof.md)，OCCT 和源数据保留检查见[拆分证明](split-proof.md)。这里整理的是已有测试记录，并非为本次 README 重新跑出的结果。

| Operation / 操作 | V2.0.0, 1.25 GB | V1.2.0, 993 MB |
| --- | ---: | ---: |
| Index / 建立索引 | 1.3 s | 1.1 s |
| Inspect saved index / 读取索引并检查 | 0.5 s | 0.7 s |
| Split all products / 拆分全部产品 | 8.4 s, 429 parts / 零件 | 2.7 s, 1,047 parts / 零件 |
| Split peak RSS / 拆分峰值内存 | 3.6 GB | 1.9 GB |
| OCCT accumulated part-read time / 逐件读取累计耗时 | 205 s | 117 s |
| OCCT part-read peak RSS / 逐件读取峰值内存 | 4.5 GB | 3.2 GB |
| OCCT validation + meshing wall time / 校验与网格生成总耗时 | 257 s / 4 分 17 秒 | Not separately recorded here / 此处无单独记录 |
| OCCT validation + meshing peak RSS / 校验与网格生成峰值内存 | 4.7 GB | Not separately recorded here / 此处无单独记录 |

The largest V2.0.0 equipment product is still a 674 MB part and dominates the CAD-kernel cost. Splitting by product does not promise that every individual part is small.

V2.0.0 最大的设备产品拆分后仍有 674 MB，是 CAD 内核耗时的主要来源。按产品拆分并不保证每个零件都很小。

The stages run separately. Do not add their peak RAM figures together. The 4.7 GB measurement demonstrates the tested workflow on an 18 GiB machine; it is not a promise that any 4.7 GB machine can run it. Preview generation, other export presets, and concurrent tasks can use additional memory.

各阶段分别运行，峰值内存不能简单相加。4.7 GB 说明该工作流程在 18 GiB 机器上的实测占用，并不意味着仅有 4.7 GB 内存的机器一定可运行。预览、其他导出设置和同时运行的任务还会占用额外内存。

## What the comparison means / 如何理解对比

The split workflow avoids repeatedly transferring the complete STEP assembly into a CAD kernel. It preserves geometry entities and processes smaller files independently. That changes where the expensive work happens.

拆分流程避免反复将整个 STEP 装配转换为 CAD 内核对象，先保留并拆出几何实体，再分别处理小文件，从而改变最耗时步骤的处理方式。

The whole-file OCCT result includes a single large GLB write. The 257 s part validation result does not. The SolidWorks figure is a reported application workflow on another machine. Presenting these times side by side explains the practical motivation; dividing them into a universal speedup factor would hide those differences. Mesh quality, source version, and output format must also be matched for an end-to-end benchmark.

整文件 OCCT 耗时包含写出一个大型 GLB，257 秒的逐件校验不包含该步骤。SolidWorks 数据则来自另一台机器上的软件操作记录。并列展示可以说明项目的实际动机，但不能直接相除得到通用加速倍数。端到端测试还需要统一网格质量、源版本和输出格式。

## Simulator startup / 仿真器场景准备

A separate three-run alternating comparison on M3 Pro measured median scene-ready time falling from 15.497 s to 5.734 s after bound-mesh simplification. Referenced GLBs fell from 587,168,572 to 259,669,320 bytes. OS caches were not cleared, and scene-ready means CPU instance setup, not first displayed frame. [Report and raw records](../benchmarks/2026-09-11-mesh-simplification/README.md).

另一组 M3 Pro 测试交替运行简化前后资源，各运行三次。场景准备时间中位数从 15.497 秒降至 5.734 秒，引用的 GLB 总字节数从 587,168,572 降至 259,669,320。未清空系统缓存；场景准备指 CPU 实例创建完成，并非第一帧显示时间。[报告及原始记录](../benchmarks/2026-09-11-mesh-simplification/README.md)。
