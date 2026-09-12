# 文档

[English](../README.md)

先阅读[入门](getting-started.md)拆分并校验 STEP 文件，再用[导出](exporting.md)选择资源包或仿真器格式，最后用[简化](simplification.md)缩减体积。

## 指南

| 指南 | 内容 |
| --- | --- |
| [发布与下载](releases.md) | 选择 STEP、GLB、仿真器或查看器压缩包 |
| [入门](getting-started.md) | 安装、下载、拆分与校验 |
| [导出](exporting.md) | 输入、JSON 任务、GLB、SDF、URDF、MJCF 与 USD |
| [简化](simplification.md) | 处理顺序、图案转换、网格缩减与检查 |
| [架构](architecture.md) | 流水线与代码结构 |
| [交互查看器](viewer.md) | 在文档站点中检查模型并调节关节 |
| [文档网站](site.md) | 本地运行、编辑页面并部署到 GitHub Pages |

## 技术参考

以下页面以英文为主：

- [STEP 内部结构](../step-internals.md)、[源文件笔记](../step-notes.md)与[拆分证明](../split-proof.md)。
- [导出预设](../export-presets.md)、[网格简化设置](../mesh-simplification.md)与[纹理图集导出](../texture-atlas.md)。
- [构图与装饰](../composition.md)、[实体提取](../entity-extraction.md)与[细节审计](../detail-optimization.md)。
- [语义导出](../semantic-export.md)、[参考资源](../reference-assets.md)与[关节设备格式](articulated-formats.md)。

## 机制与证据

- [基地重建](../base-reconstruction.md)、[基地内部审计](../base-interior-audit.md)与[基地飞镖靶轨道](../base-dart-target.md)。
- [飞镖窗口](../dart-window.md)与[科技核心关节](../technology-core-joints.md)。
- [几何审计](../geometry-audit.md)、[性能记录](performance.md)与[优化报告](../simplification.md#audits-and-experiments)。
- [原始关节设计](../articulation-design.md)，保留为设计历史；已实现的契约以[语义导出](../semantic-export.md)参考为准。

Markdown 文件既是 GitHub 浏览的源，也是文档站点的源。带日期的基准报告保留其测量范围与复现输入。
