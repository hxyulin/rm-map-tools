//! Columnar entity index of a Part 21 file plus its binary sidecar format.

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufReader, BufWriter, Read, Write};
use std::path::{Path, PathBuf};

use memmap2::Mmap;
use rayon::prelude::*;

use crate::scan::{self, Chunk};

/// Position of an entity in the index arrays (file order).
pub type Row = u32;

const MAGIC: &[u8; 8] = b"P21IDX\0\x01";

#[derive(Debug, thiserror::Error)]
pub enum IndexError {
    #[error("io error on {path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("{0} has no DATA section")]
    NoData(PathBuf),
    #[error(transparent)]
    Scan(#[from] scan::ScanError),
    #[error("{0} is not a step21 index file")]
    BadMagic(PathBuf),
    #[error("index {index} was built from {step} of {expected} bytes, file now has {actual} bytes")]
    Stale {
        index: PathBuf,
        step: PathBuf,
        expected: u64,
        actual: u64,
    },
}

fn io(path: &Path) -> impl FnOnce(std::io::Error) -> IndexError + '_ {
    move |source| IndexError::Io {
        path: path.to_path_buf(),
        source,
    }
}

/// Entity index of one file: per entity id, type, byte range and outgoing
/// references, with the source file memory-mapped for text access.
pub struct Index {
    source: PathBuf,
    data_start: u64,
    type_names: Vec<String>,
    type_ids: HashMap<String, u16>,
    ids: Vec<u32>,
    types: Vec<u16>,
    starts: Vec<u64>,
    lens: Vec<u32>,
    ref_start: Vec<u64>,
    refs: Vec<u32>,
    row_of_id: Vec<i32>,
    mmap: Mmap,
}

#[allow(unsafe_code)]
fn map_file(path: &Path) -> Result<Mmap, IndexError> {
    let file = File::open(path).map_err(io(path))?;
    // SAFETY: the archive files are never modified while indexed (they are
    // checksummed read-only inputs); a concurrent truncation would at worst
    // fault this process, which is acceptable for a command-line tool.
    unsafe { Mmap::map(&file) }.map_err(io(path))
}

impl Index {
    /// Scan `path` in parallel and build the index in memory.
    pub fn build(path: &Path) -> Result<Index, IndexError> {
        let mmap = map_file(path)?;
        let data: &[u8] = &mmap;
        let data_start =
            scan::data_section_start(data).ok_or_else(|| IndexError::NoData(path.to_path_buf()))?;
        let nchunks = rayon::current_num_threads() * 4;
        let bounds = scan::chunk_bounds(data, data_start, nchunks);
        let chunks: Vec<Chunk> = bounds
            .par_windows(2)
            .map(|w| scan::scan_chunk(data, w[0], w[1]))
            .collect::<Result<_, _>>()?;
        let n: usize = chunks.iter().map(|c| c.entities.len()).sum();
        let nrefs: usize = chunks.iter().map(|c| c.refs.len()).sum();
        let mut type_names: Vec<String> = Vec::new();
        let mut type_ids: HashMap<String, u16> = HashMap::new();
        let mut ids = Vec::with_capacity(n);
        let mut types = Vec::with_capacity(n);
        let mut starts = Vec::with_capacity(n);
        let mut lens = Vec::with_capacity(n);
        let mut ref_start = Vec::with_capacity(n + 1);
        let mut refs = Vec::with_capacity(nrefs);
        for c in chunks {
            let remap: Vec<u16> = c
                .type_names
                .iter()
                .map(|name| {
                    *type_ids.entry(name.clone()).or_insert_with(|| {
                        type_names.push(name.clone());
                        (type_names.len() - 1) as u16
                    })
                })
                .collect();
            let base = refs.len() as u64;
            for e in &c.entities {
                ids.push(e.id);
                types.push(remap[e.type_id as usize]);
                starts.push(e.start);
                lens.push(e.len);
                ref_start.push(base + e.ref_start);
            }
            refs.extend_from_slice(&c.refs);
        }
        ref_start.push(refs.len() as u64);
        let row_of_id = build_row_table(&ids);
        Ok(Index {
            source: path.to_path_buf(),
            data_start: data_start as u64,
            type_names,
            type_ids,
            ids,
            types,
            starts,
            lens,
            ref_start,
            refs,
            row_of_id,
            mmap,
        })
    }

