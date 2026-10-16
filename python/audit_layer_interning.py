#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measure opt-in layer pooling and prove all STEP references/text unchanged.

The source is mapped twice; indexes live in memory and are never serialized.
NumPy byte totals are owned arrays, not process RSS or peak allocation estimates.
Single-run timings are indicative. No STEP or runtime geometry is rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from audit_semantic_evidence import semantic_evidence
from p21index import Index
from p21model import Model


def compare_indexes(legacy, compact):
    """Check every record span, ordinary ref, and each layer's ordered refs."""
    if legacy.header != compact.header or legacy.typenames != compact.typenames:
        raise ValueError('header or type namespace changed')
    for name in ('ids', 'types', 'starts', 'lens'):
        if not np.array_equal(getattr(legacy, name), getattr(compact, name)):
            raise ValueError(f'entity identity/text spans changed: {name}')
    ordinary = np.ones(legacy.n, dtype=bool)
    ordinary[compact.layer_rows] = False
    if not np.array_equal(np.diff(legacy.refstart)[ordinary], np.diff(compact.refstart)[ordinary]):
        raise ValueError('ordinary entity reference boundaries changed')
    keep = np.ones(len(legacy.refs), dtype=bool)
    for row in compact.layer_rows:
        keep[int(legacy.refstart[row]):int(legacy.refstart[row+1])] = False
        if not np.array_equal(legacy.refs_of(int(row)), compact.refs_of(int(row))):
            raise ValueError(f'layer membership changed at #{int(legacy.ids[row])}')
    if not np.array_equal(legacy.refs[keep], compact.refs[:int(compact.refstart[-1])]):
        raise ValueError('ordinary reference values changed')
    if legacy.reference_count != compact.reference_count:
        raise ValueError('logical reference count changed')
    return {'entity_spans_checked': legacy.n, 'ordinary_references_checked': int(keep.sum()),
            'layer_records_checked': len(compact.layer_rows),
            'logical_references_checked': legacy.reference_count,
            'all_layer_names_descriptions_and_text_preserved': True}


def measure(source):
    with Path(source).open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    indexes = []; results = []
    try:
        for intern in (False, True):
            start = time.perf_counter()
            ix = Index.from_step(source, workers=1, intern_layers=intern); indexes.append(ix)
            seconds = time.perf_counter() - start
            start = time.perf_counter(); model = Model(ix)
            evidence = semantic_evidence(ix, model)
            semantic_seconds = time.perf_counter() - start
            arrays = {k: v.nbytes for k, v in vars(ix).items() if isinstance(v, np.ndarray)}
            results.append({'intern_layers': intern, 'serial_index_seconds': seconds,
                            'model_and_semantic_evidence_seconds': semantic_seconds,
                            'numpy_array_bytes': sum(arrays.values()), 'arrays_bytes': arrays,
                            'stored_reference_values': len(ix.refs),
                            'logical_references': ix.reference_count,
                            'layers': len(ix.rows_of('PRESENTATION_LAYER_ASSIGNMENT')),
                            'layer_membership_groups': len(set(ix._layer_spans.values())) if intern else None,
                            '_evidence': evidence})
            print(intern, seconds, sum(arrays.values()), len(ix.refs), flush=True)
        proof = compare_indexes(*indexes)
        proof['semantic_evidence_identical'] = results[0].pop('_evidence') == results[1].pop('_evidence')
        if not proof['semantic_evidence_identical']:
            raise ValueError('semantic classification changed')
        with Path(source).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError('source changed')
        return {'schema_version': 1, 'source_sha256': digest, 'results': results, 'proof': proof,
                'scope': 'single-run wall times; NumPy bytes exclude Python objects, mapped source and temporary/peak allocations',
                'producer_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ('audit_layer_interning.py', 'p21index.py', 'p21split.py', 'audit_semantic_evidence.py')}}
    finally:
        for ix in indexes:
            ix.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    report = measure(args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')


if __name__ == '__main__':
    main()
