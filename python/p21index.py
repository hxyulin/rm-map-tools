#!/usr/bin/env python3
"""Streaming STEP Part 21 indexer (Python counterpart of the Rust `index` command).

One pass over the file, parallel by byte chunks aligned to entity starts.
Produces a sidecar index with, per entity: id, type, byte range, refs.
No entity text is retained; refs inside string literals are ignored.

Usage: p21index.py <file.stp> <out.npz>
"""
import sys, os, re, mmap, time, array, json
import numpy as np
from multiprocessing import Pool

# entity start at a line start; used only for chunk boundaries
ENT_LINE = re.compile(rb'\n#\d+=')
# entity head: '#id=' then optional type name then '('  (empty name => complex instance)
HEAD = re.compile(rb'#(\d+)=\s*([A-Z_0-9]*)\s*\(')
# tokens: string literal | reference | terminator | comment
TOK = re.compile(rb"'(?:[^']|'')*'|#(\d+)|(;)|/\*.*?\*/", re.S)


def parse_chunk(args):
    path, start, end = args
    with open(path, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        ids = array.array('I'); types = array.array('H')
        starts = array.array('Q'); lens = array.array('I')
        refstart = array.array('Q'); refs = array.array('I')
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
            for t in finditer(mm, m.end()):
                g = t.group(1)
                if g is not None:
                    refs.append(int(g))
                elif t.group(2) is not None:
                    eend = t.end()
                    break
            if eend is None:
                raise RuntimeError(f'unterminated entity #{eid} at {m.start()}')
            ids.append(eid); types.append(ti); starts.append(m.start())
            lens.append(eend - m.start()); refstart.append(rs)
            pos = eend
        mm.close()
    names = [None] * len(tnames)
    for k, v in tnames.items():
        names[v] = k.decode() or 'CPLX'
    return names, ids, types, starts, lens, refstart, refs


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


def build_index(path, workers=None, chunks_per_worker=4):
    workers = workers or os.cpu_count()
    header, bounds = chunk_bounds(path, workers * chunks_per_worker)
    jobs = [(path, bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    with Pool(workers) as pool:
        parts = pool.map(parse_chunk, jobs)
    # merge type tables
    gnames = {}
    out_ids = []; out_types = []; out_starts = []; out_lens = []; out_refstart = []; out_refs = []
    nref = 0
    for names, ids, types, starts, lens, refstart, refs in parts:
        remap = np.array([gnames.setdefault(n, len(gnames)) for n in names] or [0], dtype=np.uint16)
        t = np.frombuffer(types, dtype=np.uint16)
        out_types.append(remap[t] if len(t) else t)
        out_ids.append(np.frombuffer(ids, dtype=np.uint32))
        out_starts.append(np.frombuffer(starts, dtype=np.uint64))
        out_lens.append(np.frombuffer(lens, dtype=np.uint32))
        out_refstart.append(np.frombuffer(refstart, dtype=np.uint64) + nref)
        r = np.frombuffer(refs, dtype=np.uint32)
        out_refs.append(r); nref += len(r)
    typenames = [None] * len(gnames)
    for k, v in gnames.items():
        typenames[v] = k
    refstart = np.concatenate(out_refstart + [np.array([nref], dtype=np.uint64)])
    return dict(
        ids=np.concatenate(out_ids), types=np.concatenate(out_types),
        starts=np.concatenate(out_starts), lens=np.concatenate(out_lens),
        refstart=refstart, refs=np.concatenate(out_refs),
        typenames=np.array(typenames), header=np.frombuffer(header, dtype=np.uint8),
        source=np.array(os.path.abspath(path)), size=np.array(os.path.getsize(path)),
    )


class Index:
    """Loaded index with id->row lookup and per-entity accessors."""

    def __init__(self, npz_path):
        z = np.load(npz_path)
        self.ids = z['ids']; self.types = z['types']; self.starts = z['starts']
        self.lens = z['lens']; self.refstart = z['refstart']; self.refs = z['refs']
        self.typenames = [str(x) for x in z['typenames']]
        self.header = z['header'].tobytes()
        self.source = str(z['source']); self.size = int(z['size'])
        self.tid = {n: i for i, n in enumerate(self.typenames)}
        self.max_id = int(self.ids.max())
        self.row = np.full(self.max_id + 1, -1, dtype=np.int32)
        self.row[self.ids] = np.arange(len(self.ids), dtype=np.int32)
        self._f = open(self.source, 'rb')
        self.mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        self.n = len(self.ids)

    def rows_of(self, *names):
        sel = np.zeros(self.n, dtype=bool)
        for n in names:
            if n in self.tid:
                sel |= self.types == self.tid[n]
        return np.nonzero(sel)[0]

    def tname(self, r):
        return self.typenames[self.types[r]]

    def refs_of(self, r):
        return self.refs[self.refstart[r]:self.refstart[r + 1]]

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
    src, out = sys.argv[1], sys.argv[2]
    t0 = time.time()
    idx = build_index(src)
    t1 = time.time()
    np.savez(out, **idx)
    print(f'{src}: {len(idx["ids"])} entities, {len(idx["refs"])} refs, '
          f'{len(idx["typenames"])} types, parse {t1 - t0:.1f}s, save {time.time() - t1:.1f}s')
