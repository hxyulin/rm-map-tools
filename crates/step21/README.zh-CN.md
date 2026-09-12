# step21

[English](README.md) · [简体中文](README.zh-CN.md)

面向超大文件的 STEP Part 21（ISO 10303-21）流式处理工具：约一秒索引 1 GB
的 CAD 发布文件，遍历其中的产品与装配，并拆分为独立的零件文件——全程不
构建类型化的实体图。

## 目录

- [功能](#功能)
- [安装](#安装)
- [用法](#用法)
- [设计要点](#设计要点)
- [相关工作](#相关工作)
- [许可](#许可)

## 功能

- **并行字节级扫描器。** 在内存映射文件上按块找出每个 `#id=TYPE(...);`
  实体，正确跳过字符串字面量和 `/* */` 注释。
- **列式实体索引。** 记录每个实体的 id、类型、字节区间和对外引用，可选
  落盘 sidecar，一个文件只需索引一次，之后反复复用。
- **产品 / 装配 / 实体 / 样式模型。** 面向 Creo 与 ST-Developer 导出的
  AP203、AP214 文件：造型表示的归属、装配出现关系、实体到面的遍历、
  面的有效颜色以及顶点包围盒。
- **无损按产品拆分。** 零件文件按原 id 逐字节复制原始实体文本，仅少数
  携带引用列表的样板实体被重新输出，且列表被过滤为闭合集合。

## 安装

```sh
cargo add step21
```

## 用法

先建立索引（或加载已有 sidecar），查看模型，然后为每个产品写出一个独立
零件文件：

```rust
use std::{fs::File, io::BufWriter, path::Path};
use step21::{Index, Model, Splitter};
use step21::split::{part_filename, Scratch};

let sidecar = Path::new("field.p21idx");
let ix = match Index::load(sidecar) {
    Ok(ix) => ix,
    Err(_) => {
        let ix = Index::build(Path::new("field.stp"))?;
        ix.save(sidecar)?;
        ix
    }
};
let m = Model::new(&ix);
let sp = Splitter::new(&ix, &m);
let mut scratch = Scratch::new(&ix);
for p in sp.products() {
    let closure = sp.closure(p, &mut scratch);
    let name = m.product_name(p);
    let mut w = BufWriter::new(File::create(part_filename(name, ix.ids()[p as usize]))?);
    sp.write_part(&closure, &mut w)?;
}
```

实体文本直接从内存映射文件读取——`ix.text(row)` 返回从 `#` 到 `;` 的
原始字节——参数文本可用
[`decode::decode_string`](https://docs.rs/step21/latest/step21/decode/fn.decode_string.html)
解码。

## 设计要点

本crate从不把实体解析为类型化数据，而是记录内存映射文件中的字节区间，
按需读取原始文本，因此内存占用与实体和引用的数量成正比，与几何复杂度无
关。拆分器利用同一性质：零件文件大部分是对源文件字节区间的复制，并保留
原始实体 id，因而输出可以直接与输入、以及与经验证的 Python
原型（本实现精确复刻其行为）进行比较。

## 相关工作

step21 是 [rm-map-tools](https://github.com/hxyulin/rm-map-tools)
的解析层；该项目拆分 1 GB 的 RoboMaster 赛场发布文件，并导出供查看器和
仿真器使用的场地资源。仓库内另有 DJI 文件的
[STEP 文件内部结构](https://github.com/hxyulin/rm-map-tools/blob/main/docs/step-internals.md)
笔记，以及[拆分无损性的证明](https://github.com/hxyulin/rm-map-tools/blob/main/docs/split-proof.md)。

## 许可

采用 [MIT](LICENSE-MIT) 或 [Apache-2.0](LICENSE-APACHE) 双重许可，任选其一。
