# 发布与下载

[文档](index.md) · [English](../releases.md)

每个资源版本对应一次发布，不同工作流使用各自独立的压缩包。STEP、GLB、仿真器模型和文档查看器共用同一个发布 tag，便于一起核查来源与差异。只有资源版本变化时才需要发新版本，而不是每增加一种文件格式就发一次。

| 下载 | 用途 |
| --- | --- |
| `rmuc2026-cad-step.zip` | 可编辑的基于源文件的 STEP 装配与位置元数据 |
| `rmuc2026-glb-optimized.zip` | 优化后的场地可视网格、碰撞体、纹理与清单 |
| `rmuc2026-simulators.zip` | SDF、URDF、USD 格式的独立设备，含共享网格资源 |
| `docs-viewer-models.zip` | 五个交互文档模型与关节目录 |
| `SHA256SUMS.txt` | 压缩包完整性校验 |
| `validation-summary.json` | 打包来源与校验范围 |

按需下载。仿真器格式共用一个 ZIP，因为 SDF 和 URDF 共享同一批 STL 资源。GitHub 自动生成的源代码压缩包只包含工具代码，不包含上述模型下载。

见 [2026 年 9 月 11 日发布说明](../releases/2026-09-11.md)与[最新发布](https://github.com/hxyulin/rm-map-tools/releases/latest)。

解压后请保留各资源包的目录结构和清单。优化 GLB 包中的模型可能与关节导出所用未简化参考不同；相同的发布 tag 不代表各格式网格化一致。CAD 源几何与重建的展示几何也相互独立。这些差异在发布说明中注明。
