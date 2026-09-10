//! Streaming STEP Part 21 (ISO 10303-21) tooling for very large files.
//!
//! The crate never builds a typed entity graph. It works in three layers:
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
//!
//! Byte ranges are the whole point: a lossless split copies the original
//! entity text verbatim and only re-emits the few list-carrying entities.

pub mod decode;
pub mod index;
pub mod model;
pub mod scan;

pub use index::{Index, IndexError};
pub use model::Model;
pub mod split;
pub use split::Splitter;
