# 关节设备导出

[文档](index.md) · [Exporting](../exporting.md) · [English](../articulated-formats.md)

`python/export_articulated.py` 将现有语义设备导出为 SDF、URDF 和 USD。
程序按运动节点划分刚体，将网格转换到所属连杆坐标系，保留关节轴和行程。
它直接使用已有绑定，不重新剖分 CAD，也不重复维护关节定义。

```sh
OPENBLAS_NUM_THREADS=1 ocpenv/bin/python python/export_articulated.py \
  ../assets/rm2026-reference --out out/articulated-models

# 按设备或格式选择
ocpenv/bin/python python/export_articulated.py \
  ../assets/rm2026-reference --asset base --asset dart-station \
  --formats sdf urdf --out out/shield-models
```

目标目录必须尚不存在。所有选定格式写入成功后，才发布整个目录。
依赖 NumPy、SciPy，USD 还需要 `usd-core`。程序自动读取参考设备子资源包。
输出是独立设备模型；静态赛场和场景组装仍由原场景导出器及仿真器负责。
本次不新增 glTF 动画、MJCF 或 SRDF 导出。

## 输出

每个设备目录包含 `model.sdf`、`model.urdf`、`model.usdc`、
`semantics.json` 和 XML 格式使用的 STL 网格。USD 内嵌网格。
`model.config` 提供 SDF 模型包描述，根清单记录文件哈希。
生成的 ROS 2 包名为 `rm_map_equipment`，可复制到工作空间 `src/`，
运行 `colcon build` 并加载工作空间环境，以解析网格 URI。同名生成包只安装一份。

| 格式 | 表达方式 | 用途 |
|---|---|---|
| SDF 1.11 | 原生转动、滑动关节，运动学连杆，关闭重力 | 使用方提供连杆姿态或引擎控制器 |
| URDF | 原生关节树，逐连杆可视及碰撞网格 | ROS 模型与关节状态可视化 |
| USD | 物理关节与运动学刚体，通过局部关节坐标系表达任意轴 | USD、Isaac 资源导入和指定运动 |

所有文件保留源设备坐标。部分提取设备的局部竖直轴是 Y，不能按查看器的上轴
猜测摆放方式。`semantics.json` 保留设备到赛场的变换矩阵，组装时应用一次。
USD 声明赛场的 Z 向上约定，但不会隐式旋转设备顶点。

## 保留内容

侧车保留完整的可视、碰撞语义绑定，包括装甲尺寸和类别、LED 通道、队伍颜色、
图层、规则依据和演示运动描述，并映射语义 ID 与导出连杆名称。
可视与碰撞网格分别使用各自绑定，不要求节点编号一致。
USD 也写入节点和关节自定义数据。材质保留基础颜色，不转换纹理及其他 PBR 参数。
侧车中的原 glTF 节点编号仍指向源文件；读取新格式时使用导出网格记录和连杆名称映射。

## 运动学与动力学边界

这些 CAD 装配没有可靠的质量、惯量、电机力矩及速度数据，因此不填写惯性参数
或执行器。URDF 必填的力矩、速度字段用零作为明确的兼容占位值，并非实测限制。
关节状态可视化可直接使用，动力学仿真或运动规划需要先补齐真实参数及控制配置。
SDF、USD 引擎的默认质量也不是实测值。根连杆是模型锚点，由仿真器决定如何连接世界。

参考资源共导出八个可动关节：能量机关两个、前哨站一个、基地护盾三个、
基地轨道靶一个、飞镖窗口一个。行程常量及其依据保持不变。
科技核心六个 `frames_only` 轴导出为固定参考坐标系，元数据保留原关节定义。
不把预览角度当作机械限位，也不把演示机械臂绑定升级为物理模型。

不生成比赛控制器或动画。使用方可以调用 `articulated_scene.link_poses`
计算设备局部连杆姿态，输入单位为米和弧度。函数拒绝未知关节、越界坐标及
固定参考轴的非零运动。正弦轨道运动、护盾开合仍由现有预览脚本负责。

## 验证与规范

测试在非零关节坐标下对比源 GLB 与导出变换，覆盖旋转父坐标系、串联关节、
USD 任意轴和碰撞分离。五个本地参考设备均通过 `check_urdf`、libsdformat 15
及 OpenUSD 解析。[参考验证报告](../articulated-validation.json)记录源哈希，
静止及非零关节坐标下的 STL 坐标最大误差低于 4.3e-8 米。79 项 Python
测试全部通过。这验证模型结构及几何导出，不代表已测试 Gazebo、Isaac
控制器行为。本环境未运行 ROS 工作空间构建。

适配器遵循官方 [SDF 运动学规范](https://sdformat.org/tutorials/specification/spec_model_kinematics/)、
[ROS URDF 关节文档](https://docs.ros.org/en/humble/Tutorials/URDF/Building-a-Movable-Robot-Model-with-URDF.html)
和 [USD Physics 模式](https://openusd.org/release/api/usd_physics_page_front.html)。
