#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Re-export composed mesh payloads and verify their actual GLBs and manifests."""
import argparse, importlib.util, json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out.resolve(); summary = json.loads((out / 'summary.json').read_bytes())
    spec = importlib.util.spec_from_file_location('pipeline', ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py')
    pipeline = importlib.util.module_from_spec(spec); spec.loader.exec_module(pipeline)
    checks = []; native_total = 0
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        for row in summary['components']:
            for name, expected in row['dependencies_sha256'].items():
                if digest(ROOT / name) != expected: raise ValueError('composition dependency changed: ' + name)
            for name, expected in row['producer_sha256'].items():
                if digest(ROOT / name) != expected: raise ValueError('composition producer changed')
            candidate = ROOT / row['candidate_glb']
            if digest(candidate) != row['candidate_sha256']: raise ValueError('composed output changed')
            record = {'id': row['id'], 'candidate_glb_sha256': digest(candidate)}
            npz = candidate.with_suffix('.npz')
            if candidate.parent == out / row['id'] and npz.exists():
                mesh = np.load(npz)
                pipeline.save_mesh(folder, 'candidate', mesh['positions_mm'], mesh['triangles'], mesh['material_ids'], [v or None for v in mesh['palette'].tolist()], mesh['unit_ids'])
                if digest(folder / 'candidate.glb') != digest(candidate): raise ValueError('mesh payload / actual export mismatch')
                record['npz_sha256'] = digest(npz); record['full_glb_reexport_byte_exact'] = True
            for unit in row['shell_operations']:
                guard = unit.get('validation', {})
                if 'sampled_deviation_mm' in guard and guard['sampled_deviation_mm']['max'] > guard['sampled_limit_mm'] + .001:
                    raise ValueError('composed LOD exceeds edited-source guard')
            checks.append(record)
    result = {'summary_sha256': digest(out / 'summary.json'), 'components': checks,
              'full_glb_reexports': sum(c.get('full_glb_reexport_byte_exact', False) for c in checks),
              'dependencies_verified': True, 'producer_sha256': digest(Path(__file__))}
    (out / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Validated', len(checks), 'definitions;', result['full_glb_reexports'], 'byte-exact full GLB reexports')

if __name__ == '__main__': main()
