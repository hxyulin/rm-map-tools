//! Lossless text-level per-product split.
//!
//! A part file for a product contains
//!
//! * the forward closure of the product's `SHAPE_DEFINITION_REPRESENTATION`s
//!   and of the `SHAPE_REPRESENTATION_RELATIONSHIP`s between its own
//!   representations (geometry, topology, placements, units and contexts,
//!   product / PDM chain);
//! * every `STYLED_ITEM` / `OVER_RIDING_STYLED_ITEM` whose target is in that
//!   closure, with its style chain;
//! * reverse-referenced boilerplate (material properties, product category,
//!   application protocol, `CC_DESIGN_*` assignments, layers, presentation
//!   representation) whose reference lists are filtered to the closure.
//!
//! Entity text is copied byte for byte with its original id; only the
//! list-filtered boilerplate is re-emitted. The algorithm reproduces
//! `prototype/p21split.py` exactly (same rounds, same list wrapping), so the
//! Rust output can be compared with the validated Python output with `cmp`.

use std::collections::HashMap;
use std::io::{self, Write};

use crate::index::{Index, Row};
use crate::model::Model;

/// How an entity type refers back into a part's closure: by one reference
/// at a fixed argument position, or by a list of references that is
/// filtered to the closure when the entity is re-emitted.
#[derive(Debug, Clone, Copy)]
pub enum Reverse {
    /// The reference at this position in the entity's reference list
    /// (negative counts from the end) must be in the closure.
    Key(i32),
    /// The first parenthesised list of references is filtered to the closure.
    List,
}

/// Entity types that are never referenced from the geometry but belong to
/// the part when they point at it.
pub const REVERSE: [(&str, Reverse); 15] = [
    ("STYLED_ITEM", Reverse::Key(-1)),
    ("OVER_RIDING_STYLED_ITEM", Reverse::Key(-2)),
    ("PROPERTY_DEFINITION", Reverse::Key(-1)),
    ("PROPERTY_DEFINITION_REPRESENTATION", Reverse::Key(0)),
    ("APPLICATION_PROTOCOL_DEFINITION", Reverse::Key(-1)),
    ("PRODUCT_CATEGORY_RELATIONSHIP", Reverse::Key(-1)),
    ("APPROVAL_DATE_TIME", Reverse::Key(-1)),
    ("APPROVAL_PERSON_ORGANIZATION", Reverse::Key(1)),
    ("PRODUCT_RELATED_PRODUCT_CATEGORY", Reverse::List),
    ("PRESENTATION_LAYER_ASSIGNMENT", Reverse::List),
    (
        "MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION",
        Reverse::List,
    ),
    (
        "CC_DESIGN_PERSON_AND_ORGANIZATION_ASSIGNMENT",
        Reverse::List,
    ),
    ("CC_DESIGN_DATE_AND_TIME_ASSIGNMENT", Reverse::List),
    ("CC_DESIGN_SECURITY_CLASSIFICATION", Reverse::List),
    ("CC_DESIGN_APPROVAL", Reverse::List),
];

const LIST_FLAG: u32 = 1 << 31;

/// Where the filterable reference list sits inside a list-carrying entity.
#[derive(Debug, Clone)]
struct ListSpan {
    /// Byte range of the text before the list (from `#id=` on).
    prefix: (usize, usize),
    /// Byte range of the text after the list (up to and including `;`).
    suffix: (usize, usize),
    /// Entity ids in the list, in order.
    ids: Vec<u32>,
}

/// Precomputed reverse tables for splitting one file.
pub struct Splitter<'a> {
    pub ix: &'a Index,
    pub m: &'a Model<'a>,
    crlf: &'static [u8],
    /// CSR: for each row, the reverse-table rows that reference it. Entries
    /// with [`LIST_FLAG`] are list-carrying owners, the rest key-based.
    rev_start: Vec<u32>,
    rev_entries: Vec<u32>,
    list_spans: HashMap<Row, ListSpan>,
}

/// The closure of one product: which rows go into the part, and the
/// re-emitted text of the list-filtered rows.
pub struct Closure {
    /// Rows in the part, ascending.
    pub rows: Vec<Row>,
    /// Re-emitted text of the list-carrying boilerplate rows, by row.
    pub rewritten: HashMap<Row, Vec<u8>>,
}

/// Scratch space reused across products (one bit per entity).
pub struct Scratch {
    mask: Vec<bool>,
    marked: Vec<Row>,
}

