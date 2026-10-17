#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Trial material-independent collision LOD on separate rigid equipment members.

Not a runtime package: moving owners and scoring detectors must be bound by the
consumer. DJI / RoboMaster owns source geometry and appearance.
"""
import argparse
import json
from pathlib import Path
from run import ROOT, save_mesh
import numpy as np
from cad_collision_proxy import collision_proxy
from gltf_scene import read_glb, mesh_instances
from mesh_quality import deviation
from plan_cad_lods import digest

TARGETS = ['dart-station/deck-and-shared-hardware', 'dart-station/frame',
           'dart-station/door-candidate', 'outpost/fixed/upper-cluster',
           'resource-area/mechanism', 'energy-unit/unit']


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'out/rmuc2027-residual-equipment/composition.json'
    manifest = json.loads(source.read_bytes()); by_id = {r['id']: r for r in manifest['components']}; rows = []
    for cid in TARGETS:
        row = by_id[cid]; glb = ROOT / row['candidate_glb']; path = glb.with_suffix('.npz')
        if digest(glb) != row['candidate_sha256']: raise ValueError('approved visual changed')
        d = np.load(path); p, t, units = [d[k] for k in ['positions_mm', 'triangles', 'unit_ids']]
        doc, blob = read_glb(glb); instances = list(mesh_instances(doc, blob))
        count = sum(len(f) for _, _, _, f, _ in instances)
        if count != len(t) or count != row['candidate_triangles']: raise ValueError('visual/NPZ triangle mismatch')
        # Match actual export positions to the source NPZ, allowing glTF float32.
        from scipy.spatial import cKDTree
        actual = np.concatenate([q[f].reshape(-1, 3) * 1000 for _, _, q, f, _ in instances])
        if cKDTree(p).query(actual)[0].max() > .002: raise ValueError('visual/NPZ positions mismatch')
        folder = args.out / cid; folder.mkdir(parents=True, exist_ok=True)
        for label, nominal, limit in [('contact-3mm', 1, 3), ('contact-6mm', 3, 6)]:
            chunks = []; faces = []; owners = []; records = []; offset = 0
            for unit in np.unique(units):
                ids = units == unit; used, inv = np.unique(t[ids], return_inverse=True); before = p[used]; old = inv.reshape(-1, 3)
                if len(old) >= 128:
                    q, f, proof = collision_proxy(before, old, nominal_error_mm=nominal, sampled_limit_mm=limit, sample_count=2048)
                else:
                    q, f = before, old; proof = {'operation': 'retain-small-member', 'input_triangles': len(old), 'output_triangles': len(old), 'primitive': None}
                chunks.append(q); faces.append(f + offset); offset += len(q); owners.extend([unit] * len(f))
                proof['source_member'] = int(unit); records.append(proof)
            q = np.concatenate(chunks); f = np.concatenate(faces); check = deviation(p, t, q, f, count=16384)
            # Independent denser whole-equipment check: reject rather than relax.
            if check['max'] > limit:
                raise ValueError('whole equipment guard failed ' + cid + ' ' + str(check))
            save_mesh(folder, label, q, f, np.zeros(len(f), dtype=np.int64), ['0.45,0.65,0.80'], np.array(owners))
            result = {'id': cid, 'uses': row['uses'], 'variant': label, 'visual_triangles': len(t), 'collision_triangles': len(f), 'sampled_deviation_mm': check,
                      'source_visual_sha256': digest(glb), 'source_npz_sha256': digest(path), 'collision_glb_sha256': digest(folder / (label + '.glb')),
                      'box_members': sum(r['operation'] == 'box' for r in records), 'members': records}
            rows.append(result); print(cid, label, len(t), '->', len(f), 'boxes', result['box_members'], check, flush=True)
    report = {'composition_sha256': digest(source), 'components': rows, 'producer_sha256': digest(__file__),
              'pass_sha256': digest(ROOT / 'python/cad_collision_proxy.py'),
              'scope': 'Inspection-only collision from approved visual surfaces, not native solid equality. Separate rigid members and variants; no scoring target, runtime collider, installed field or source modification. Base retains its earlier dedicated collider.'}
    (args.out / 'collision-summary.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
