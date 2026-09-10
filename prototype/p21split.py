#!/usr/bin/env python3
"""Text-level per-product split of a STEP Part 21 file (prototype of `split`).

For every PRODUCT that owns shape representations, write a standalone STEP
file containing:
  * the forward closure of its SHAPE_DEFINITION_REPRESENTATION(s) and the
    SHAPE_REPRESENTATION_RELATIONSHIPs between its own representations
    (geometry, topology, placements, units/contexts, product/PDM chain);
  * every STYLED_ITEM / OVER_RIDING_STYLED_ITEM whose target is in that
    closure, with the style chain (colours, fonts);
  * reverse-referenced boilerplate (material properties, product category,
    application protocol, CC_DESIGN_* assignments, layers, presentation
    representation) with their reference lists filtered to the closure.
Entity text is copied byte for byte and keeps its original id; only the
list-filtered boilerplate entities are re-emitted.

Usage: p21split.py <index.npz> <out_dir> [--products name,name] [--limit N]
"""
import sys, os, re, json, time, argparse, collections
import numpy as np
from p21index import Index
from p21model import Model, first_string, decode_p21

# reverse-referenced entities: policy = ('key', ref position) or ('list',)
REVERSE = {
    'STYLED_ITEM': ('key', -1), 'OVER_RIDING_STYLED_ITEM': ('key', -2),
    'PROPERTY_DEFINITION': ('key', -1), 'PROPERTY_DEFINITION_REPRESENTATION': ('key', 0),
    'APPLICATION_PROTOCOL_DEFINITION': ('key', -1), 'PRODUCT_CATEGORY_RELATIONSHIP': ('key', -1),
    'APPROVAL_DATE_TIME': ('key', -1), 'APPROVAL_PERSON_ORGANIZATION': ('key', 1),
    'PRODUCT_RELATED_PRODUCT_CATEGORY': ('list',), 'PRESENTATION_LAYER_ASSIGNMENT': ('list',),
    'MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION': ('list',),
    'CC_DESIGN_PERSON_AND_ORGANIZATION_ASSIGNMENT': ('list',),
    'CC_DESIGN_DATE_AND_TIME_ASSIGNMENT': ('list',),
    'CC_DESIGN_SECURITY_CLASSIFICATION': ('list',), 'CC_DESIGN_APPROVAL': ('list',),
}
LIST_RE = re.compile(rb'\(\s*#\d+(?:\s*,\s*#\d+)*\s*\)')
SAFE_RE = re.compile(r'[^A-Za-z0-9_.\-一-鿿]+')
SOLID_TYPES = ('MANIFOLD_SOLID_BREP', 'BREP_WITH_VOIDS', 'FACETED_BREP')


def gather_refs(ix, rows):
    """flat array of ref *rows* (may be -1) for the given entity rows, plus owner index."""
    starts = ix.refstart[rows]; lens = (ix.refstart[rows + 1] - starts).astype(np.int64)
    total = int(lens.sum())
    if total == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    owner = np.repeat(np.arange(len(rows)), lens)
    base = np.repeat(starts.astype(np.int64), lens)
    within = np.arange(total) - np.repeat(np.cumsum(lens) - lens, lens)
    ids = ix.refs[base + within]
    return ix.row[ids].astype(np.int64), owner


def forward_closure(ix, seeds, mask):
    frontier = np.unique(np.asarray(seeds, dtype=np.int64))
    frontier = frontier[frontier >= 0]
    mask[frontier] = True
    while len(frontier):
        rows, _ = gather_refs(ix, frontier)
        rows = np.unique(rows[rows >= 0])
        rows = rows[~mask[rows]]
        mask[rows] = True
        frontier = rows
    return mask