    /// Write the sidecar file.
    pub fn save(&self, path: &Path) -> Result<(), IndexError> {
        let mut w = BufWriter::new(File::create(path).map_err(io(path))?);
        let e = io(path);
        let r = (|| -> std::io::Result<()> {
            w.write_all(MAGIC)?;
            let src = self.source.to_string_lossy();
            for v in [
                self.mmap.len() as u64,
                self.data_start,
                self.ids.len() as u64,
                self.refs.len() as u64,
                self.type_names.len() as u64,
                src.len() as u64,
            ] {
                w.write_all(&v.to_le_bytes())?;
            }
            w.write_all(src.as_bytes())?;
            for t in &self.type_names {
                w.write_all(&(t.len() as u16).to_le_bytes())?;
                w.write_all(t.as_bytes())?;
            }
            write_u32s(&mut w, &self.ids)?;
            write_u16s(&mut w, &self.types)?;
            write_u64s(&mut w, &self.starts)?;
            write_u32s(&mut w, &self.lens)?;
            write_u64s(&mut w, &self.ref_start)?;
            write_u32s(&mut w, &self.refs)?;
            w.flush()
        })();
        r.map_err(e)
    }

    /// Load a sidecar written by [`Index::save`]; the source file it names is
    /// memory-mapped again and must have the recorded size.
    pub fn load(path: &Path) -> Result<Index, IndexError> {
        let mut r = BufReader::new(File::open(path).map_err(io(path))?);
        let e = io(path);
        let mut magic = [0u8; 8];
        r.read_exact(&mut magic).map_err(io(path))?;
        if &magic != MAGIC {
            return Err(IndexError::BadMagic(path.to_path_buf()));
        }
        let mut hdr = [0u64; 6];
        for v in hdr.iter_mut() {
            *v = read_u64(&mut r).map_err(io(path))?;
        }
        let [size, data_start, n, nrefs, ntypes, src_len] = hdr;
        let mut src = vec![0u8; src_len as usize];
        r.read_exact(&mut src).map_err(io(path))?;
        let source = PathBuf::from(String::from_utf8_lossy(&src).into_owned());
        let mut type_names = Vec::with_capacity(ntypes as usize);
        for _ in 0..ntypes {
            let mut l = [0u8; 2];
            r.read_exact(&mut l).map_err(io(path))?;
            let mut name = vec![0u8; u16::from_le_bytes(l) as usize];
            r.read_exact(&mut name).map_err(io(path))?;
            type_names.push(String::from_utf8_lossy(&name).into_owned());
        }
        let type_ids = type_names
            .iter()
            .enumerate()
            .map(|(i, t)| (t.clone(), i as u16))
            .collect();
        let n = n as usize;
        let ids = read_u32s(&mut r, n).map_err(io(path))?;
        let types = read_u16s(&mut r, n).map_err(io(path))?;
        let starts = read_u64s(&mut r, n).map_err(io(path))?;
        let lens = read_u32s(&mut r, n).map_err(io(path))?;
        let ref_start = read_u64s(&mut r, n + 1).map_err(io(path))?;
        let refs = read_u32s(&mut r, nrefs as usize).map_err(e)?;
        let mmap = map_file(&source)?;
        if mmap.len() as u64 != size {
            return Err(IndexError::Stale {
                index: path.to_path_buf(),
                step: source,
                expected: size,
                actual: mmap.len() as u64,
            });
        }
        let row_of_id = build_row_table(&ids);
        Ok(Index {
            source,
            data_start,
            type_names,
            type_ids,
            ids,
            types,
            starts,
            lens,
            ref_start,
            refs,
            row_of_id,
            mmap,
        })
    }

