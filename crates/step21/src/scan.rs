//! Byte-level scanner for the DATA section of a Part 21 file.
//!
//! Grammar actually needed (everything hit in the DJI files):
//!
//! * an instance is `#id=` then an optional simple type name then `(` ... `;`;
//!   an empty type name means a complex instance `#id=(A(...)B(...));` and is
//!   recorded under the pseudo type [`CPLX`];
//! * instances wrap across lines and are terminated by the first `;` that is
//!   outside a string literal and outside a comment;
//! * string literals are `'...'` with `''` as the escaped quote; they may
//!   contain `;`, `(`, `#` and `\X2\...\X0\` escapes, so `#` inside them is
//!   never a reference;
//! * `/* ... */` comments may appear anywhere (the V1.2.0 header has them).

use memchr::{memchr, memmem};

/// Pseudo type name used for complex instances, which have no single type.
pub const CPLX: &str = "CPLX";

/// One scanned instance: where it is and which entities it references.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Scanned {
    /// Entity id (the number after `#`).
    pub id: u32,
    /// Index into the chunk-local type table.
    pub type_id: u16,
    /// Byte offset of the `#` that starts the instance.
    pub start: u64,
    /// Length in bytes up to and including the terminating `;`.
    pub len: u32,
    /// Offset into the chunk-local `refs` array where this instance's references begin.
    pub ref_start: u64,
}

/// Result of scanning one byte range.
#[derive(Debug, Default)]
pub struct Chunk {
    /// Distinct instance type names in order of first appearance; the
    /// pseudo type [`CPLX`] stands in for complex instances.
    pub type_names: Vec<String>,
    /// Scanned instances in file order.
    pub entities: Vec<Scanned>,
    /// Outgoing references of all entities, concatenated in order.
    pub refs: Vec<u32>,
}

/// Scan `data[start..end]` for instances. `start` must be at or before the
/// `#` of an instance start (or whitespace before one); `end` must be at an
/// instance start boundary or the end of the data. Offsets are absolute.
///
/// # Errors
///
/// [`ScanError::Unterminated`] if the slice ends inside an instance.
pub fn scan_chunk(data: &[u8], start: usize, end: usize) -> Result<Chunk, ScanError> {
    let mut out = Chunk::default();
    let mut type_ids: Vec<(Vec<u8>, u16)> = Vec::new();
    let mut pos = start;
    while let Some(head) = find_head(data, pos, end) {
        let ty = &data[head.name_start..head.name_end];
        let type_id = match type_ids.iter().find(|(n, _)| n == ty) {
            Some((_, t)) => *t,
            None => {
                let t = out.type_names.len() as u16;
                out.type_names.push(if ty.is_empty() {
                    CPLX.to_string()
                } else {
                    String::from_utf8_lossy(ty).into_owned()
                });
                type_ids.push((ty.to_vec(), t));
                t
            }
        };
        let ref_start = out.refs.len() as u64;
        let body_end =
            scan_body(data, head.body_start, &mut out.refs).ok_or(ScanError::Unterminated {
                id: head.id,
                offset: head.start,
            })?;
        out.entities.push(Scanned {
            id: head.id,
            type_id,
            start: head.start as u64,
            len: (body_end - head.start) as u32,
            ref_start,
        });
        pos = body_end;
    }
    Ok(out)
}

#[derive(Debug, thiserror::Error)]
pub enum ScanError {
    /// The data ended before an instance found its terminating `;`.
    #[error("unterminated instance #{id} at byte {offset}")]
    Unterminated { id: u32, offset: usize },
}

struct Head {
    id: u32,
    start: usize,
    name_start: usize,
    name_end: usize,
    body_start: usize,
}

/// Find the next `#id=NAME(` at or after `pos` and before `end`.
fn find_head(data: &[u8], mut pos: usize, end: usize) -> Option<Head> {
    while pos < end {
        let hash = pos + memchr(b'#', &data[pos..end])?;
        let mut p = hash + 1;
        let mut id: u64 = 0;
        let digits_start = p;
        while p < end && data[p].is_ascii_digit() {
            id = id * 10 + (data[p] - b'0') as u64;
            p += 1;
        }
        if p == digits_start || p >= end || data[p] != b'=' || id > u32::MAX as u64 {
            pos = hash + 1;
            continue;
        }
        p += 1;
        while p < end && data[p].is_ascii_whitespace() {
            p += 1;
        }
        let name_start = p;
        while p < end
            && (data[p].is_ascii_uppercase() || data[p].is_ascii_digit() || data[p] == b'_')
        {
            p += 1;
        }
        let name_end = p;
        while p < end && data[p].is_ascii_whitespace() {
            p += 1;
        }
        if p >= end || data[p] != b'(' {
            pos = hash + 1;
            continue;
        }
        return Some(Head {
            id: id as u32,
            start: hash,
            name_start,
            name_end,
            body_start: p,
        });
    }
    None
}

