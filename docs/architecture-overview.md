# Architecture diagrams / 架构图

[English README](../README.md) · [中文 README](../README.zh-CN.md) · [Implementation details / 实现细节](architecture.md)

These diagrams separate source preservation, asset generation, and demo behavior. A successful check in one stage does not certify the others.

以下分别展示源数据保留、资源生成和演示行为。一个阶段通过检查，并不代表其他阶段也已得到验证。

## 1. STEP processing / STEP 处理

```mermaid
flowchart LR
    A["Official STEP source<br/>官方 STEP 源文件"] --> B["Rust scanner and index<br/>Rust 扫描与索引"]
    B --> C["Entity IDs, byte ranges, references<br/>实体编号、字节范围、引用关系"]
    C --> D["Ownership and assembly model<br/>归属与装配关系"]
    D --> E["Reference closure and style filtering<br/>引用闭包与样式列表筛选"]
    E --> F["Standalone STEP parts<br/>独立 STEP 零件"]
    E --> G["parts.json<br/>来源、颜色、包围盒"]
    F --> H["OCCT per-part import<br/>OCCT 逐件导入"]
    G --> I["Face, bounds and color checks<br/>面数、边界与颜色校验"]
    H --> I
```

`crates/step21` handles source bytes and references; `crates/rm-map-tools` exposes `index`, `inspect`, and `split`. Geometry entities are copied verbatim. Shared list records are filtered, while assembly placements are recorded separately. OCCT is only needed after the split.

`crates/step21` 处理源字节与引用，`crates/rm-map-tools` 提供 `index`、`inspect` 和 `split` 命令。几何实体逐字节复制，共享列表按归属筛选，装配位置单独记录。只有拆分之后才需要 OCCT。

## 2. Simulator asset pipeline / 仿真资源流水线

```mermaid
flowchart TB
    A["Split parts and source index<br/>拆分零件与源索引"] --> B["Field and element exporters<br/>场地与元素导出"]
    P["Export policy<br/>可视与碰撞精度"] --> B
    R["Element ownership rules<br/>元素归属规则"] --> B
    B --> V["Visual GLBs<br/>可视网格"]
    B --> C["Collision GLBs<br/>碰撞网格"]
    B --> M["Manifests and validation<br/>清单与验证结果"]
    V --> S["Semantic binding<br/>语义绑定"]
    C --> S
    S --> Q["Optional mesh simplification<br/>可选网格简化"]
    Q --> D["Deviation and integrity checks<br/>偏差与完整性检查"]
    M --> D
    D --> K["Staged runtime package<br/>暂存并发布运行资源包"]
    K --> SIM["rm-simulator consumer<br/>仿真器读取"]
    B --> X["Static scene adapters<br/>静态场景转换"]
    X --> F["SDF / MJCF / USD"]
    S --> A["Rigid links from motion nodes<br/>按运动节点划分连杆"]
    A --> J["Articulated SDF / URDF / USD<br/>关节模型导出"]
```

Visual and collision tolerances are independent. Semantic bindings precede simplification so node, material, and joint boundaries can be preserved. The simplifier has its own collision contract and sampled deviation checks. File hashes verify package integrity. SDF/MJCF/USD adapters export static scene arrangements; articulated assets require an explicit rest-pose bake in that path.

可视与碰撞精度独立设置。先做语义绑定，再简化网格，以保留节点、材质和关节边界。简化器有独立的碰撞约定与采样偏差检查，文件哈希用于检查资源包完整性。SDF/MJCF/USD 路径导出静态场景，遇到带关节的资源时需明确选择静止姿态烘焙。

The separate [articulated exporter](articulated-formats.md) preserves semantic joint bindings as SDF, URDF, and USD kinematic equipment models.

独立的[关节导出器](articulated-formats.md)将语义关节绑定保留为 SDF、URDF、USD 运动学设备模型。

## 3. Semantic reference and motion / 语义参考与运动

```mermaid
flowchart LR
    CAD["Pinned source meshes<br/>固定哈希的源网格"] --> REF["Reference package<br/>参考资源包"]
    RULES["Reviewed rules and partitions<br/>审核后的规则与几何分组"] --> REF
    ADD["Labeled reconstruction<br/>明确标注的补建结构"] --> REF
    REF --> GLB["glTF node extras<br/>节点元数据"]
    REF --> SIDE["articulation.json<br/>关节与语义侧文件"]
    GLB --> POSE["Joint pose application<br/>应用关节姿态"]
    SIDE --> POSE
    DEMO["Demo profiles and Core preview rig<br/>演示曲线与核心预览绑定"] --> POSE
    POSE --> RENDER["VTK and ffmpeg<br/>GIF / MP4 / PNG"]
    POSE --> CHECK["Rest geometry and motion checks<br/>静止几何与运动检查"]
```

The reference package is separate from the active simulator installation. Joint metadata describes axes, parents, children, limits where known, and evidence. Armor and LED metadata describe family, size, color ownership, and control channels. Layers categorize geometry; they do not automatically remove collision geometry.

参考资源包与仿真器当前安装分开。关节元数据记录轴、父子关系、已知限位和依据。装甲板与 LED 元数据记录类型、大小、队伍颜色归属及控制通道。图层用于分类，不会自动删除碰撞几何。

The Base inner wall is a labeled reconstruction. Its shield travel is illustrative. The Core's source reference retains unbound meshes and six joint frames; a disposable demo rig binds selected CAD parts, restores the tool enclosure, and adds schematic bearings. The rail's sine motion is demo-only. Simulator match behavior remains a separate consumer responsibility.

基地内壁是明确标注的补建结构，护甲行程为示意值。科技核心源参考保留未绑定网格和六个关节框架；临时演示模型绑定选定 CAD 零件、恢复工具外壳，并使用示意轴承。轨道正弦运动只用于演示。比赛状态与控制逻辑仍由使用资源的仿真器负责。
