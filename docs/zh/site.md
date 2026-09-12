# 文档网站

[文档](index.md) · [交互查看器](viewer.md) · [English](../site.md)

网站使用 VitePress。指南保持 `docs/` 中的普通 Markdown，可直接在 GitHub 阅读；交互模型检查由 Vue 组件实现。文档没有需要单独维护的第二份副本。锁文件固定 VitePress 1.6.4，并覆写 Vite 6.4.3 以使用修补后的开发服务器。

## 本地运行

安装 Node.js 22 或更高版本，然后在仓库根目录运行：

```sh
npm ci
npm run docs:models
npm run docs:dev
```

打开 VitePress 打印的地址，位于 `/rm-map-tools/` 下。检查与构建：

```sh
npm run docs:check
npm run docs:test
npm run docs:build
npm run docs:check -- --built
npm run docs:preview
```

构建输出在 `docs/.vitepress/dist/`。依赖与构建输出不进入 Git。运行查看器不需要 Python 和 Rust；链接检查器使用 Python 3。

## 发布到 GitHub Pages

在仓库 Settings → Pages 中选择 **GitHub Actions** 作为构建来源。文档工作流会构建拉取请求，并在推送 `main` 或手动触发时发布。工作流成功部署后，站点地址为 `https://hxyulin.github.io/rm-map-tools/`。

若是 fork，请修改 `docs/.vitepress/config.mjs` 中的仓库链接和 `base`；`base` 必须与 GitHub Pages 的仓库路径一致。参见 [VitePress 部署文档](https://vitepress.dev/guide/deploy)。

## 编辑文档

README 聚焦项目简介与上手步骤；操作流程放入主指南，设置放入技术参考，实测结果放入带日期的基准报告。新增指南时，同时更新文档索引和侧边栏。

主指南是双语的：每个翻译页面在 `docs/zh/` 下有一个对应文件；站点导航栏的语言切换在两者之间切换，GitHub 上每个文件只有一种语言。新增指南时，请同时创建 `docs/<name>.md` 和 `docs/zh/<name>.md`，并在 `docs/.vitepress/config.mjs` 的两个语言侧边栏中登记。深度技术参考和带日期的基准报告仅保留英文，中文页面以 `../` 路径链接过去。`docs/simplification-results.md` 由脚本按实测数据更新，没有中文副本。

构建网站时，`docs/` 之外的仓库链接会被改写为 GitHub 地址；Markdown 为仓库浏览保留原始相对路径。查看器组件由主题注册，页面中用 `<ModelViewer />` 嵌入；组件只在浏览器挂载，静态构建不依赖 WebGL。

## 模型与运动

查看器使用 Three.js 和 URDFLoader。其 SDF 适配器接受本仓库关节导出器输出的设备结构；它不实现仿真器，也不泛化替代 SDF 框架语义。

目录包含基地、能量机关、前哨站、飞镖站和科技核心五个 CAD 模型，每个绑定的可动实体都有控件。由现有参考资源包生成：

```sh
npm run docs:models
npm run docs:test-models
```

该过程使用 `ocpenv` Python 环境和 `../assets/rm2026-reference`。可用 `scripts/prepare_viewer_models.py --source PATH` 指定其他来源。输出到 `docs/public/models/`，该目录必须尚不存在；重建时删除该生成目录，或用 `--out` 另选输出。

生成器对照语义侧车校验每个源 GLB，保留运动节点层级，并用既有绑定辅助创建独立的 Core 展示绑定；它写出 gzip 压缩的 GLB 和记录名称、关节范围、源哈希与输出哈希的目录。浏览器在绑定关节前先校验解压后的模型哈希。包约 60 MB，每个模型按需下载。

模型不进入 Git。要把同一模型包提供给 GitHub Pages，先打包并托管到一个可下载的地址：

```sh
mkdir -p out
python3 -m zipfile -c out/docs-viewer-models.zip docs/public/models
```

把该压缩包地址设为仓库 Actions 变量 `DOCS_MODELS_URL`。文档工作流会把它下载到 `docs/public/`，测试全部五个模型，并纳入 Pages 产物；缺少目录模型时工作流不会部署查看器。拉取请求仍可在没有模型包的情况下构建 Markdown。生成的压缩包仍保留 DJI / RoboMaster 几何的归属与条款。

录制的 GIF/MP4 文件和独立的截帧/录像脚本已移除。数值化运动验证、源审计报告和可复用的关节/绑定辅助仍保留，静态几何对比图也作为证据保留。
