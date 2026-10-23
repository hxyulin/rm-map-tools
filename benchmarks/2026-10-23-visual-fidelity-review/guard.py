# SPDX-License-Identifier: MIT OR Apache-2.0
"""Withdraw latest lossy detail edits in protected visual scopes.

This freezes the accepted 1 mm input pending the original STEP review. It does
not declare that input optically equivalent to STEP, or install runtime assets.
"""
import copy
import json
from pathlib import Path
import shutil
import sys
from audit_current import ROOT, OUT, POLICY, digest, scopes

sys.path.insert(0, str(ROOT / 'python'))
from cad_glb_composition import RigidComposer
from gltf_scene import accessor, read_glb, scene_nodes, write_glb
from simplify_package import compact, scene_triangles
import numpy as np


def protected_nodes(doc, asset, policy):
    owners = scopes(doc, asset)
    ids = set(policy['protected_source_body_ids'].get(asset, [])) | set(policy.get('protected_source_shell_ids', {}).get(asset, []))
    prefixes = policy['protected_component_prefixes']
    return {i for i, (component, body) in owners.items()
            if asset in policy['protected_assets'] or body in ids or
            any(component.startswith(prefix) for prefix in prefixes)}


def restore(candidate, reference, output, asset, policy):
    cd, cb = read_glb(candidate)
    rd, rb = read_glb(reference)
    selected = protected_nodes(rd, asset, policy)
    assert len(cd['nodes']) == len(rd['nodes'])
    for a, b in zip(cd['nodes'], rd['nodes']):
        assert {k: v for k, v in a.items() if k != 'mesh'} == {k: v for k, v in b.items() if k != 'mesh'}
    output.parent.mkdir(parents=True, exist_ok=True)
    if asset in policy['protected_assets']:
        shutil.copyfile(reference, output)
    elif not selected:
        shutil.copyfile(candidate, output)
    else:
        c = RigidComposer()
        c.append_definition('candidate', cd, cb)
        c.append_definition('reference', rd, rb)
        nodes, roots = c.definitions['candidate']
        source_nodes, _ = c.definitions['reference']
        c.document['nodes'] = copy.deepcopy(nodes)
        c.document['scenes'][0]['nodes'] = roots.copy()
        c.document['asset'] = copy.deepcopy(cd['asset'])
        c.document['asset'].setdefault('extras', {})['visual_fidelity_guard'] = {
            'policy_sha256': digest(POLICY), 'reference_sha256': digest(reference),
            'status': 'Protected scopes frozen at accepted 1 mm; full STEP review pending.'}
        for i in selected:
            c.document['nodes'][i].pop('mesh', None)
            if 'mesh' in source_nodes[i]:
                c.document['nodes'][i]['mesh'] = source_nodes[i]['mesh']
        binary = compact(c.document, c.binary)
        write_glb(output, c.document, binary)
    actual, ab = read_glb(output)
    # Reopened, exact indexed attributes/materials for protected AND unprotected
    # nodes. This also catches shared-mesh edits leaking across scope boundaries.
    for i, world, parent in scene_nodes(actual):
        sd, sb = (rd, rb) if i in selected else (cd, cb)
        n, s = actual['nodes'][i], sd['nodes'][i]
        assert ('mesh' in n) == ('mesh' in s)
        if 'mesh' not in n:
            continue
        ap, sp = actual['meshes'][n['mesh']]['primitives'], sd['meshes'][s['mesh']]['primitives']
        assert len(ap) == len(sp)
        for a, b in zip(ap, sp):
            assert actual['materials'][a['material']] == sd['materials'][b['material']]
            assert set(a['attributes']) == set(b['attributes'])
            for key in a['attributes']:
                assert np.array_equal(accessor(actual, ab, a['attributes'][key]), accessor(sd, sb, b['attributes'][key]))
            assert np.array_equal(accessor(actual, ab, a['indices']), accessor(sd, sb, b['indices']))
    return {'input': str(candidate), 'input_sha256': digest(candidate),
            'protected_reference': str(reference), 'protected_reference_sha256': digest(reference),
            'output': str(output), 'sha256': digest(output), 'protected_nodes': sorted(selected),
            'before': scene_triangles(cd), 'after': scene_triangles(actual)}


def main():
    policy = json.loads(POLICY.read_text())
    refined = json.loads((ROOT / 'out/rmuc2027-runtime-opportunities/refined.json').read_text())
    plan = json.loads((ROOT / 'benchmarks/2026-10-23-feature-investigation/plan.json').read_text())
    old = next(l for l in plan['levels'] if l['id'] == 'combined-visual')
    records = {}
    total = 0
    for asset, entry in old['files'].items():
        source = ROOT / entry['path']
        assert digest(source) == entry['sha256']
        baseline = ROOT / 'out/rmuc2027-runtime-opportunities' / refined['assets'][asset + '/visual']['output']
        assert digest(baseline) == refined['assets'][asset + '/visual']['sha256']
        target = OUT / 'protected-1mm' / (asset + '.glb')
        records[asset] = restore(source, baseline, target, asset, policy)
        copies = refined['assets'][asset + '/visual']['placements']
        records[asset]['placements'] = copies
        total += records[asset]['after'] * copies
    report = {'status': 'Latest omissions withdrawn in protected visual scopes; earlier source fidelity under review.',
              'policy_sha256': digest(POLICY), 'placed_visual_triangles': total, 'assets': records,
              'verification': 'Reopened exact attributes, indices and materials from 1mm in protected nodes; combined trial elsewhere. Installed package untouched.'}
    (OUT / 'guard.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Protected interim visual candidate:', total, flush=True)


if __name__ == '__main__':
    main()
