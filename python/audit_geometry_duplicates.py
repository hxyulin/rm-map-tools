#!/usr/bin/env python3
"""Read-only STEP body graph duplicate audit. Does not authorize shape replacement.

Matches ordered geometry graphs after replacing entity IDs with child hashes
and ignoring simple entity display names, comments and whitespace. Numeric
spellings, topology order and coordinates must match. Styles and product
metadata are deliberately outside the geometry fingerprint.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np
from p21index import Index
from p21model import BODY_TYPES, Model

TOKEN = re.compile(rb"'(?:[^']|'')*'|#(\d+)|/\*.*?\*/|\s+", re.S)
NAME = re.compile(rb"^([A-Z_0-9]+\(\s*)'(?:[^']|'')*'", re.S)


class GeometryFingerprints:
    def __init__(self, index):
        self.ix = index
        self.memo = {}
        self.active = set()

    def entity_text(self, row):
        return self.ix.text(row).split(b'=', 1)[1].strip()

    def signature(self, row):
        if row < 0:
            raise ValueError('unresolved geometry reference')
        if row in self.memo:
            return self.memo[row]
        if row in self.active:
            raise ValueError('cyclic geometry graph')
        self.active.add(row)
        try:
            text = self.entity_text(row)
            text = NAME.sub(rb"\1''", text, count=1)
            def token(match):
                if match.group(1) is not None:
                    child = self.ix.r(int(match.group(1)))
                    return b'@' + self.signature(child).hex().encode()
                value = match.group()
                return value if value.startswith(b"'") else b''
            result = hashlib.sha256(TOKEN.sub(token, text)).digest()
            self.memo[row] = result
            return result
        finally:
            self.active.remove(row)


def audit(index_path, output):
    start = time.perf_counter()
    ix = Index(index_path)
    try:
        model = Model(ix)
        fingerprints = GeometryFingerprints(ix)
        groups = defaultdict(list)
        skipped = []
        bodies = ix.rows_of(*BODY_TYPES)
        for i, row in enumerate(bodies):
            row = int(row)
            try:
                groups[fingerprints.signature(row)].append(row)
            except ValueError as exc:
                skipped.append({'body':int(ix.ids[row]),'reason':str(exc)})
            if i % 5000 == 0:
                print(f'{i}/{len(bodies)} bodies, {len(fingerprints.memo)} geometry entities hashed',flush=True)
        product_bodies = defaultdict(list)
        body_owners = defaultdict(set)
        for body, rep in model.bodies:
            product = model.rep_product.get(rep)
            if product is not None:
                product_bodies[product].append(body)
                body_owners[body].add(model.pname(product))
        products = defaultdict(list)
        for product, rows in product_bodies.items():
            if all(row in fingerprints.memo for row in rows):
                key = tuple(sorted(fingerprints.memo[row] for row in rows))
                products[key].append({'id':int(ix.ids[product]),'name':model.pname(product),'bodies':len(rows)})
        duplicate_groups = []
        for rows in groups.values():
            if len(rows) < 2:
                continue
            duplicate_groups.append(dict(type=ix.tname(rows[0]),count=len(rows),
                body_ids=[int(ix.ids[row]) for row in rows],
                products=sorted({name for row in rows for name in body_owners[row]})))
        duplicate_groups.sort(key=lambda item:-item['count'])
        report = dict(source=ix.source,source_bytes=ix.size,source_sha256=hashlib.sha256(ix.mm).hexdigest(),
            method=__doc__,body_definitions=len(bodies),unique_body_fingerprints=len(groups),
            duplicate_body_definitions=sum(len(rows)-1 for rows in groups.values()),
            visited_geometry_entities=len(fingerprints.memo),
            duplicate_groups_by_type=dict(Counter(item['type'] for item in duplicate_groups)),
            duplicate_body_groups=duplicate_groups,
            duplicate_product_geometry_groups=[rows for rows in products.values() if len(rows)>1],
            skipped=skipped,elapsed_seconds=time.perf_counter()-start)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('method','duplicate_body_groups','duplicate_product_geometry_groups','skipped')},indent=2),flush=True)
    finally:
        ix.mm.close(); ix._f.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('index',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    args = ap.parse_args()
    audit(args.index,args.out)

if __name__ == '__main__': main()
