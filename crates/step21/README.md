# step21

Streaming STEP Part 21 (ISO 10303-21) tooling for very large files: a
parallel byte-level scanner, a columnar entity index with an optional
on-disk sidecar, a product / assembly / body / style model for AP203 and
AP214 files, and a lossless per-product splitter that copies entity text
verbatim.

It was written to take apart the 1 GB RoboMaster arena releases in seconds
(index at about 1 s per GB, split in a few seconds) without ever building a
typed entity graph; see the
[rm-map-tools](https://github.com/hxyulin/rm-map-tools) repository for the
tooling built on it, the measured proof that the split is lossless, and
notes on what the DJI files actually contain.

```rust
use std::{fs::File, io::BufWriter, path::Path};
use step21::{Index, Model, Splitter};
use step21::split::{Scratch, part_filename};

let ix = Index::build(Path::new("field.stp"))?;   // or Index::load(sidecar)
let m = Model::new(&ix);
let sp = Splitter::new(&ix, &m);
let mut scratch = Scratch::new(&ix);
for p in sp.products() {
    let closure = sp.closure(p, &mut scratch);
    let name = m.product_name.get(&p).map(String::as_str).unwrap_or("unnamed");
    let mut w = BufWriter::new(File::create(part_filename(name, ix.ids()[p as usize]))?);
    sp.write_part(&closure, &mut w)?;
}
```

Licensed under MIT or Apache-2.0, at your option.
