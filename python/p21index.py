#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Streaming STEP Part 21 indexer (Python counterpart of the Rust `index` command).

One pass over the file, parallel by byte chunks aligned to entity starts.
Produces a sidecar index with, per entity: id, type, byte range, refs.
No entity text is retained; refs inside string literals are ignored.

Usage: p21index.py <file.stp> <out.npz>
"""
import sys, os, re, mmap, time, array, argparse
import numpy as np
from multiprocessing import Pool

# entity start at a line start; used only for chunk boundaries
ENT_LINE = re.compile(rb'\n[ \t]*#\d+\s*=')
# entity head: '#id=' then optional type name then '('  (empty name => complex instance)
HEAD = re.compile(rb'#(\d+)\s*=\s*([A-Z_0-9]*)\s*\(')
# tokens: string literal | reference | terminator | comment
TOK = re.compile(rb"'(?:[^']|'')*'|#(\d+)|(;)|/\*.*?\*/", re.S)
LAYER_PREFIX = re.compile(rb"\s*'(?:[^']|'')*'\s*,\s*'(?:[^']|'')*'\s*,\s*\(")
LAYER_ITEMS = re.compile(rb'\s*(?:#\d+\s*(?:,\s*#\d+\s*)*)?')
LAYER_END = re.compile(rb'\s*\)\s*;')
REFERENCE = re.compile(rb'#(\d+)')


def fast_layer(mm, pos):
    """Recognize plain membership syntax; comments/unusual syntax use TOK instead."""
    prefix = LAYER_PREFIX.match(mm, pos)
    if prefix is None:
        return None
    end = mm.find(b')', prefix.end())
    if end < 0:
        return None
    items = mm[prefix.end():end]
    suffix = LAYER_END.match(mm, end + 1)
    if suffix is None or LAYER_ITEMS.fullmatch(items) is None:
        return None
    return items, suffix.end()


def parse_chunk(args):
    path, start, end, *options = args
    intern_layers = bool(options and options[0])
    with open(path, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        ids = array.array('I'); types = array.array('H')
        starts = array.array('Q'); lens = array.array('I')
        refstart = array.array('Q'); refs = array.array('I')
        layer_rows = array.array('I'); layer_starts = array.array('Q'); layer_counts = array.array('I')
        layer_cache = {}
        tnames = {}
        pos = start
        search = HEAD.search; finditer = TOK.finditer
        while True:
            m = search(mm, pos, end)
            if not m:
                break
            eid = int(m.group(1)); tn = m.group(2)
            ti = tnames.get(tn)
            if ti is None:
                ti = tnames[tn] = len(tnames)
            rs = len(refs)
            eend = None
            layer_span = None
            fast = fast_layer(mm, m.end()) if intern_layers and tn == b'PRESENTATION_LAYER_ASSIGNMENT' else None
            if fast is not None:
                items, eend = fast
                layer_span = layer_cache.get(items)
                if layer_span is None:
                    refs.extend(int(g) for g in REFERENCE.findall(items))
                    layer_span = layer_cache[items] = (rs, len(refs) - rs)
            else:
                for t in finditer(mm, m.end()):
                    g = t.group(1)
                    if g is not None:
                        refs.append(int(g))
                    elif t.group(2) is not None:
                        eend = t.end()
                        break
                if intern_layers and tn == b'PRESENTATION_LAYER_ASSIGNMENT':
                    layer_span = (rs, len(refs) - rs)
            if eend is None:
                raise RuntimeError(f'unterminated entity #{eid} at {m.start()}')
            if layer_span is not None:
                layer_rows.append(len(ids)); layer_starts.append(layer_span[0]); layer_counts.append(layer_span[1])
            ids.append(eid); types.append(ti); starts.append(m.start())
            lens.append(eend - m.start()); refstart.append(rs)
            pos = eend
        mm.close()
    names = [None] * len(tnames)
    for k, v in tnames.items():
        names[v] = k.decode() or 'CPLX'
    return names, ids, types, starts, lens, refstart, refs, layer_rows, layer_starts, layer_counts


def chunk_bounds(path, nchunks):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        data_at = mm.find(b'\nDATA;')
        if data_at < 0:
            raise RuntimeError('no DATA section')
        data_at += len(b'\nDATA;')
        header = bytes(mm[:data_at])
        bounds = [data_at]
        for i in range(1, nchunks):
            approx = data_at + (size - data_at) * i // nchunks
            m = ENT_LINE.search(mm, approx)
            b = m.start() + 1 if m else size
            if b > bounds[-1]:
                bounds.append(b)
        bounds.append(size)
        mm.close()
    return header, bounds


def build_index(path, workers=None, chunks_per_worker=4, *, intern_layers=False):
    workers = workers or os.cpu_count()
    header, bounds = chunk_bounds(path, workers * chunks_per_worker)
    jobs = [(path, bounds[i], bounds[i + 1], intern_layers) for i in range(len(bounds) - 1)]
    if workers == 1:
        parts = [parse_chunk(job) for job in jobs]
    else:
        with Pool(workers) as pool:
            parts = pool.map(parse_chunk, jobs)
    # merge type tables
    gnames = {}
    out_ids = []; out_types = []; out_starts = []; out_lens = []; out_refstart = []; out_refs = []
    nref = 0; nrow = 0
    out_layer_rows = []; out_layer_starts = []; out_layer_counts = []
    for names, ids, types, starts, lens, refstart, refs, lrows, lstarts, lcounts in parts:
        remap = np.array([gnames.setdefault(n, len(gnames)) for n in names] or [0], dtype=np.uint16)
        t = np.frombuffer(types, dtype=np.uint16)
        out_types.append(remap[t] if len(t) else t)
        out_ids.append(np.frombuffer(ids, dtype=np.uint32))
        out_starts.append(np.frombuffer(starts, dtype=np.uint64))
        out_lens.append(np.frombuffer(lens, dtype=np.uint32))
        out_refstart.append(np.frombuffer(refstart, dtype=np.uint64) + nref)
        r = np.frombuffer(refs, dtype=np.uint32)
        out_layer_rows.append(np.frombuffer(lrows, dtype=np.uint32) + nrow)
        out_layer_starts.append(np.frombuffer(lstarts, dtype=np.uint64) + nref)
        out_layer_counts.append(np.frombuffer(lcounts, dtype=np.uint32))
        out_refs.append(r); nref += len(r)
        nrow += len(ids)
    typenames = [None] * len(gnames)
    for k, v in gnames.items():
        typenames[v] = k
    refstart = np.concatenate(out_refstart + [np.array([nref], dtype=np.uint64)])
    result = dict(
        ids=np.concatenate(out_ids), types=np.concatenate(out_types),
        starts=np.concatenate(out_starts), lens=np.concatenate(out_lens),
        refstart=refstart, refs=np.concatenate(out_refs),
        typenames=np.array(typenames), header=np.frombuffer(header, dtype=np.uint8),
        source=np.array(os.path.abspath(path)), size=np.array(os.path.getsize(path)),
    )
    if intern_layers:
        result.update(layer_rows=np.concatenate(out_layer_rows),
                      layer_starts=np.concatenate(out_layer_starts),
                      layer_counts=np.concatenate(out_layer_counts))
        intern_layer_references(result)
    return result


def intern_layer_references(data):
    """Pool exact ordered layer refs across chunks; retain every entity/text span.

    refstart remains a monotone index of ordinary references. Layer spans point
    into an appended shared pool. This is an opt-in Python cache layout, not the
    legacy flat-reference NPZ/Rust interchange format.
    """
    rows = data['layer_rows']; starts = data['layer_starts']; counts = data['layer_counts']
    lengths = np.diff(data['refstart'])
    keep = np.ones(len(data['refs']), dtype=bool)
    for row in rows:
        lo, hi = data['refstart'][row:row + 2]
        keep[int(lo):int(hi)] = False
    lengths[rows] = 0
    ordinary = data['refs'][keep]
    pool = {}; offsets = []; size = 0
    for start, count in zip(starts, counts):
        key = data['refs'][int(start):int(start) + int(count)].tobytes()
        offset = pool.get(key)
        if offset is None:
            offset = size; pool[key] = offset; size += int(count)
        offsets.append(len(ordinary) + offset)
    values = np.frombuffer(b''.join(pool), dtype=np.uint32)
    data['refs'] = np.concatenate([ordinary, values])
    data['refstart'] = np.concatenate([np.array([0], dtype=np.uint64), np.cumsum(lengths, dtype=np.uint64)])
    data['layer_starts'] = np.array(offsets, dtype=np.uint64)
    data['reference_layout'] = np.array('layer-interned-v1')


class Index:
    """Loaded index with id->row lookup and per-entity accessors."""

    def __init__(self, npz_path):
        with np.load(npz_path) as data:
            self._load(data)

    @classmethod
    def from_step(cls, path, workers=None, *, intern_layers=False):
        """Index STEP directly in memory; no persistent index or rewritten CAD is created."""
        result = cls.__new__(cls)
        if workers is not None and workers < 1:
            raise ValueError('worker count must be positive')
        result._load(build_index(os.fspath(path), workers=1 if workers is None else workers, intern_layers=intern_layers))
        return result

    def _load(self, z):
        self.ids = z['ids']; self.types = z['types']; self.starts = z['starts']
        self.lens = z['lens']; self.refstart = z['refstart']; self.refs = z['refs']
        self.layers_interned = 'reference_layout' in z
        if self.layers_interned and str(z['reference_layout']) != 'layer-interned-v1':
            raise ValueError('unsupported reference layout')
        self.layer_rows = z['layer_rows'] if self.layers_interned else np.array([], dtype=np.uint32)
        self.layer_starts = z['layer_starts'] if self.layers_interned else np.array([], dtype=np.uint64)
        self.layer_counts = z['layer_counts'] if self.layers_interned else np.array([], dtype=np.uint32)
        self._layer_spans = {int(r): (int(s), int(n)) for r, s, n in zip(self.layer_rows, self.layer_starts, self.layer_counts)}
        if self.layers_interned:
            self.refs.flags.writeable = False
            for values in (self.layer_rows, self.layer_starts, self.layer_counts):
                values.flags.writeable = False
        self.typenames = [str(x) for x in z['typenames']]
        self.header = z['header'].tobytes()
        self.source = str(z['source']); self.size = int(z['size'])
        self.tid = {n: i for i, n in enumerate(self.typenames)}
        if not len(self.ids):
            raise ValueError('STEP contains no indexed entities')
        self.max_id = int(self.ids.max())
        self.row = np.full(self.max_id + 1, -1, dtype=np.int32)
        self.row[self.ids] = np.arange(len(self.ids), dtype=np.int32)
        self._f = open(self.source, 'rb')
        self.mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        self.n = len(self.ids)

    def close(self):
        """Release the read-only source mapping and file handle."""
        self.mm.close()
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def rows_of(self, *names):
        sel = np.zeros(self.n, dtype=bool)
        for n in names:
            if n in self.tid:
                sel |= self.types == self.tid[n]
        return np.nonzero(sel)[0]

    def tname(self, r):
        return self.typenames[self.types[r]]

    def refs_of(self, r):
        if r in self._layer_spans:
            start, count = self._layer_spans[r]
            return self.refs[start:start + count]
        return self.refs[self.refstart[r]:self.refstart[r + 1]]

    def reference_spans(self, rows):
        """Physical starts and logical lengths for entity rows, including layers."""
        rows = np.asarray(rows, dtype=np.int64)
        starts = self.refstart[rows].copy()
        counts = self.refstart[rows + 1] - starts
        if len(self.layer_rows):
            indices = np.searchsorted(self.layer_rows, rows)
            candidates = np.flatnonzero(indices < len(self.layer_rows))
            matched = candidates[self.layer_rows[indices[candidates]] == rows[candidates]]
            starts[matched] = self.layer_starts[indices[matched]]
            counts[matched] = self.layer_counts[indices[matched]]
        return starts, counts

    def layer_membership_key(self, row):
        """Process-local shared span key, or None; never a source layer identity."""
        return self._layer_spans.get(int(row))

    @property
    def reference_count(self):
        """Logical reference occurrences; len(refs) counts physically stored values."""
        return int(self.refstart[-1]) + int(self.layer_counts.sum())

    def unresolved_reference_count(self):
        """Count missing logical references, including repeated pooled memberships."""
        in_range = self.refs <= self.max_id
        bad = ~in_range
        bad[in_range] = self.row[self.refs[in_range]] < 0
        if not bad.any():
            return 0
        missing = int(bad[:int(self.refstart[-1])].sum())
        for start, count in zip(self.layer_starts, self.layer_counts):
            missing += int(bad[int(start):int(start) + int(count)].sum())
        return missing

    def text(self, r):
        s = int(self.starts[r]); return self.mm[s:s + int(self.lens[r])]

    def args(self, r):
        """entity text after the type name's '(' up to the final ')' (bytes)."""
        t = self.text(r)
        return t[t.index(b'(') + 1: t.rindex(b')')]

    def r(self, eid):
        """row of entity id, or -1."""
        return int(self.row[eid]) if 0 <= eid <= self.max_id else -1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source'); ap.add_argument('out')
    ap.add_argument('--intern-layers', action='store_true', help='opt-in Python-only shared-reference cache layout')
    ap.add_argument('--workers', type=int, default=1)
    args = ap.parse_args(); src, out = args.source, args.out
    t0 = time.time()
    idx = build_index(src, workers=args.workers, intern_layers=args.intern_layers)
    t1 = time.time()
    np.savez(out, **idx)
    print(f'{src}: {len(idx["ids"])} entities, {len(idx["refs"])} refs, '
          f'{len(idx["typenames"])} types, parse {t1 - t0:.1f}s, save {time.time() - t1:.1f}s')
