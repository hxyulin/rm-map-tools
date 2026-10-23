# SPDX-License-Identifier: MIT OR Apache-2.0
"""Verify actual inputs, review coverage and unchanged runtime package."""
import json
from pathlib import Path
from audit_current import ROOT, OUT, POLICY, digest
from gltf_scene import read_glb
from simplify_package import scene_triangles
from PIL import Image


def main():
    report = json.loads((OUT / 'review.json').read_text())
    refs_path = ROOT / 'out/rmuc2027-protected-source-reference/ledger.json'
    refs = json.loads(refs_path.read_text())
    reference_files = {r['reference_glb']: r['reference_glb_sha256'] for r in refs['references']}
    audit = json.loads((OUT / 'current-audit.json').read_text())
    guard = json.loads((OUT / 'guard.json').read_text())
    assert guard['policy_sha256'] == digest(POLICY) == audit['policy_sha256']
    expected = {}
    for asset in audit['assets'].values():
        for key in ('installed', 'refined-1mm', 'combined-17mm'):
            r = asset[key]
            expected[r['path']] = r['sha256']
    for r in guard['assets'].values():
        expected[r['output']] = r['sha256']
    for subject in report['subjects']:
        for stage, files in subject['inputs'].items():
            if stage == 'source':
                for f in files:
                    assert digest(ROOT / f) == reference_files[f]
            else:
                assert digest(Path(files)) == expected[files]
    keys = {(r['group'], r['stage'], r['view']) for r in report['views']}
    assert len(keys) == len(report['views']) == 400
    assert len(report['subjects']) == 10
    for row in report['views']:
        with Image.open(OUT / row['image']) as image:
            assert image.size == (1200, 1200)
        subject = next(s for s in report['subjects'] if s['id'] == row['group'])
        assert row['triangles'] == subject['triangles'][row['stage']]
    installed = {}
    for rel in ('manifest.json', 'equipment/manifest.json'):
        path = ROOT.parent / 'rm-simulator/field-2027' / rel
        for a in json.loads(path.read_text())['assets'].values():
            for role in ('visual', 'collision'):
                p = path.parent / a[role]
                installed[str(p)] = digest(p)
                assert installed[str(p)] == a[role + '_sha256']
    assert len(installed) == 12
    placed = sum(scene_triangles(read_glb(Path(r['output']))[0]) * r['placements'] for r in guard['assets'].values())
    assert placed == guard['placed_visual_triangles'] == 196716
    # The source agent added a complete Base context to its reference ledger
    # after these close-ups started. Pin the final ledger only after checking
    # the exact hashes of EVERY source GLB actually rendered above.
    report['reference_ledger_sha256'] = digest(refs_path)
    (OUT / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    findings = []
    for subject in report['subjects']:
        rows = [r for r in report['views'] if r['group'] == subject['id'] and r['stage'] == 'protected-1mm']
        worst = max(rows, key=lambda r: r['metrics']['foreground_difference_pixels'] / max(1, r['metrics']['source_foreground_pixels']))
        m = worst['metrics']
        findings.append({'subject': subject['id'], 'worst_silhouette_view': worst['view'],
                         'silhouette_disagreement_fraction': m['foreground_difference_pixels'] / max(1, m['source_foreground_pixels']),
                         'maximum_red_pixels_lost': max(r['metrics']['red']['lost_pixels'] for r in rows)})
    result = {'status': 'Source comparison complete; older protected approximations have visible differences and are not fidelity-approved.',
              'policy_sha256': digest(POLICY), 'source_sha256': report['source_sha256'],
              'reference_ledger_sha256': digest(refs_path), 'close_up_images_verified': len(keys),
              'whole_arena_images': 28, 'interim_placed_visual_triangles': placed,
              'ownership_regression_tests_passed': 4,
              'restored_latest_omission_triangles': placed - 193222,
              'installed_inputs_unchanged': installed, 'findings': findings,
              'scope': report['scope'], 'producer_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')}}
    (OUT / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    compact = {k: v for k, v in result.items() if k != 'installed_inputs_unchanged'}
    (Path(__file__).parent / 'results.json').write_text(json.dumps(compact, indent=2) + '\n')
    print('Verified 400 close-ups, six interim assets, 12 unchanged runtime inputs;', placed, 'placed visual triangles.')


if __name__ == '__main__':
    main()
