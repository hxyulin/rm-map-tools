//! Streaming STEP Part 21 (ISO 10303-21) tooling for very large files.
//!
//! The crate never builds a typed entity graph. Everything hangs off byte
//! ranges into a memory-mapped file, so the original text of an entity is
//! always at hand. It works in layers:
//!
//! * [`scan`]: a byte-level tokeniser that finds every `#id=TYPE(...);`
//!   instance in a memory-mapped file, in parallel over chunks aligned to
//!   entity starts, recording only id, type, byte range and outgoing
//!   references (string literals and comments are skipped).
//! * [`index`]: the resulting columnar [`Index`], with an id-to-row table,
//!   per-entity text access and an optional binary sidecar file so a 1 GB
//!   file is indexed once and reused.
//! * [`model`]: the product / assembly / body / style [`Model`] built from
//!   the index for AP203/AP214 files as exported by Creo and ST-Developer:
//!   ownership of shape representations, assembly occurrences, bodies,
//!   face traversal, effective face colours and vertex bounding boxes.
//! * [`split`]: a lossless per-product [`Splitter`]. Byte ranges are the
//!   whole point: a part copies the original entity text verbatim and only
//!   re-emits the few list-carrying boilerplate entities.
//! * [`decode`]: helpers for reading argument text without a full parser
//!   (string escapes, numbers, enumerations).
//!
//! # Examples
//!
//! Index a file, look at the model, and split one product into a
//! standalone part:
//!
//! ```
//! use step21::{Index, Model, Splitter};
//! use step21::split::{part_filename, Scratch};
//!
//! // A minimal Part 21 file: one product owning one solid.
//! let step = std::env::temp_dir().join("step21-doctest-overview.stp");
//! std::fs::write(
//!     &step,
//!     "ISO-10303-21;\n\
//!      HEADER;\nENDSEC;\nDATA;\n\
//!      #1=PRODUCT('plate','plate','',(#4));\n\
//!      #2=PRODUCT_DEFINITION_FORMATION('','',#1);\n\
//!      #3=PRODUCT_DEFINITION('','',#2,$);\n\
//!      #4=PRODUCT_CONTEXT('','part definition',$);\n\
//!      #5=PRODUCT_DEFINITION_SHAPE('','',#3);\n\
//!      #6=MANIFOLD_SOLID_BREP('base',#7);\n\
//!      #7=CLOSED_SHELL('',(#8));\n\
//!      #8=ADVANCED_FACE('',(#9),#14,.T.);\n\
//!      #9=FACE_OUTER_BOUND('',#10,.T.);\n\
//!      #10=EDGE_LOOP('',(#11));\n\
//!      #11=ORIENTED_EDGE('',*,*,#12,.T.);\n\
//!      #12=EDGE_CURVE('',#13,#13,#15,.T.);\n\
//!      #13=VERTEX_POINT('',#16);\n\
//!      #14=PLANE('',#23);\n\
//!      #15=LINE('',#16,#17);\n\
//!      #16=CARTESIAN_POINT('',(0.,0.,0.));\n\
//!      #17=VECTOR('',#18,1.);\n\
//!      #18=DIRECTION('',(1.,0.,0.));\n\
//!      #19=SHAPE_DEFINITION_REPRESENTATION(#5,#20);\n\
//!      #20=ADVANCED_BREP_SHAPE_REPRESENTATION('plate',(#6),#21);\n\
//!      #21=(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNIT_ASSIGNED_CONTEXT((#22))REPRESENTATION_CONTEXT('',''));\n\
//!      #22=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));\n\
//!      #23=AXIS2_PLACEMENT_3D('',#16,$);\n\
//!      ENDSEC;\nEND-ISO-10303-21;\n",
//! )?;
//!
//! let ix = Index::build(&step)?;
//!
//! // Entity text is read straight from the mapped file.
//! let row = ix.row(1).unwrap();
//! assert_eq!(ix.type_name(row), "PRODUCT");
//!
//! let m = Model::new(&ix);
//! assert_eq!(m.products.len(), 1);
//! let name = m.product_name(m.products[0]);
//! assert_eq!(name, "plate");
//!
//! let sp = Splitter::new(&ix, &m);
//! let mut scratch = Scratch::new(&ix);
//! let product = sp.products()[0];
//! let closure = sp.closure(product, &mut scratch);
//! // This file holds exactly one product, so the part keeps every entity.
//! assert_eq!(closure.rows.len(), ix.len());
//!
//! let filename = part_filename(&name, ix.ids()[product as usize]);
//! assert_eq!(filename, "plate-1.stp");
//! let mut out = Vec::new();
//! sp.write_part(&closure, &mut out)?;
//! # Ok::<(), Box<dyn std::error::Error>>(())
//! ```

pub mod decode;
pub mod index;
pub mod model;
pub mod scan;
pub mod split;

pub use index::{Index, IndexError};
pub use model::Model;
pub use split::Splitter;
