# rm-map-tools

[English](README.md) · [简体中文](README.zh-CN.md)

[![Rust 1.88+](https://img.shields.io/badge/Rust-1.88%2B-DEA584?logo=rust&logoColor=black)](Cargo.toml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](docs/previews.md)
[![OCCT 8.0.1](https://img.shields.io/badge/OCCT-8.0.1-336699)](docs/split-proof.md)
[![glTF 2.0](https://img.shields.io/badge/glTF-2.0-87C540?logo=gltf&logoColor=white)](docs/semantic-export.md)
[![CI](https://img.shields.io/github/actions/workflow/status/hxyulin/rm-map-tools/ci.yml?branch=main&label=CI)](https://github.com/hxyulin/rm-map-tools/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20Apache--2.0-blue)](#许可与源数据)

将 RoboMaster 场地 CAD 转换为可独立处理的零件、经过校验的仿真资源，以及可查看机构运动的动画。

**1.25 GB 的 STEP 文件可在 8.4 秒内拆成 429 个独立零件。在 M3 Pro 上，逐件导入、校验并生成网格共耗时 4 分 17 秒，峰值内存为 4.7 GB。**

[速度与内存](docs/performance.md) · [架构图](docs/architecture-overview.md) · [演示画廊](docs/demos.md) · [导出设置](docs/export-presets.md)

![RoboMaster 场地总览](docs/previews/field-elements-full-map-top.png)

## 为什么做这个项目

官方场地文件包含数百万个 STEP 实体、大量共享的显示样式、片体，以及混合存放的装配零件。将整个文件直接导入 CAD 软件后，即使只修改一个小机构，也可能需要漫长的等待。仿真器还需要独立碰撞模型、合理的坐标原点、可识别的装甲板和灯光，以及能够带动正确零件的关节。

`rm-map-tools` 先拆分 STEP 引用关系，再调用 CAD 内核。Rust 负责索引和复制相关源实体，OCCT 按零件导入，Python 则负责场地组合、来源与颜色保留、语义标注和几何校验。这样可以单独处理一个机构，而不必反复导入整个场地。

## 速度与内存

实际记录的区别是：**整文件处理需要数小时；拆分只需数秒，逐件校验和生成网格只需数分钟。**

| 工作流程 | 机器 | 耗时 | 峰值内存 | 计时范围 |
| --- | --- | ---: | ---: | --- |
| OCCT 整文件转换 | M5 Max Mac¹ | **8 小时 57 分** | **约 40 GB** | STEP 读取、XCAF 转换、网格生成及单个 GLB 写出 |
| SolidWorks 2024 | Ryzen 9 9950X3D² | **15 小时** | **约 25 GB** | 项目作者提供的整文件处理结果，未记录具体阶段 |
| Rust 拆分 RMUC V2.0.0 | M3 Pro，18 GiB | **8.4 秒** | **3.6 GB** | 写出全部 429 个独立 STEP 零件 |
| OCCT 逐件校验与网格生成 | M3 Pro，18 GiB | **4 分 17 秒** | **4.7 GB** | 导入、校验并网格化已拆分的 V2.0.0 零件 |

V2.0.0 的首次索引另需 **1.3 秒**。993 MB 的 V1.2.0 可在 **2.7 秒**内拆成 **1,047 个零件**，拆分峰值内存为 **1.9 GB**。

¹ 转换日志记录了 32,229 秒；M5 Max 的机器信息由项目作者确认，约 40 GB 的内存数字来自已有项目记录。² SolidWorks 的时间和内存由项目作者提供。表中机器和工作范围不同，4 分 17 秒不包含同等的整场 GLB 序列化，因此不据此宣称端到端加速倍数。峰值内存是实测占用，不是最低系统配置保证。

[详细计时、数据来源与适用范围 →](docs/performance.md)

可选的网格简化还将本地仿真场景准备时间从 **15.50 秒降到 5.73 秒**，所引用的 GLB 总体积从 **587 MB 降到 260 MB**。这是热缓存条件下的对照测试，不代表帧率或冷启动性能。[查看测试记录 →](benchmarks/2026-09-11-mesh-simplification/README.md)

## 可以得到什么

| 输出 | 用途 |
| --- | --- |
| `parts/*.stp` 与 `parts.json` | 独立源零件，以及归属、包围盒、面数和颜色记录 |
| 可视与碰撞 GLB、`manifest.json` | 带实例位置、文件哈希和明确碰撞约定的场地元素 |
| glTF 元数据与 `articulation.json` | 易读名称、关节、装甲板大小与类型、LED、队伍颜色和图层 |
| 语义参考资源包 | 可检查的机构及明确标注的补建结构，与仿真器安装目录分开 |
| GIF、MP4、PNG 与 JSON 报告 | 环绕镜头、关节检查、原始模型与演示模型对照 |
| SDF、MJCF、USD | 面向 Gazebo、MuJoCo、Isaac Sim 的场景导出，见[使用指南](docs/getting-started.md) |

STEP 拆分逐字节保留几何实体。曲面网格化本身有近似误差；可选网格简化则是经过采样误差检查的有损步骤。各阶段分别记录验证结果，见[拆分证明](docs/split-proof.md)、[几何审计](docs/geometry-audit.md)和[简化约定](docs/mesh-simplification.md)。

## 机构演示

[可折叠演示画廊](docs/demos.md)汇总了现有机构的全部 GIF 与 MP4、场地总览和源模型审计图片。

| 机构 | 预览 | 运动内容 |
| --- | --- | --- |
| 基地 | [环绕 MP4](docs/previews/clean/base-joints-orbit.mp4) | 护甲展开与轨道飞镖靶移动；补建内壁和装甲板固定 |
| 科技核心 | [姿态演示 MP4](docs/previews/clean/tech-core-demo-orbit.mp4) | 六轴演示、已恢复的工具外壳，以及 100 mm 平移段 |
| 能量机关 | [环绕 MP4](docs/previews/clean/rune-joints-orbit.mp4) | 叶臂及外围轮毂旋转；中心标志与轴保持固定 |
| 前哨站 | [环绕 MP4](docs/previews/clean/outpost-joints-orbit.mp4) | 转子及附属零件一起运动 |
| 飞镖发射井 | [环绕 MP4](docs/previews/clean/dart-station-joints-orbit.mp4) | 窗口沿倾斜导轨滑动 |

护甲行程和补建尺寸仍为示意值。科技核心导出的关节目前仅包含坐标框架；网格动画使用单独的预览绑定和示意轴承。演示时序不等于比赛控制逻辑。画廊各节均附有对应依据和限制。

## 快速开始

索引、查看和拆分只需 Rust 1.88 或更新版本，无需 CAD 内核。

```sh
cargo build --release --locked
python3 source/download.py fetch RMUC2026_V2.0.0.stp
mkdir -p out

target/release/rm-map-tools index source/RMUC2026_V2.0.0.stp -o out/v20.p21idx
target/release/rm-map-tools inspect out/v20.p21idx --json out/v20-inspection.json
target/release/rm-map-tools split out/v20.p21idx -o out/v20
```

源文件较大。下载脚本支持断点续传并校验记录的哈希；已通过校验的本地文件会直接复用。

OCCT 校验、仿真导出和动画生成步骤见[使用指南](docs/getting-started.md)。完整流水线通过 [JSON 任务文件](docs/detail-optimization.md)配置，其中路径相对于任务文件解析。`out/` 是可重新生成的中间目录，原始数据和最终资源包应单独保存。

## 架构与文档

[架构概览](docs/architecture-overview.md)分别展示 STEP 处理、仿真资源导出和语义运动流程。[实现文档](docs/architecture.md)介绍 Rust 模块与拆分算法。

| 文档 | 内容 |
| --- | --- |
| [性能记录](docs/performance.md) | 耗时、内存、机器信息及测试范围 |
| [使用指南](docs/getting-started.md) | 安装、拆分、校验、导出与预览命令 |
| [演示画廊](docs/demos.md) | 可折叠动画和可视化对照 |
| [STEP 笔记](docs/step-notes.md) / [拆分证明](docs/split-proof.md) | 源数据结构及保留验证 |
| [导出预设](docs/export-presets.md) / [细节优化](docs/detail-optimization.md) | 网格化、碰撞策略和导出任务 |
| [语义导出](docs/semantic-export.md) / [参考资源](docs/reference-assets.md) | 关节、装甲板、灯光、颜色和图层约定 |
| [几何审计](docs/geometry-audit.md) / [网格简化](docs/mesh-simplification.md) | 归属、遗漏检查及网格减面 |

## 许可与源数据

代码和文档采用 [MIT](LICENSE-MIT) 或 [Apache-2.0](LICENSE-APACHE) 双重许可。官方 CAD 及其派生模型几何属于 DJI / RoboMaster，使用时仍受其条款约束。仓库不提交模型文件，但包含渲染预览和派生报告。本项目为独立项目，详见 [NOTICE.md](NOTICE.md)。
