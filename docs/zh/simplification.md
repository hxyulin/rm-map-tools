# 简化

[文档](index.md) · [导出](exporting.md) · [English](../simplification.md)

各预设与后续处理的网格、图元、顶点、三角形和文件大小实测见[简化统计](../simplification-results.md)。

缩减发生在多个阶段：STEP 拆分保留源几何，网格化近似 CAD 曲面，之后的网格简化是有损的。并非每个资源包都需要所有优化，JSON 导出运行器也不会自动执行以下全部步骤。

## 目录

- [处理顺序](#处理顺序)
- [网格缩减](#网格缩减)
- [图案与碰撞清理](#图案与碰撞清理)
- [审计与实验](#审计与实验)

## 处理顺序

1. **拆分并校验源文件。** 保留原始 STEP、拆分清单和源哈希；先解决缺面和归属问题再降细节。见[入门](getting-started.md)与[几何审计](../geometry-audit.md)。
2. **选择网格化设置。** 可视与碰撞网格分别生成；默认 `simulation` 预设带地形和机构的逐资源例外。见[导出预设](../export-presets.md)。
3. **应用已复核的构图与提取规则。** 视情况删除重复的道路字样、分类装饰、提取独立场景单元。这些操作依赖针对源文件的选择。见[构图与装饰](../composition.md)与[实体提取](../entity-extraction.md)。
4. **绑定语义与关节。** 以校验和固定的节点、图元和三角形选择必须在简化改变三角形编号之前应用。见[语义导出](../semantic-export.md)。
5. **按需提取纹理图案。** 选择精确的平面节点/材质对并移除选中的图案三角形；处理底图期间贴片单独保存。见[纹理图集](../texture-atlas.md)。
6. **简化其余网格。** 在既有图元内塌缩边，保留受保护几何与连通分量，并分别对可视与碰撞独立做抽样偏差检查。按所建资源包选择包简化器或图集流水线的底图简化器。
7. **最后附加原生纹理贴片。** 在底图简化后嵌入 PNG 和带纹理的四边形；侧车模式则需要消费方自行绘制贴片。纹理四边形不会成为碰撞体。
8. **检查并组装结果。** 复查几何、关节运动、计数、抽样误差、清单与碰撞契约；保留纹理页和侧车。图集资源不会自动贯穿所有构图或部署工具。

不要对同一几何串联两条简化路径；修改设置时从未简化的源重新开始。生产包简化器会拒绝已简化的资源。

## 网格缩减

安装可选依赖，复制[仿真配置示例](../../rules/simplify-simulation.example.json)并设置其输入输出路径后运行：

```sh
uv pip install --python ocpenv/bin/python -r python/requirements-simplification.txt
ocpenv/bin/python python/simplify_package.py rules/simplify-simulation.example.json
```

路径相对于配置文件解析；输出必须是新目录。默认值与逐资源覆盖控制可视和碰撞误差指标、抽样上限、边界锁定与精确图元保留。设置与实现细节见[网格简化](../mesh-simplification.md)。

简化器只焊接完全相等的位置，并在材质图元内工作。缺失的连通分量会以更紧的误差设置重试，最多十二轮；不可再缩的分量保留原始三角形。关节层级、节点变换、语义元数据和受保护的光学表面保持不变。

仿真设置解锁边界以压缩 CAD 接缝和小开口，但这不分类每个孔，也不保证孔径上限。抽样距离相对输入网格度量，而输入本身已含网格化误差，因此不是相对 STEP 的认证最大偏差。

## 图案与碰撞清理

[构图与装饰](../composition.md)说明两处重复的道路字样与已复核的墙面/甲板装饰。分类保留可视图案，只移除显式选中的碰撞几何，并按配置修补底图。

[纹理图集导出](../texture-atlas.md)把选中的平面图案转为栅格贴片；可选的 `simplify` 块在提取与附加之间简化可视底图；`collision_simplify` 单独移除匹配的碰撞体图案并可简化剩余碰撞体。可视三角形序号绝不能复用为碰撞选择器。

## 审计与实验

这些报告记录流水线的发展过程，是带日期的结果，不是额外的默认阶段。

| 工作 | 状态与证据 |
| --- | --- |
| 更粗的网格化 | [预设对比](../../benchmarks/2026-09-11-tessellation-presets/README.md) |
| 小曲面与放宽角度容差 | [细节审计](../detail-optimization.md)；未启用自动 CAD 孔/圆角删除 |
| 锁定与解锁边塌缩 | [初始轮](../../benchmarks/2026-09-11-mesh-simplification/README.md)、[边界研究](../../benchmarks/2026-09-11-aggressive-mesh/README.md)、[解锁输出](../../benchmarks/2026-09-11-unlocked-mesh/README.md) |
| 连通分量保留改进 | [分量改进](../../benchmarks/2026-09-11-component-refinement/README.md)，已实现于简化器 |
| 图案转换与碰撞底图 | [图集简化](../../benchmarks/2026-09-11-atlas-simplification/README.md)、[原生纹理](../../benchmarks/2026-09-11-native-textures/README.md)、[碰撞图案](../../benchmarks/2026-09-11-collision-artwork/README.md) |
| 共享几何与分发压缩 | [几何共享](../../benchmarks/2026-09-11-geometry-sharing/README.md)、[成组薄板原型](../../benchmarks/2026-09-11-grouped-sheets/README.md)、[去重探索](../../benchmarks/2026-09-11-geometric-deduplication/README.md) |
| 以原始源为上限的重复简化 | [递归试验](../../benchmarks/2026-09-11-recursive-simplification/README.md)；仅供检查 GLB，不是生产默认 |

实测启动与内存结果见[性能记录](performance.md)。三角形更少本身不构成帧率或物理加速的证明。