impl Scratch {
    /// Allocate scratch space sized for `ix`, reusable for every product.
    pub fn new(ix: &Index) -> Scratch {
        Scratch {
            mask: vec![false; ix.len()],
            marked: Vec::new(),
        }
    }
    fn clear(&mut self) {
        for &r in &self.marked {
            self.mask[r as usize] = false;
        }
        self.marked.clear();
    }
    #[inline]
    fn mark(&mut self, r: Row) -> bool {
        let m = &mut self.mask[r as usize];
        if *m {
            false
        } else {
            *m = true;
            self.marked.push(r);
            true
        }
    }
}

impl<'a> Splitter<'a> {
    /// Precompute the reverse tables (which [`REVERSE`] rows point into
    /// each entity) for one file. This is the only setup cost; afterwards
    /// closures reuse it, so splitting many products is cheap.
    pub fn new(ix: &'a Index, m: &'a Model<'a>) -> Splitter<'a> {
        let crlf: &'static [u8] = if memchr::memmem::find(ix.header(), b"\r\n").is_some() {
            b"\r\n"
        } else {
            b"\n"
        };
        // Reverse pairs (target row -> table row) are built straight into CSR
        // form by counting: the layer assignments of V2.0.0 alone hold 88 M
        // references, too many to collect and sort.
        let mut list_spans = HashMap::new();
        let mut table_rows: Vec<(Row, Reverse)> = Vec::new();
        for (name, policy) in REVERSE {
            for row in ix.rows_of(&[name]) {
                table_rows.push((row, policy));
                if let Reverse::List = policy
                    && let Some(span) = list_span(ix, row)
                {
                    list_spans.insert(row, span);
                }
            }
        }
        let each_pair = |f: &mut dyn FnMut(Row, u32)| {
            for &(row, policy) in &table_rows {
                match policy {
                    Reverse::Key(k) => {
                        let refs = ix.refs_of(row);
                        let pos = if k < 0 {
                            refs.len() as i64 + k as i64
                        } else {
                            k as i64
                        };
                        if pos >= 0
                            && (pos as usize) < refs.len()
                            && let Some(key) = ix.row(refs[pos as usize])
                        {
                            f(key, row);
                        }
                    }
                    Reverse::List => {
                        for target in ix.refs_of(row).iter().filter_map(|&r| ix.row(r)) {
                            f(target, row | LIST_FLAG);
                        }
                    }
                }
            }
        };
        let mut rev_start = vec![0u32; ix.len() + 1];
        each_pair(&mut |t, _| rev_start[t as usize + 1] += 1);
        for i in 0..ix.len() {
            rev_start[i + 1] += rev_start[i];
        }
        let mut cursor = rev_start.clone();
        let mut rev_entries = vec![0u32; rev_start[ix.len()] as usize];
        each_pair(&mut |t, e| {
            rev_entries[cursor[t as usize] as usize] = e;
            cursor[t as usize] += 1;
        });
        // sorted per row so the closure scan can skip repeats
        for i in 0..ix.len() {
            let (a, b) = (rev_start[i] as usize, rev_start[i + 1] as usize);
            if b - a > 1 {
                rev_entries[a..b].sort_unstable();
            }
        }
        Splitter {
            ix,
            m,
            crlf,
            rev_start,
            rev_entries,
            list_spans,
        }
    }

    /// Products that own shape representations, in file order.
    pub fn products(&self) -> Vec<Row> {
        self.m
            .products
            .iter()
            .copied()
            .filter(|p| self.m.product_reps.contains_key(p))
            .collect()
    }

    /// Seed rows of a product: its shape definition representations and the
    /// relationships between its own representations.
    pub fn seeds(&self, product: Row) -> Vec<Row> {
        let m = self.m;
        let reps = m
            .product_reps
            .get(&product)
            .map(|v| v.as_slice())
            .unwrap_or(&[]);
        let mut seeds: Vec<Row> = reps
            .iter()
            .filter_map(|r| m.sdr_of_rep.get(r).copied())
            .collect();
        for &(row, r1, r2) in &m.srr {
            if let (Some(a), Some(b)) = (r1, r2)
                && reps.contains(&a)
                && reps.contains(&b)
            {
                seeds.push(row);
            }
        }
        seeds
    }

    fn forward_closure(&self, scratch: &mut Scratch, seeds: &[Row]) {
        let ix = self.ix;
        let mut frontier: Vec<Row> = Vec::new();
        for &s in seeds {
            if scratch.mark(s) {
                frontier.push(s);
            }
        }
        let mut next = Vec::new();
        while !frontier.is_empty() {
            for &r in &frontier {
                for x in ix.refs_of(r).iter().filter_map(|&x| ix.row(x)) {
                    if scratch.mark(x) {
                        next.push(x);
                    }
                }
            }
            std::mem::swap(&mut frontier, &mut next);
            next.clear();
        }
    }