class Splitter:
    def __init__(self, ix: Index, m: Model):
        self.ix, self.m = ix, m
        self.crlf = b'\r\n' if b'\r\n' in ix.header else b'\n'
        # precompute reverse tables
        self.key_tab = {}   # type -> (rows, key_rows)
        self.list_tab = {}  # type -> (rows, ref_rows, owner)
        for tn, pol in REVERSE.items():
            rows = ix.rows_of(tn).astype(np.int64)
            if not len(rows):
                continue
            if pol[0] == 'key':
                k = pol[1]
                keys = np.array([ix.row[int(ix.refs_of(r)[k])] if len(ix.refs_of(r)) > abs(k) - (1 if k < 0 else 0) else -1
                                 for r in rows], dtype=np.int64)
                self.key_tab[tn] = (rows, keys)
            else:
                ref_rows, owner = gather_refs(ix, rows)
                # per row: byte prefix/suffix around the inner ref list, the list ids in
                # order, and where that list sits inside the row's flat refs
                spans = []
                for o, row in enumerate(rows.tolist()):
                    text = ix.text(row)
                    mt = LIST_RE.search(text, text.index(b'('))
                    lo = int(np.searchsorted(owner, o)); hi = int(np.searchsorted(owner, o + 1))
                    if not mt:
                        spans.append(None); continue
                    lids = np.array([int(x) for x in re.findall(rb'#(\d+)', mt.group(0))], dtype=np.int64)
                    allids = ix.refs[ix.refstart[row]:ix.refstart[row + 1]].astype(np.int64)
                    li = -1
                    for k in range(len(allids) - len(lids) + 1):
                        if allids[k] == lids[0] and allids[k + len(lids) - 1] == lids[-1]:
                            li = k; break
                    spans.append((text[:mt.start()], text[mt.end():], lids, lo + li, len(lids)) if li >= 0 else None)
                self.list_tab[tn] = (rows, ref_rows, owner, spans)
        self.srr = [(row, r1, r2) for row, r1, r2 in m.srr_rows]

    def product_seeds(self, p):
        m = self.m
        reps = set(m.product_reps.get(p, []))
        seeds = [m.sdr_rows[r] for r in reps if r in m.sdr_rows]
        seeds += [row for row, r1, r2 in self.srr if r1 in reps and r2 in reps]
        return seeds, reps

    def sheet_bodies(self, reps):
        """rows of the non-solid bodies (sheet models) in these representations."""
        return [b for b, rep in self.m.bodies if rep in reps and self.ix.tname(b) not in SOLID_TYPES]

    def closure(self, p, solids_only=False):
        """returns (mask, rewritten: {row: bytes}).

        solids_only drops the product's sheet bodies: they are blocked from the
        closure and each representation's item list is re-emitted without them,
        so the file holds the solids only (the V1.2.0 assemblies carry tens of
        thousands of single-face sheets next to a handful of solids)."""
        ix = self.ix
        seeds, reps = self.product_seeds(p)
        mask = np.zeros(ix.n, dtype=bool)
        rewritten = {}
        blocked = np.array(self.sheet_bodies(reps) if solids_only else [], dtype=np.int64)
        if len(blocked):
            blocked_set = set(blocked.tolist())
            mask[blocked] = True
            for rep in reps:
                text = ix.text(rep)
                mt = LIST_RE.search(text, text.index(b'('))
                lids = [int(x) for x in re.findall(rb'#(\d+)', mt.group(0))]
                keep = np.array([i for i in lids if ix.row[i] not in blocked_set], dtype=np.int64)
                rewritten[rep] = text[:mt.start()] + self.emit_list(keep) + text[mt.end():]
        forward_closure(ix, seeds, mask)
        mask[blocked] = False
        for _ in range(6):
            before = int(mask.sum())
            add = []
            for tn, (rows, keys) in self.key_tab.items():
                ok = keys >= 0
                hit = np.zeros(len(rows), bool); hit[ok] = mask[keys[ok]]
                add.extend(rows[hit & ~mask[rows]].tolist())
            for tn, (rows, ref_rows, owner, spans) in self.list_tab.items():
                ok = ref_rows >= 0
                hit = np.zeros(len(ref_rows), bool); hit[ok] = mask[ref_rows[ok]]
                owners_hit = np.unique(owner[hit])
                for o in owners_hit.tolist():
                    row = int(rows[o])
                    if row in rewritten or spans[o] is None:
                        continue
                    prefix, suffix, lids, li, ln = spans[o]
                    keep = lids[hit[li:li + ln]]
                    if not len(keep):
                        continue
                    rewritten[row] = prefix + self.emit_list(keep) + suffix
                    add.append(row)
            if add:
                add = np.array(add, dtype=np.int64)
                # rewritten entities: forward-close only their kept refs
                plain = np.array([r for r in add.tolist() if r not in rewritten], dtype=np.int64)
                mask[add] = True
                if len(plain):
                    forward_closure(ix, plain, mask)
                kept = []
                for r in add.tolist():
                    if r in rewritten:
                        body = rewritten[r][rewritten[r].index(b'='):]  # skip own '#id='
                        kept.extend(ix.row[int(x)] for x in re.findall(rb'#(\d+)', body))
                forward_closure(ix, np.array(kept, dtype=np.int64), mask)
                mask[blocked] = False
            if int(mask.sum()) == before:
                break
        return mask, rewritten

    def emit_list(self, ids):
        """'(#a,#b,...)' wrapped at ~72 columns like the exporters do."""
        out = []; line = b''
        for i in ids.tolist():
            tok = b'#%d' % i
            if line and len(line) + len(tok) + 1 > 72:
                out.append(line + b','); line = tok
            else:
                line = (line + b',' + tok) if line else tok
        out.append(line)
        return b'(' + self.crlf.join(out) + b')'

    def write(self, p, path, solids_only=False):
        ix = self.ix
        mask, rewritten = self.closure(p, solids_only)
        rows = np.nonzero(mask)[0]
        kind = np.zeros(len(rows), np.int8)
        if rewritten:
            rw = np.array(sorted(rewritten), dtype=np.int64)
            kind[np.isin(rows, rw)] = 1
        # runs of consecutive rows of the same kind
        brk = np.nonzero((np.diff(rows) != 1) | (np.diff(kind) != 0))[0] + 1
        bounds = np.concatenate([[0], brk, [len(rows)]])
        mm = ix.mm; nbytes = 0
        with open(path, 'wb') as f:
            f.write(ix.header); f.write(self.crlf)
            for a, b in zip(bounds[:-1], bounds[1:]):
                if kind[a] == 0:
                    s = int(ix.starts[rows[a]]); e = int(ix.starts[rows[b - 1]]) + int(ix.lens[rows[b - 1]])
                    f.write(mm[s:e]); f.write(self.crlf); nbytes += e - s
                else:
                    for r in rows[a:b].tolist():
                        f.write(rewritten[r]); f.write(self.crlf); nbytes += len(rewritten[r])
            f.write(b'ENDSEC;' + self.crlf + b'END-ISO-10303-21;' + self.crlf)
        return int(len(rows)), len(rewritten), nbytes