/// Tokenise from `pos` to the terminating `;`, pushing references.
/// Returns the offset just past the `;`.
fn scan_body(data: &[u8], mut pos: usize, refs: &mut Vec<u32>) -> Option<usize> {
    let n = data.len();
    while pos < n {
        match data[pos] {
            b'\'' => {
                // string literal with '' escapes
                pos += 1;
                loop {
                    let q = pos + memchr(b'\'', &data[pos..])?;
                    if q + 1 < n && data[q + 1] == b'\'' {
                        pos = q + 2;
                    } else {
                        pos = q + 1;
                        break;
                    }
                }
            }
            b'#' => {
                let mut p = pos + 1;
                let mut id: u64 = 0;
                while p < n && data[p].is_ascii_digit() {
                    id = id * 10 + (data[p] - b'0') as u64;
                    p += 1;
                }
                if p > pos + 1 && id <= u32::MAX as u64 {
                    refs.push(id as u32);
                }
                pos = p;
            }
            b';' => return Some(pos + 1),
            b'/' if pos + 1 < n && data[pos + 1] == b'*' => {
                let close = memmem::find(&data[pos + 2..], b"*/")?;
                pos = pos + 2 + close + 2;
            }
            _ => pos += 1,
        }
    }
    None
}

/// Byte offset just past the `DATA;` line that opens the instance section,
/// or `None` if the file has none.
pub fn data_section_start(data: &[u8]) -> Option<usize> {
    memmem::find(data, b"\nDATA;").map(|p| p + b"\nDATA;".len())
}

/// Chunk boundaries for parallel scanning: `nchunks` ranges between
/// `data_start` and the end of the data, aligned to a line that starts an
/// instance (`\n#<digits>=`).
pub fn chunk_bounds(data: &[u8], data_start: usize, nchunks: usize) -> Vec<usize> {
    let size = data.len();
    let mut bounds = vec![data_start];
    for i in 1..nchunks {
        let approx = data_start + (size - data_start) / nchunks * i;
        let b = next_instance_line(data, approx).unwrap_or(size);
        if b > *bounds.last().unwrap_or(&0) {
            bounds.push(b);
        }
    }
    if *bounds.last().unwrap_or(&0) < size {
        bounds.push(size);
    }
    bounds
}

/// Offset of the `#` of the next `\n#<digits>=` at or after `from`.
fn next_instance_line(data: &[u8], mut from: usize) -> Option<usize> {
    loop {
        let nl = from + memchr(b'\n', &data[from..])?;
        let mut p = nl + 1;
        if p < data.len() && data[p] == b'#' {
            p += 1;
            let ds = p;
            while p < data.len() && data[p].is_ascii_digit() {
                p += 1;
            }
            if p > ds && p < data.len() && data[p] == b'=' {
                return Some(nl + 1);
            }
        }
        from = nl + 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scans_strings_refs_and_comments() {
        let src = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1=PRODUCT('a;b''#9',#2,\n#3);\n#2=(A(#4)B(/* #5 */ 'x'));\n#7=CARTESIAN_POINT('',(1.,2.,3.));\nENDSEC;\nEND-ISO-10303-21;\n";
        let ds = data_section_start(src).unwrap();
        let c = scan_chunk(src, ds, src.len()).unwrap();
        assert_eq!(c.type_names, vec!["PRODUCT", "CPLX", "CARTESIAN_POINT"]);
        assert_eq!(c.entities.len(), 3);
        assert_eq!(c.refs, vec![2, 3, 4]);
        let e = c.entities[0];
        assert_eq!(
            &src[e.start as usize..(e.start + e.len as u64) as usize],
            b"#1=PRODUCT('a;b''#9',#2,\n#3);"
        );
        let bounds = chunk_bounds(src, ds, 2);
        assert!(bounds.windows(2).all(|w| w[0] < w[1]));
    }
}