    pub fn source(&self) -> &Path {
        &self.source
    }
    /// Whole file bytes.
    pub fn data(&self) -> &[u8] {
        &self.mmap
    }
    /// Everything up to and including `DATA;`.
    pub fn header(&self) -> &[u8] {
        &self.mmap[..self.data_start as usize]
    }
    pub fn len(&self) -> usize {
        self.ids.len()
    }
    pub fn is_empty(&self) -> bool {
        self.ids.is_empty()
    }
    pub fn ref_count(&self) -> usize {
        self.refs.len()
    }
    pub fn type_names(&self) -> &[String] {
        &self.type_names
    }
    pub fn type_id(&self, name: &str) -> Option<u16> {
        self.type_ids.get(name).copied()
    }
    pub fn ids(&self) -> &[u32] {
        &self.ids
    }
    pub fn types(&self) -> &[u16] {
        &self.types
    }
    pub fn max_id(&self) -> u32 {
        (self.row_of_id.len().saturating_sub(1)) as u32
    }
    /// Row of entity `id`, if it exists.
    #[inline]
    pub fn row(&self, id: u32) -> Option<Row> {
        match self.row_of_id.get(id as usize) {
            Some(&r) if r >= 0 => Some(r as Row),
            _ => None,
        }
    }
    #[inline]
    pub fn id(&self, row: Row) -> u32 {
        self.ids[row as usize]
    }
    #[inline]
    pub fn type_of(&self, row: Row) -> u16 {
        self.types[row as usize]
    }
    pub fn type_name(&self, row: Row) -> &str {
        &self.type_names[self.types[row as usize] as usize]
    }
    /// Referenced entity ids of `row`, in argument order.
    #[inline]
    pub fn refs_of(&self, row: Row) -> &[u32] {
        let r = row as usize;
        &self.refs[self.ref_start[r] as usize..self.ref_start[r + 1] as usize]
    }
    /// Byte range `[start, end)` of the instance text.
    #[inline]
    pub fn span(&self, row: Row) -> (usize, usize) {
        let s = self.starts[row as usize] as usize;
        (s, s + self.lens[row as usize] as usize)
    }
    /// Instance text from `#` to `;` inclusive.
    pub fn text(&self, row: Row) -> &[u8] {
        let (s, e) = self.span(row);
        &self.mmap[s..e]
    }
    /// Argument text between the type's `(` and the final `)`.
    pub fn args(&self, row: Row) -> &[u8] {
        let t = self.text(row);
        let open = memchr::memchr(b'(', t).map(|p| p + 1).unwrap_or(0);
        let close = memchr::memrchr(b')', t).unwrap_or(t.len());
        if close >= open {
            &t[open..close]
        } else {
            &t[open..]
        }
    }
    /// Rows of all entities whose type is one of `names`, ascending.
    pub fn rows_of(&self, names: &[&str]) -> Vec<Row> {
        let wanted: Vec<u16> = names.iter().filter_map(|n| self.type_id(n)).collect();
        if wanted.is_empty() {
            return Vec::new();
        }
        self.types
            .iter()
            .enumerate()
            .filter(|(_, t)| wanted.contains(t))
            .map(|(i, _)| i as Row)
            .collect()
    }
    /// Count of entities per type name, most frequent first.
    pub fn type_histogram(&self) -> Vec<(&str, usize)> {
        let mut counts = vec![0usize; self.type_names.len()];
        for &t in &self.types {
            counts[t as usize] += 1;
        }
        let mut v: Vec<(&str, usize)> = self
            .type_names
            .iter()
            .map(|s| s.as_str())
            .zip(counts)
            .collect();
        v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(b.0)));
        v
    }
}

fn build_row_table(ids: &[u32]) -> Vec<i32> {
    let max = ids.iter().copied().max().unwrap_or(0) as usize;
    let mut row = vec![-1i32; max + 1];
    for (i, &id) in ids.iter().enumerate() {
        row[id as usize] = i as i32;
    }
    row
}

fn write_u32s<W: Write>(w: &mut W, v: &[u32]) -> std::io::Result<()> {
    let mut buf = Vec::with_capacity(v.len() * 4);
    for x in v {
        buf.extend_from_slice(&x.to_le_bytes());
    }
    w.write_all(&buf)
}
fn write_u16s<W: Write>(w: &mut W, v: &[u16]) -> std::io::Result<()> {
    let mut buf = Vec::with_capacity(v.len() * 2);
    for x in v {
        buf.extend_from_slice(&x.to_le_bytes());
    }
    w.write_all(&buf)
}
fn write_u64s<W: Write>(w: &mut W, v: &[u64]) -> std::io::Result<()> {
    let mut buf = Vec::with_capacity(v.len() * 8);
    for x in v {
        buf.extend_from_slice(&x.to_le_bytes());
    }
    w.write_all(&buf)
}
fn read_u64<R: Read>(r: &mut R) -> std::io::Result<u64> {
    let mut b = [0u8; 8];
    r.read_exact(&mut b)?;
    Ok(u64::from_le_bytes(b))
}
fn read_u32s<R: Read>(r: &mut R, n: usize) -> std::io::Result<Vec<u32>> {
    let mut buf = vec![0u8; n * 4];
    r.read_exact(&mut buf)?;
    Ok(buf
        .as_chunks::<4>()
        .0
        .iter()
        .map(|c| u32::from_le_bytes(*c))
        .collect())
}
fn read_u16s<R: Read>(r: &mut R, n: usize) -> std::io::Result<Vec<u16>> {
    let mut buf = vec![0u8; n * 2];
    r.read_exact(&mut buf)?;
    Ok(buf
        .as_chunks::<2>()
        .0
        .iter()
        .map(|c| u16::from_le_bytes(*c))
        .collect())
}
fn read_u64s<R: Read>(r: &mut R, n: usize) -> std::io::Result<Vec<u64>> {
    let mut buf = vec![0u8; n * 8];
    r.read_exact(&mut buf)?;
    Ok(buf
        .as_chunks::<8>()
        .0
        .iter()
        .map(|c| u64::from_le_bytes(*c))
        .collect())
}