def part_filename(name, pid):
    safe = SAFE_RE.sub('_', name or 'unnamed').strip('_')[:60] or 'unnamed'
    return f'{safe}-{pid}.stp'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('index'); ap.add_argument('out')
    ap.add_argument('--products', default=None); ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--manifest-only', action='store_true', help='recompute parts.json without writing part files')
    a = ap.parse_args()
    t0 = time.time()
    ix = Index(a.index); m = Model(ix); sp = Splitter(ix, m)
    print(f'model ready {time.time() - t0:.1f}s', flush=True)
    os.makedirs(os.path.join(a.out, 'parts'), exist_ok=True)
    prods = [p for p in m.product_name if p in m.product_reps]
    if a.products:
        want = set(a.products.split(','))
        prods = [p for p in prods if m.pname(p) in want]
    if a.limit:
        prods = prods[:a.limit]
    manifest = []
    prev = {}
    if a.manifest_only and os.path.exists(os.path.join(a.out, 'parts.json')):
        prev = {q['product_id']: q for q in json.load(open(os.path.join(a.out, 'parts.json')))['parts']}
    t1 = time.time(); total_ents = 0; total_bytes = 0
    for i, p in enumerate(prods):
        pid = int(ix.ids[p]); name = m.pname(p)
        fn = part_filename(name, pid)
        ts = time.time()
        if a.manifest_only:
            q = prev.get(pid, {}); nents, nrw = q.get('entities', 0), q.get('rewritten', 0)
            nbytes = os.path.getsize(os.path.join(a.out, 'parts', fn))
        else:
            nents, nrw, nbytes = sp.write(p, os.path.join(a.out, 'parts', fn))
        bodies = []
        for b, rep in m.bodies:
            if m.rep_product.get(rep) != p:
                continue
            faces = m.body_faces(b)
            mn, mx, nv = m.body_bbox(b)
            fc = m.face_colour_hist(b, faces)
            bodies.append(dict(id=int(ix.ids[b]), type=ix.tname(b), faces=len(faces),
                               extra_outer_bounds=m.extra_outer_bounds(faces),
                               body_colour=m.surface_colour(b),
                               face_colours={str(k): v for k, v in fc.items()},
                               bbox_min=None if mn is None else [round(float(x), 4) for x in mn],
                               bbox_max=None if mx is None else [round(float(x), 4) for x in mx],
                               vertices=nv))
        manifest.append(dict(file='parts/' + fn, product_id=pid, name=name, entities=nents,
                             rewritten=nrw, bytes=nbytes, bodies=bodies, seconds=round(time.time() - ts, 3)))
        total_ents += nents; total_bytes += nbytes
        if i % 50 == 0 or i == len(prods) - 1:
            print(f'[{i + 1}/{len(prods)}] {fn}: {nents} entities, {nbytes / 1e6:.1f} MB, {len(bodies)} bodies', flush=True)
    json.dump(dict(source=ix.source, source_size=ix.size, entities=ix.n, parts=manifest,
                   colour_names={k: sorted(v) for k, v in m.colour_names.items()},
                   total_entities_written=total_ents, total_bytes_written=total_bytes,
                   split_seconds=round(time.time() - t1, 1)),
              open(os.path.join(a.out, 'parts.json'), 'w'), indent=1, ensure_ascii=False)
    print(f'{len(prods)} parts, {total_ents} entities ({total_ents / ix.n:.2f}x source), '
          f'{total_bytes / 1e6:.0f} MB, {time.time() - t1:.1f}s')


if __name__ == '__main__':
    main()