    /// Compute the closure of one product.
    pub fn closure(&self, product: Row, scratch: &mut Scratch) -> Closure {
        let ix = self.ix;
        scratch.clear();
        self.forward_closure(scratch, &self.seeds(product));
        let mut rewritten: HashMap<Row, Vec<u8>> = HashMap::new();
        let mut scanned = 0usize;
        for _round in 0..6 {
            let before = scratch.marked.len();
            let mut add_plain: Vec<Row> = Vec::new();
            let mut add_rewritten: Vec<Row> = Vec::new();
            for i in scanned..before {
                let r = scratch.marked[i];
                let (a, b) = (
                    self.rev_start[r as usize] as usize,
                    self.rev_start[r as usize + 1] as usize,
                );
                let mut prev = u32::MAX;
                for &e in &self.rev_entries[a..b] {
                    if e == prev {
                        continue;
                    }
                    prev = e;
                    if e & LIST_FLAG != 0 {
                        let owner = e & !LIST_FLAG;
                        if rewritten.contains_key(&owner) {
                            continue;
                        }
                        let Some(span) = self.list_spans.get(&owner) else {
                            continue;
                        };
                        let keep: Vec<u32> = span
                            .ids
                            .iter()
                            .copied()
                            .filter(|&id| ix.row(id).is_some_and(|r| scratch.mask[r as usize]))
                            .collect();
                        if keep.is_empty() {
                            continue;
                        }
                        let mut text = ix.data()[span.prefix.0..span.prefix.1].to_vec();
                        self.emit_list(&keep, &mut text);
                        text.extend_from_slice(&ix.data()[span.suffix.0..span.suffix.1]);
                        rewritten.insert(owner, text);
                        add_rewritten.push(owner);
                    } else if !scratch.mask[e as usize] {
                        add_plain.push(e);
                    }
                }
            }
            scanned = before;
            for &r in add_rewritten.iter() {
                scratch.mark(r);
            }
            self.forward_closure(scratch, &add_plain);
            let mut kept: Vec<Row> = Vec::new();
            for r in &add_rewritten {
                let text = &rewritten[r];
                let from = memchr::memchr(b'=', text).map(|p| p + 1).unwrap_or(0);
                kept.extend(ref_ids(&text[from..]).filter_map(|id| ix.row(id)));
            }
            self.forward_closure(scratch, &kept);
            if scratch.marked.len() == before {
                break;
            }
        }
        let mut rows = scratch.marked.clone();
        rows.sort_unstable();
        Closure { rows, rewritten }
    }

    /// `(#a,#b,...)` wrapped at 72 columns like the exporters do.
    fn emit_list(&self, ids: &[u32], out: &mut Vec<u8>) {
        out.push(b'(');
        let mut line_len = 0usize;
        let mut first = true;
        for &id in ids {
            let tok = format!("#{id}");
            if !first && line_len + tok.len() + 1 > 72 {
                out.push(b',');
                out.extend_from_slice(self.crlf);
                line_len = 0;
            } else if !first {
                out.push(b',');
                line_len += 1;
            }
            out.extend_from_slice(tok.as_bytes());
            line_len += tok.len();
            first = false;
        }
        out.push(b')');
    }

    /// Write a part file for `closure`; returns the file size in bytes.
    ///
    /// # Errors
    ///
    /// Whatever the writer returns.
    pub fn write_part<W: Write>(&self, closure: &Closure, w: &mut W) -> io::Result<u64> {
        let ix = self.ix;
        let data = ix.data();
        w.write_all(ix.header())?;
        w.write_all(self.crlf)?;
        let nl = self.crlf.len() as u64;
        let mut nbytes = (ix.header().len() + self.crlf.len()) as u64;
        let rows = &closure.rows;
        let mut i = 0;
        while i < rows.len() {
            if let Some(text) = closure.rewritten.get(&rows[i]) {
                w.write_all(text)?;
                w.write_all(self.crlf)?;
                nbytes += text.len() as u64 + nl;
                i += 1;
                continue;
            }
            // run of consecutive verbatim rows: one copy of the byte range
            let mut j = i;
            while j + 1 < rows.len()
                && rows[j + 1] == rows[j] + 1
                && !closure.rewritten.contains_key(&rows[j + 1])
            {
                j += 1;
            }
            let (s, _) = ix.span(rows[i]);
            let (_, e) = ix.span(rows[j]);
            w.write_all(&data[s..e])?;
            w.write_all(self.crlf)?;
            nbytes += (e - s) as u64 + nl;
            i = j + 1;
        }
        w.write_all(b"ENDSEC;")?;
        w.write_all(self.crlf)?;
        w.write_all(b"END-ISO-10303-21;")?;
        w.write_all(self.crlf)?;
        Ok(nbytes + (b"ENDSEC;".len() + b"END-ISO-10303-21;".len()) as u64 + 2 * nl)
    }
}

