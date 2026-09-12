# 导出

[文档](index.md) · [入门](getting-started.md) · [简化](simplification.md) · [English](../exporting.md)

按用途选择输出。以下命令均在仓库根目录运行，使用[入门](getting-started.md)中安装的 Python 环境。

## 目录

- [支持的输出](#支持的输出)
- [准备输入](#准备输入)
- [配置完整导出](#配置完整导出)
- [生成并检查 GLB 资源包](#生成并检查-glb-资源包)
- [导出静态仿真场景](#导出静态仿真场景)
- [导出关节设备](#导出关节设备)
- [检查结果](#检查结果)

## 支持的输出

| 输出 | 导出器 | 用途与限制 |
| --- | --- | --- |
| STEP `.stp` + `parts.json` | Rust `split` | 独立的源产品；保留几何实体 |
| 可视/碰撞 `.glb` + `manifest.json` | `export_field_package.py`、`export_elements.py` | 带位置、颜色和独立碰撞几何的场地资源 |
| GLB 元数据 + `articulation.json` | `export_semantics.py` | 关节、装甲、LED、队伍颜色与图层 |
| 静态 SDF、MJCF、USD | `export_sim.py` | 场地场景；含关节的输入需显式静止姿态烘焙 |
| 关节设备 SDF、URDF、USD | `export_articulated.py` | 使用已有关节绑定的独立设备模型 |
| PNG 纹理图集，侧车或内嵌 GLB | `texture_atlas.py` 或导出器选项 | 栅格化图案；见[纹理图集导出](../texture-atlas.md) |

URDF 是设备导出，MJCF 是静态场景导出。关节 XML 模型使用 STL 网格文件；USD 内嵌网格。关节适配器保留基础颜色，但不转换纹理及其他 PBR 属性。

## 准备输入

单文件 STEP 拆分参见[快速开始](../../README.zh-CN.md#快速开始)。完整场地生成还需要 Python 源索引：

```sh
ocpenv/bin/python python/p21index.py source/RMUC2026_V2.0.0.stp v20.npz
```

[示例场地任务](../../rules/export-job.example.json)会合并多个发布版本。运行前需准备：

| 输入 | 示例位置 | 获取方式 |
| --- | --- | --- |
| V1.2.0 拆分资源包 | `out/v12` | 下载 `RMUC2026_V1.2.0.stp`，按快速开始索引并拆分 |
| V1.2.0 Python 索引 | `v12.npz` | 对 V1.2.0 的 STEP 运行 `p21index.py` |
| V2.0.0 拆分与 Python 索引 | `out/v20`、`v20.npz` | 快速开始加上面的命令；提供嫁接的道路资源 |
| 已有设备资源包 | `../assets/rm2026-field` | 提供任务引用的本地资源包；快速开始不会打包或创建它 |
| 归属与容差规则 | `rules/` | 对照你的源版本核对提供的 JSON 文件 |

设备依赖意味着该示例不是仅凭全新克隆就能完成的完整场地重建。源文件、拆分资源包和预生成 GLB 设备是不同的输入。

## 配置完整导出

使用 JSON 任务配置输入路径、嫁接、输出目录和导出阶段：

```sh
ocpenv/bin/python python/export_job.py rules/export-job.example.json --dry-run
ocpenv/bin/python python/export_job.py rules/export-job.example.json
```

路径相对于 JSON 文件解析，与当前目录无关。运行器在启动前校验完整的任务结构和共享策略；它使用当前 Python 解释器调用脚本、不经 shell、在第一个失败阶段停止。输出目录必须是新目录且不得重叠。某阶段失败时已完成的阶段仍然保留；没有自动回滚或续跑。几何与语义检查仍在各个导出器内运行。

阶段的 `type` 为 `field`、`elements`、`entities`、`semantics` 或 `deploy`。参数使用 snake_case 命名；`package` 和 `index` 取代位置参数。嫁接使用结构化的 `package`、`index`，场地导出器还使用 `products` 字段。示例包含完整的 field/elements/deploy 流程。查看新导出资源的目录后，可添加带 `package`、`rules`、`out` 的 `semantics` 阶段。语义规则以校验和固定；该运行器不改写这些校验和。

共享的 `policy` 文件控制网格化和精确名称覆盖，也可以写 `"preset": "simulation"`，让预设同样保存在配置里。显式的命令行 `--preset` 优先。容差优先级和碰撞排除见[导出预设](../export-presets.md)。

## 生成并检查 GLB 资源包

把 `rules/export-job.example.json` 复制为 `rules/export-job.local.json`，修改其中的输入输出路径后运行：

```sh
ocpenv/bin/python python/export_job.py rules/export-job.local.json --dry-run
ocpenv/bin/python python/export_job.py rules/export-job.local.json
```

示例依次运行场地导出、元素导出和运行时组装；`deploy` 阶段写入配置的输出目录。要添加语义绑定，先查看新 GLB 目录和以校验和固定的规则，再加入 `semantics` 阶段，见[语义导出](../semantic-export.md)。可在绑定前用 `entities` 阶段创建独立场景单元，见[实体提取](../entity-extraction.md)。

默认网格化预设是 `simulation`。容差表、精确名称覆盖和直接调用导出器见[导出预设](../export-presets.md)。减面与装饰清理是独立操作，见[简化](simplification.md)。

使用资源包前，检查 `manifest.json`、其中的文件哈希与碰撞声明，以及各导出器的校验报告。源选择器有改动时，复查几何与运动。保留源资源包副本，并为每次候选输出选择新目录。

## 导出静态仿真场景

在同一环境中安装可选的 USD 与 MuJoCo 依赖：

```sh
uv pip install --python ocpenv/bin/python usd-core mujoco
ocpenv/bin/python python/export_sim.py out/configured-elements \
  --out out/sim-scenes --static-rest-pose
ocpenv/bin/python python/export_sim.py out/configured-elements \
  --out out/sim-scenes --static-rest-pose verify
```

该命令写出 SDF、MJCF 和 USD 场景资源。`--static-rest-pose` 允许含关节的输入，并按源静止姿态烘焙；纯静态输入可省略。`--no-isaac` 跳过 USD；未安装 `usd-core` 时 USD 也会被跳过。导出命令自带校验；运行时相关校验需要对应的库。

## 导出关节设备

先按[参考资源](../reference-assets.md)准备固定版本的语义资源包。安装 NumPy、SciPy 和 `usd-core` 后：

```sh
ocpenv/bin/python python/export_articulated.py \
  ../assets/rm2026-reference --out out/articulated-models
```

用重复的 `--asset` 参数和 `--formats sdf urdf` 选择设备与格式。输出目录必须是新目录；导出器自动发现内嵌的设备资源包。

这些模型保留关节绑定和已知行程，不包含质量、惯量、执行器或比赛控制器。科技核心的六个坐标框架导出为固定参考框架。ROS 包安装、坐标系、材质支持与验证见[关节设备格式](articulated-formats.md)。

## 检查结果

打开[交互查看器](viewer.md)检查本地 GLB 或导出的 URDF/SDF 设备目录，用轨道控制和关节滑块在不同坐标下检查几何。
