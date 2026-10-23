# SPDX-License-Identifier: MIT OR Apache-2.0
"""Matched protected-scope views against fresh original STEP tessellation."""
import copy
import argparse
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from audit_current import ROOT, OUT, POLICY, digest, scopes
import numpy as np
from PIL import Image
from gltf_scene import accessor, read_glb, scene_nodes, local_matrix


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


FRAME = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])


def load(path, placement, select=None, wrapper=None):
    d, b = read_glb(path)
    if wrapper is not None:
        d = copy.deepcopy(d)
        roots = d['scenes'][d.get('scene', 0)]['nodes']
        wi = len(d['nodes'])
        d['nodes'].append({'matrix': np.asarray(wrapper).T.ravel().tolist(), 'children': roots})
        d['scenes'][d.get('scene', 0)]['nodes'] = [wi]
    ext = local_matrix({'translation': placement.get('translation_m', [0, 0, 0]),
                        'rotation': placement.get('rotation_xyzw', [0, 0, 0, 1])})
    arrays = [[], [], [], [], []]
    texture = np.zeros((1, 1, 3), np.uint8)
    for i, w, parent in scene_nodes(d):
        n = d['nodes'][i]
        if 'mesh' not in n or (select is not None and i not in select):
            continue
        matrix = ext @ w
        for pr in d['meshes'][n['mesh']]['primitives']:
            p = accessor(d, b, pr['attributes']['POSITION']).astype(float)
            t = accessor(d, b, pr['indices']).reshape(-1, 3)
            if np.linalg.det(matrix[:3, :3]) < 0:
                t = t[:, ::-1]
            arrays[0].append(((p @ matrix[:3, :3].T + matrix[:3, 3]) @ FRAME.T)[t])
            mat = d['materials'][pr['material']]
            pbr = mat.get('pbrMetallicRoughness', {})
            textured = 'baseColorTexture' in pbr
            color = mat.get('extras', {}).get('step_colour_srgb')
            if color is None:
                color = pbr.get('baseColorFactor', [.65, .65, .65, 1])[:3]
            arrays[1].append(np.tile(color, (len(t), 1)))
            arrays[3].append(np.full(len(t), textured, np.int32))
            arrays[4].append(np.full(len(t), i, np.int32))
            if textured:
                im = d['images'][d['textures'][pbr['baseColorTexture']['index']]['source']]
                bv = d['bufferViews'][im['bufferView']]
                tex = np.asarray(Image.open(io.BytesIO(b[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']])).convert('RGB'))
                if texture.shape != (1, 1, 3):
                    assert np.array_equal(texture, tex), 'multiple atlases unsupported'
                texture = tex
                arrays[2].append(accessor(d, b, pr['attributes']['TEXCOORD_0'])[t])
            else:
                arrays[2].append(np.zeros((len(t), 3, 2)))
    assert arrays[0], f'Empty protected selection: {path}'
    return tuple(np.concatenate(a) for a in arrays) + (texture,)


def concatenate(items):
    textures = [d[5] for d in items if d[3].any()]
    assert not textures or all(np.array_equal(t, textures[0]) for t in textures)
    return tuple(np.concatenate([d[i] for d in items]) for i in range(5)) + (textures[0] if textures else np.zeros((1, 1, 3), np.uint8),)


def select(path, asset, component=None, body=None):
    d, _ = read_glb(path)
    own = scopes(d, asset)
    return {i for i, (c, b) in own.items() if (component is None or c == component) and (body is None or b == body)}


def metrics(a, b):
    fg_a = np.any(a != a[0, 0], axis=2)
    fg_b = np.any(b != b[0, 0], axis=2)
    def color(image, channel):
        im = image.astype(float)
        return (im[:, :, channel] > 70) & (im[:, :, channel] > np.max(np.delete(im, channel, axis=2), axis=2) * 1.3)
    result = {'foreground_difference_pixels': int(np.count_nonzero(fg_a ^ fg_b)),
              'source_foreground_pixels': int(fg_a.sum()),
              'rgb_difference_over_10_pixels': int(np.count_nonzero(np.max(np.abs(a.astype(int) - b.astype(int)), axis=2) > 10))}
    for channel, name in enumerate(('red', 'green', 'blue')):
        x, y = color(a, channel), color(b, channel)
        result[name] = {'source_pixels': int(x.sum()), 'candidate_pixels': int(y.sum()),
                        'lost_pixels': int((x & ~y).sum()), 'gained_pixels': int((y & ~x).sum())}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group-prefix', help='Refresh only matching subjects in an existing review.')
    args = parser.parse_args()
    reference = json.loads((ROOT / 'out/rmuc2027-protected-source-reference/ledger.json').read_text())
    guard = json.loads((OUT / 'guard.json').read_text())
    audit = json.loads((OUT / 'current-audit.json').read_text())
    refs = {r['id']: r for r in reference['references']}
    manifests = {}
    package = ROOT.parent / 'rm-simulator/field-2027'
    for rel in ('manifest.json', 'equipment/manifest.json'):
        manifests.update(json.loads((package / rel).read_text())['assets'])
    subjects = [('tech-core-face', 'Tech Core · crucial face', 'tech-core', ['technology-core/tool-head'])]
    rune = sorted(k for k in refs if k.startswith('rune/'))
    subjects += [('rune', 'Power Rune · complete assembly', 'rune', rune)]
    for bank in ('a', 'b'):
        subjects.append((f'rune-arm-{bank}', f'Power Rune · bank {bank.upper()} arm', 'rune', [f'rune/banks/bank-{bank}/arm-0']))
    for i in range(3):
        subjects.append((f'outpost-armor-{i}', f'Outpost armor {i + 1}', 'outpost', [f'outpost/rotor/module-{i}']))
    base_groups = json.loads(POLICY.read_text())['base_module_groups']
    for i, body in enumerate((4099408, 4121375, 4143351)):
        subjects.append((f'base-armor-{body}', f'Base armor · complete module {i + 1}', 'base', ['base/source-model']))
    stages = [('installed', 'Installed visual'), ('refined-1mm', 'Accepted merged 1 mm'),
              ('combined-17mm', 'Previous 17 mm trial'), ('protected-1mm', 'Protected interim candidate')]
    report = {'source_sha256': reference['source_sha256'], 'reference_ledger_sha256': digest(ROOT / 'out/rmuc2027-protected-source-reference/ledger.json'),
              'subjects': [], 'stages': dict(stages), 'views': [],
              'scope': 'Fresh unsimplified original STEP .4mm/.25rad, full protected modules, source rest placement. 1200px orthographic source-color flat two-sided diagnostics, not runtime PBR or all animation poses. Differences are review flags, not automatic acceptance.'}
    if args.group_prefix:
        old = json.loads((OUT / 'review.json').read_text())
        report['subjects'] = [s for s in old['subjects'] if not s['id'].startswith(args.group_prefix)]
        report['views'] = [r for r in old['views'] if not r['group'].startswith(args.group_prefix)]
        subjects = [s for s in subjects if s[0].startswith(args.group_prefix)]
    directions = [('oblique', (1, .5, 1)), ('reverse', (-1, .5, -1)),
                  ('front', (0, .000001, 1)), ('back', (0, .000001, -1)),
                  ('side', (1, .000001, 0)), ('other-side', (-1, .000001, 0)),
                  ('top', (0, 1, .000001)), ('bottom', (0, -1, .000001))]
    renderer = module('fidelity_raster', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        helper = tmp / 'raster'
        subprocess.run(['clang++', '-O3', '-std=c++17', str(ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'), '-o', str(helper)], check=True)
        for group, title, asset, ids in subjects:
            placement = manifests[asset]['placements_in_source_arena_frame'][0]
            base_units = None
            if asset == 'base':
                module_index = (4099408, 4121375, 4143351).index(int(group.rsplit('-', 1)[1]))
                membership = base_groups[f'base.armor.{module_index}']
                base_units = set(membership['source_body_ids'] + membership['source_shell_ids'])
            original = []
            for key in ids:
                row = refs[key]
                path = ROOT / row['reference_glb']
                selection = None
                if base_units is not None:
                    source_doc, _ = read_glb(path)
                    selection = {i for i, n in enumerate(source_doc['nodes']) if n.get('extras', {}).get('source_unit_id') in base_units}
                original.append(load(path, placement, selection, wrapper=row['runtime']['component_rest_matrix_m']))
            source = concatenate(original)
            data = {'source': source}
            paths = {'source': [refs[k]['reference_glb'] for k in ids]}
            for stage, label in stages:
                path = Path(guard['assets'][asset]['output']) if stage == 'protected-1mm' else Path(audit['assets'][asset][stage]['path'])
                choices = []
                for key in ids:
                    row = refs[key]
                    if base_units is not None:
                        doc, _ = read_glb(path)
                        selection = {i for i, (_, b) in scopes(doc, asset).items() if b in base_units}
                    else:
                        selection = select(path, asset, row['component_id'])
                    choices.append(load(path, placement, selection))
                data[stage] = concatenate(choices)
                paths[stage] = str(path)
            # Camera always comes from STEP; large missing parts cannot silently
            # change framing and conceal a regression.
            folder = OUT / 'renders' / group
            folder.mkdir(parents=True, exist_ok=True)
            report['subjects'].append({'id': group, 'label': title, 'asset': asset,
                                       'triangles': {s: len(d[0]) for s, d in data.items()}, 'inputs': paths})
            for view, direction in directions:
                images = {}
                for stage, d in data.items():
                    path = folder / f'{stage}-{view}.webp'
                    images[stage] = renderer(d, source[0], direction, helper, tmp, tmp / 'frame.png')
                    Image.fromarray(images[stage]).save(path, lossless=True)
                    report['views'].append({'group': group, 'stage': stage, 'view': view,
                                            'image': str(path.relative_to(OUT)), 'triangles': len(d[0]),
                                            'metrics': None if stage == 'source' else metrics(images['source'], images[stage])})
            print('Rendered', group, report['subjects'][-1]['triangles'], flush=True)
    (OUT / 'review.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
