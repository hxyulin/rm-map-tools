# step21

[English](README.md) · [简体中文](README.zh-CN.md)

Streaming STEP Part 21 (ISO 10303-21) tooling for very large files: index a
1 GB CAD release in about a second, walk its products and assemblies, and
split it into standalone part files — without ever building a typed entity
graph.

## Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Design notes](#design-notes)
- [Related work](#related-work)
- [License](#license)

## Features

- **Parallel byte-level scanner.** Finds every `#id=TYPE(...);` instance in
  a memory-mapped file, chunk by chunk, skipping string literals and
  `/* */` comments.
- **Columnar entity index.** Per entity: id, type, byte range, and outgoing
  references, plus an optional on-disk sidecar so a file is indexed once
  and reused.
- **Product / assembly / body / style model.** For AP203 and AP214 files as
  exported by Creo and ST-Developer: shape representation ownership,
  assembly occurrences, body-to-face traversal, effective face colours, and
  vertex bounding boxes.
- **Lossless per-product splitter.** Part files copy the original entity
  text byte for byte under the original ids; only the few list-carrying
  boilerplate entities are re-emitted, with their reference lists filtered.

## Installation

```sh
cargo add step21
```

## Usage

Build an index once (or load a saved sidecar), inspect the model, and write
one standalone part file per product:

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

Entity text is read straight from the mapped file — `ix.text(row)` returns
the exact bytes from `#` to `;` — and argument text decodes with
[`decode::decode_string`](https://docs.rs/step21/latest/step21/decode/fn.decode_string.html).

## Design notes

The crate never parses entities into typed data. It records byte ranges
into a memory-mapped file and reads the original text on demand, so memory
use is proportional to the number of entities and references rather than to
the geometry. The splitter exploits the same property: a part is mostly a
copy of source byte ranges, written under the original entity ids so the
output can be compared against the input and against the validated Python
prototype it reproduces.

## Related work

step21 is the parsing layer of
[rm-map-tools](https://github.com/hxyulin/rm-map-tools), which splits the
1 GB RoboMaster arena releases and exports field assets for viewers and
simulators. That repository documents the
[STEP file internals](https://github.com/hxyulin/rm-map-tools/blob/main/docs/step-internals.md)
observed in the DJI files and the
[proof that the split is lossless](https://github.com/hxyulin/rm-map-tools/blob/main/docs/split-proof.md).

## License

Licensed under [MIT](LICENSE-MIT) or
[Apache-2.0](LICENSE-APACHE), at your option.
