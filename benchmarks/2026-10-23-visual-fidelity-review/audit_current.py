# SPDX-License-Identifier: MIT OR Apache-2.0
"""Inventory protected visual scopes across the existing reduction stages.

Changed triangle payload is an audit flag, not proof of visible regression.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from gltf_scene import accessor, read_glb, scene_nodes

OUT = ROOT / 'out/rmuc2027-visual-fidelity-review'
POLICY = ROOT / 'rules/visual-fidelity-rmuc2027.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scopes(doc, asset):
    result = {}
    for i, world, parent in scene_nodes(doc):
        n = doc['nodes'][i]
        ex = n.get('extras', {})
        component, body = result.get(parent, ('', None))
        component = ex.get('component_id') or component
        body = ex.get('source_unit_id', body)
        match = re.fullmatch(r'source_body_(\d+)', n.get('name', ''))
        if match:
            body = int(match[1])
        result[i] = component, body
    return result


def inventory(path, asset):
    d, b = read_glb(path)
    ownership = scopes(d, asset)
    rows = {}
    policy = json.loads(POLICY.read_text())
    base_ids = set(policy['protected_source_body_ids']['base']) | set(policy.get('protected_source_shell_ids', {}).get('base', []))
    for i, world, parent in scene_nodes(d):
        n = d['nodes'][i]
        if 'mesh' not in n:
            continue
        component, body = ownership[i]
        if asset == 'rune':
            key = component or 'rune'
        elif component.startswith('technology-core/tool-head'):
            key = 'technology-core/tool-head'
        elif component.startswith('outpost/rotor/module-'):
            key = component
        elif asset == 'base' and body in base_ids:
            key = f'base/armor-{body}'
        else:
            continue
        row = rows.setdefault(key, {'triangles': 0, 'nodes': [], 'payloads': []})
        row['nodes'].append(i)
        for pr in d['meshes'][n['mesh']]['primitives']:
            t = accessor(d, b, pr['indices']).reshape(-1, 3)
            row['triangles'] += len(t)
            h = hashlib.sha256()
            h.update(json.dumps(d['materials'][pr['material']], sort_keys=True).encode())
            for name, ai in sorted(pr['attributes'].items()):
                h.update(name.encode())
                h.update(np.ascontiguousarray(accessor(d, b, ai)[t]).tobytes())
            h.update(np.ascontiguousarray(world).tobytes())
            row['payloads'].append(h.hexdigest())
    for row in rows.values():
        row['payload_sha256'] = hashlib.sha256(''.join(sorted(row.pop('payloads'))).encode()).hexdigest()
    return {'path': str(path), 'sha256': digest(path), 'scopes': rows}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    refined = json.loads((ROOT / 'out/rmuc2027-runtime-opportunities/refined.json').read_text())
    plan = json.loads((ROOT / 'benchmarks/2026-10-23-feature-investigation/plan.json').read_text())
    combined = next(l for l in plan['levels'] if l['id'] == 'combined-visual')['files']
    report = {'policy_sha256': digest(POLICY), 'assets': {},
              'meaning': 'Exact payload changes flag scopes requiring source comparison; they are not optical-equivalence measurements.'}
    for asset in ('tech-core', 'rune', 'outpost', 'base'):
        installed = ROOT.parent / 'rm-simulator/field-2027' / ('equipment' if asset in ('tech-core', 'base') else '') / (asset + '.glb')
        paths = {'installed': installed,
                 'refined-1mm': ROOT / 'out/rmuc2027-runtime-opportunities' / refined['assets'][asset + '/visual']['output'],
                 'combined-17mm': ROOT / combined[asset]['path']}
        report['assets'][asset] = {stage: inventory(path, asset) for stage, path in paths.items()}
        before = report['assets'][asset]['refined-1mm']['scopes']
        after = report['assets'][asset]['combined-17mm']['scopes']
        print(asset, 'protected triangles:', {s: sum(x['triangles'] for x in r['scopes'].values()) for s, r in report['assets'][asset].items()}, flush=True)
        report['assets'][asset]['latest_changes'] = [
            {'scope': key, 'before': before[key]['triangles'], 'after': after.get(key, {}).get('triangles', 0)}
            for key in before if before[key]['payload_sha256'] != after.get(key, {}).get('payload_sha256')]
    (OUT / 'current-audit.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