/// Iterate `#<digits>` occurrences (anywhere, including inside strings, as
/// the prototype's regex did).
fn ref_ids(text: &[u8]) -> impl Iterator<Item = u32> + '_ {
    let mut pos = 0;
    std::iter::from_fn(move || {
        while pos < text.len() {
            let h = pos + memchr::memchr(b'#', &text[pos..])?;
            let mut p = h + 1;
            let mut id: u64 = 0;
            while p < text.len() && text[p].is_ascii_digit() {
                id = id * 10 + (text[p] - b'0') as u64;
                p += 1;
            }
            pos = p.max(h + 1);
            if p > h + 1 && id <= u32::MAX as u64 {
                return Some(id as u32);
            }
        }
        None
    })
}

/// Find the first parenthesised list made only of references,
/// `( #a , #b , ... )`, at or after the entity's opening parenthesis.
fn list_span(ix: &Index, row: Row) -> Option<ListSpan> {
    let (start, end) = ix.span(row);
    let text = &ix.data()[start..end];
    let mut from = memchr::memchr(b'(', text)?;
    while let Some(open) = memchr::memchr(b'(', &text[from..]).map(|p| p + from) {
        if let Some((close, ids)) = match_ref_list(&text[open..]) {
            return Some(ListSpan {
                prefix: (start, start + open),
                suffix: (start + open + close, end),
                ids,
            });
        }
        from = open + 1;
    }
    None
}

/// Match `\(\s*#\d+(?:\s*,\s*#\d+)*\s*\)` at the start of `t`; returns the
/// length matched and the ids.
fn match_ref_list(t: &[u8]) -> Option<(usize, Vec<u32>)> {
    let mut p = 1;
    let mut ids = Vec::new();
    let skip_ws = |p: &mut usize| {
        while *p < t.len() && t[*p].is_ascii_whitespace() {
            *p += 1;
        }
    };
    loop {
        skip_ws(&mut p);
        if t.get(p) != Some(&b'#') {
            return None;
        }
        p += 1;
        let ds = p;
        let mut id: u64 = 0;
        while p < t.len() && t[p].is_ascii_digit() {
            id = id * 10 + (t[p] - b'0') as u64;
            p += 1;
        }
        if p == ds {
            return None;
        }
        ids.push(id as u32);
        skip_ws(&mut p);
        match t.get(p) {
            Some(b',') => p += 1,
            Some(b')') => return Some((p + 1, ids)),
            _ => return None,
        }
    }
}

/// `sanitised-name-<product id>.stp`, as the prototype names parts.
///
/// # Examples
///
/// ```
/// use step21::split::part_filename;
/// assert_eq!(part_filename("BREP 9", 14249), "BREP_9-14249.stp");
/// assert_eq!(part_filename("", 5), "unnamed-5.stp");
/// ```
pub fn part_filename(name: &str, product_id: u32) -> String {
    let mut safe = String::new();
    let mut last_sep = false;
    for c in name.chars() {
        let ok = c.is_ascii_alphanumeric()
            || matches!(c, '_' | '.' | '-')
            || ('\u{4E00}'..='\u{9FFF}').contains(&c);
        if ok {
            safe.push(c);
            last_sep = false;
        } else if !last_sep {
            safe.push('_');
            last_sep = true;
        }
    }
    let trimmed: String = safe.trim_matches('_').chars().take(60).collect();
    let stem = if trimmed.is_empty() {
        "unnamed".to_string()
    } else {
        trimmed
    };
    format!("{stem}-{product_id}.stp")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_ref_lists() {
        assert_eq!(
            match_ref_list(b"(#1, #22 ,#3)x"),
            Some((13, vec![1, 22, 3]))
        );
        assert_eq!(match_ref_list(b"(#1,#2,(#3))"), None);
        assert_eq!(part_filename("BREP_9", 14249), "BREP_9-14249.stp");
        assert_eq!(part_filename("(未保存)", 1), "未保存-1.stp");
        assert_eq!(part_filename("", 5), "unnamed-5.stp");
        assert_eq!(
            ref_ids(b"=X('#9',#10,#11);").collect::<Vec<_>>(),
            vec![9, 10, 11]
        );
    }
}
