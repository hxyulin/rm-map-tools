# SPDX-License-Identifier: MIT OR Apache-2.0
"""Audit STEP ownership, references, placements and unused metadata.

Usage: ocpenv/bin/python python/audit_step.py v12.npz --out out/v12-audit.json
Geometry is read by OCCT elsewhere; this checks the text model feeding exports.
"""
import argparse
import collections
import json
import re

import numpy as np

from p21index import Index
from p21model import BODY_TYPES, Model
from mesh_parts import nauo_transforms, occurrence_transforms


def geometry_length_units(ix):
    """Inspect geometry contexts, excluding metre units used only by density."""
    counts = collections.Counter()
    for row in ix.rows_of('CPLX'):
        text = ix.text(int(row))
        match = re.search(rb'GLOBAL_UNIT_ASSIGNED_CONTEXT\s*\(\s*\((.*?)\)\s*\)', text, re.S)
        if not match:
            continue
        for value in re.findall(rb'#(\d+)', match.group(1)):
            unit = ix.text(ix.r(int(value)))
            if b'LENGTH_UNIT' in unit:
                si = re.search(rb'SI_UNIT\s*\(([^)]*)\)', unit)
                counts[re.sub(rb'\s+', b'', si.group(1)).decode() if si else 'non-SI'] += 1
    return dict(counts)


def audit(index):
    ix = Index(index)
    model = Model(ix)
    transforms = nauo_transforms(ix, model)
    placed = occurrence_transforms(ix, model, transforms)
    raw_bodies = set(ix.rows_of(*BODY_TYPES).tolist())
    owned = {b for b, rep in model.bodies if rep in model.rep_product}
    references = ix.refs
    in_range = references <= ix.max_id
    unresolved = int((~in_range).sum() + (ix.row[references[in_range]] < 0).sum())
    complex_types = collections.Counter()
    metadata = {}
    interesting = ('UNIT', 'MEASURE', 'PROPERTY', 'LAYER', 'INVIS', 'STYLE',
                   'TRANSFORM', 'MAPPED', 'REPRESENTATION', 'TOLERANCE')
    for name in ix.typenames:
        if any(token in name for token in interesting):
            rows = ix.rows_of(name)
            metadata[name] = {'count': len(rows), 'examples': [
                ix.text(int(row)).decode('ascii', 'replace')[:300] for row in rows[:2]]}
    for row in ix.rows_of('CPLX'):
        text = ix.text(int(row))
        names = re.findall(rb'([A-Z][A-Z0-9_]*)\s*\(', text)
        for name in names:
            decoded = name.decode()
            complex_types[decoded] += 1
            if any(token in decoded for token in interesting):
                entry = metadata.setdefault(decoded, {'count': 0, 'examples': []})
                entry['count'] += 1
                if len(entry['examples']) < 2:
                    entry['examples'].append(text.decode('ascii', 'replace')[:300])
    result = {
        'source': ix.source, 'entities': int(ix.n), 'unresolved_references': unresolved,
        'body_entities': len(raw_bodies), 'owned_bodies': len(owned),
        'unowned_bodies': [int(ix.ids[r]) for r in raw_bodies - owned],
        'occurrences': len(model.nauo), 'explicit_transforms': len(transforms),
        'missing_transforms': [int(ix.ids[r]) for r in model.nauo if r not in transforms],
        'unplaced_products': [model.pname(r) for r in model.product_reps if r not in placed],
        'non_rigid_transforms': [int(ix.ids[r]) for r, matrix in transforms.items()
            if not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6)
            or np.linalg.det(matrix[:3, :3]) <= 0],
        'geometry_length_units': geometry_length_units(ix),
        'entity_types': {ix.typenames[int(k)]: int(v) for k, v in zip(*np.unique(ix.types, return_counts=True))},
        'complex_entity_types': dict(complex_types), 'metadata': metadata,
    }
    result['ok'] = not any(result[key] for key in (
        'unresolved_references', 'unowned_bodies', 'missing_transforms',
        'unplaced_products', 'non_rigid_transforms'))
    ix.mm.close()
    ix._f.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = audit(args.index)
    with open(args.out, 'w') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('entity_types', 'complex_entity_types', 'metadata')}))
    if not result['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
