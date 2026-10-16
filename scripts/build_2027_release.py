#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build and verify the four 2027 asset archives from checksum-pinned CAD.

Run with ocpenv/bin/python. Needs the Rust release CLI, the CAD environment,
usd-core, and python/requirements-simplification.txt. No publishing is performed.
Existing complete source packages are verified and reused; choose a fresh work
directory after changing export settings. Failed exports retain their logs.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from export_field_package import GlbWriter, sha256
from export_source_package import dump
from gltf_scene import read_glb_local_nodes, read_glb_nodes
import provenance
from simplify_package import simplify_glb


def run(command, log):
    print('running ' + ' '.join(map(str, command)), flush=True)
    with Path(log).open('w') as output:
        result = subprocess.run(list(map(str, command)), cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}); see {log}\n{Path(log).read_text()[-4000:]}")


def optimize(source, output):
    """Simplify component meshes, then recompose the arena from those components."""
    if output.exists():
        if (output / 'mesh-simplification.json').exists():
            return
        raise ValueError(f'incomplete optimized output: {output}')
    output.mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file() and path.suffix in {'.json', '.glb'}:
            shutil.copy2(path, output / path.name)
    manifest = json.loads((output / 'manifest.json').read_text())
    sidecar = json.loads((output / 'articulation.json').read_text())
    results = {}
    full = {k: GlbWriter('FULL-MAP', provenance.glb_asset('build_2027_release.py', manifest['source_file'],
                        manifest['source_sha256'], frame='Z-up arena, metres', collision=k == 'collision'))
            for k in ('visual', 'collision')}
    for name, entry in manifest['assets'].items():
        if name == 'full-map':
            continue
        results[name] = {}
        for kind in ('visual', 'collision'):
            path = output / entry[kind]
            binding = sidecar['assets'][name]['files'][kind]
            if sha256(path) != entry[kind + '_sha256'] or binding['sha256'] != entry[kind + '_sha256']:
                raise ValueError('input mesh hash mismatch')
            record = simplify_glb(path, error_mm=1, binding=binding,
                                  sampled_limit_mm=2, deviation_samples=512, lock_borders=True)
            record['input_sha256'] = entry[kind + '_sha256']
            entry[kind + '_sha256'] = binding['sha256'] = sha256(path)
            entry['triangles' if kind == 'visual' else 'collision_triangles'] = record['after_triangles']
            entry[kind + '_bytes'] = path.stat().st_size
            results[name][kind] = record
            for node, points, triangles, colours, matrix, extras in read_glb_local_nodes(path, include_extras=True):
                for i, placement in enumerate(entry['placements_in_source_arena_frame']):
                    placed_extras = copy.deepcopy(extras)
                    if identity := placed_extras.get('cad_source'):
                        identity['source_occurrence_path'] = (placement.get('source_occurrence_path', [])
                                                               + identity.get('relative_occurrence_path', []))
                    full[kind].add_node(f'{name}_{i}_{node}', points, triangles, colours,
                        matrix=np.asarray(placement['matrix_local_to_arena']) @ matrix, extras=placed_extras)
            print(f"{source.name}/{name}/{kind}: {record['before_triangles']} -> {record['after_triangles']} triangles", flush=True)
        entry['mesh_simplification'] = {k: {f: v for f, v in rec.items() if f != 'primitives'} for k, rec in results[name].items()}
        entry['step']['archive'] = 'rm2027-cad-step.zip'
        entry['collision_method'] = 'meshopt-simplification-v1; borders locked, 1 mm error, 2 mm sampled deviation limit'
        clouds = [points for _, points, _, _ in read_glb_nodes(output / entry['visual'])]
        entry['bbox_local_m'] = [np.min([p.min(0) for p in clouds], axis=0).tolist(),
                                 np.max([p.max(0) for p in clouds], axis=0).tolist()]
    for kind, writer in full.items():
        entry = manifest['assets']['full-map']
        writer.write(output / entry[kind])
        entry[kind + '_sha256'] = sha256(output / entry[kind])
        entry['triangles' if kind == 'visual' else 'collision_triangles'] = writer.triangles
    dump(output / 'articulation.json', sidecar)
    manifest['articulation']['sha256'] = sha256(output / 'articulation.json')
    manifest['mesh_simplification'] = {'error_limit_mm': 1, 'sampled_limit_mm': 2,
        'samples_per_direction': 512, 'open_borders_locked': True,
        'note': 'Sampled deviation from source tessellation, not a certified maximum distance from CAD.'}
    manifest['collision_contract'] = 'Source tessellation simplified with locked borders and component preservation; no collision exclusions or convex decomposition.'
    dump(output / 'manifest.json', manifest)
    dump(output / 'mesh-simplification.json', results)


def verify_package(root, include_cad=True):
    manifest = json.loads((root / 'manifest.json').read_text())
    if not manifest['body_coverage']['complete'] or manifest['body_coverage']['unowned']:
        raise ValueError('incomplete body coverage')
    count = 0
    for name, entry in manifest['assets'].items():
        for kind in ('visual', 'collision'):
            if sha256(root / entry[kind]) != entry[kind + '_sha256']:
                raise ValueError(f'{root}/{name}/{kind}: hash mismatch')
            # Parsing meshes catches invalid accessors and bad indices as well
            # as truncated files; every transformed coordinate must be finite.
            triangles = 0
            for _, points, faces, _ in read_glb_nodes(root / entry[kind]):
                if not np.isfinite(points).all() or faces.min() < 0 or faces.max() >= len(points):
                    raise ValueError(f'{name}: invalid mesh')
                triangles += len(faces)
            if triangles != entry['triangles' if kind == 'visual' else 'collision_triangles']:
                raise ValueError(f'{name}: triangle count mismatch')
            count += 1
        if name != 'full-map' and include_cad:
            if sha256(root / entry['step']['file']) != entry['step']['sha256'] or not entry['step']['validation']['ok']:
                raise ValueError(f'{name}: CAD validation failed')
    sidecar = root / manifest['articulation']['file']
    if sha256(sidecar) != manifest['articulation']['sha256']:
        raise ValueError('semantic descriptor hash mismatch')
    from articulated_scene import load_asset
    for name, entry in manifest['assets'].items():
        if entry.get('semantics'):
            load_asset(root, name, entry)
    return {'glb_references_verified': count, 'body_coverage': manifest['body_coverage'],
            'source_sha256': manifest['source_sha256']}


def verify_simulators(root):
    from pxr import Usd
    path = root / 'simulators' / 'rm_map_equipment'
    manifest = json.loads((path / 'manifest.json').read_text())
    for filename, checksum in manifest['files_sha256'].items():
        if sha256(path / filename) != checksum:
            raise ValueError(f'simulator hash mismatch: {filename}')
    for name in manifest['assets']:
        folder = path / name
        for filename in ('model.sdf', 'model.urdf'):
            doc = ET.parse(folder / filename)
            for node in doc.findall('.//uri'):
                if not (folder / node.text).is_file():
                    raise ValueError('SDF mesh missing')
            for node in doc.findall('.//mesh[@filename]'):
                prefix = 'package://rm_map_equipment/'
                value = node.get('filename')
                if not value.startswith(prefix) or not (path / value[len(prefix):]).is_file():
                    raise ValueError('URDF mesh missing')
        if not Usd.Stage.Open(str(folder / 'model.usdc')):
            raise ValueError('USD stage cannot be opened')
    return {'assets': len(manifest['assets']), 'files_verified': len(manifest['files_sha256']),
            'scope': 'SDF/URDF structure and mesh paths, USD stages, file hashes; source rest pose, no mechanical joint bindings'}


def archive(output, files):
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, path in sorted(files.items()):
            z.write(path, name)
        z.write(ROOT / 'NOTICE.md', 'NOTICE.md')
    with zipfile.ZipFile(output) as z:
        if z.testzip():
            raise ValueError('archive CRC verification failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'out/rm2027')
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rm2027/release')
    parser.add_argument('--prepare', action='store_true', help='download, index, split, and export missing source packages first')
    args = parser.parse_args()
    work, output = args.work_dir.resolve(), args.out.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f'release directory exists: {output}')
    configs = json.loads((ROOT / 'rules/sources-2027.json').read_text())['sources']
    python = sys.executable
    if args.prepare:
        for config in configs:
            src = ROOT / 'source' / config['source']
            dest = work / src.stem
            dest.mkdir(exist_ok=True)
            run([python, ROOT / 'source/download.py', 'fetch', src.name], dest / 'download.log')
            for command, log in [
                ([ROOT / 'target/release/rm-map-tools', 'index', src, '-o', dest / 'source.p21idx'], 'index.log'),
                ([ROOT / 'target/release/rm-map-tools', 'inspect', dest / 'source.p21idx', '--json', dest / 'inspection.json'], 'inspect.log'),
                ([ROOT / 'target/release/rm-map-tools', 'split', dest / 'source.p21idx', '-o', dest / 'split', '--jobs', '4'], 'split.log'),
                ([python, ROOT / 'python/p21index.py', src, dest / 'source.npz'], 'python-index.log')]:
                run(command, dest / log)
            package = work / 'packages' / config['id']
            if not (package / 'models/catalog.json').exists():
                run([python, ROOT / 'python/export_source_package.py', dest / 'split', dest / 'source.npz',
                     '--config', ROOT / 'rules/sources-2027.json', '--source', config['id'], '--out', package], dest / 'export.log')
    checks, files = {}, {k: {} for k in ('cad', 'glb', 'simulators', 'viewer')}
    catalog = {'schema_version': 1, 'copyright': provenance.COPYRIGHT, 'models': []}
    for config in configs:
        name = config['id']
        raw = work / 'packages' / name
        if sha256(ROOT / 'source' / config['source']) != config['source_sha256']:
            raise ValueError(f'{name}: source hash mismatch')
        source_manifest = json.loads((raw / 'manifest.json').read_text())
        if (source_manifest['source_sha256'] != config['source_sha256']
                or source_manifest['source_configuration_sha256'] != hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()):
            raise ValueError(f'{name}: package was built from a different source configuration')
        checks[name] = {'source': verify_package(raw), 'simulators': verify_simulators(raw)}
        optimized = work / 'optimized' / name
        optimize(raw, optimized)
        checks[name]['optimized'] = verify_package(optimized, include_cad=False)
        manifest = json.loads((raw / 'manifest.json').read_text())
        cad_manifest = {k: v for k, v in manifest.items() if k != 'assets'}
        cad_manifest['assets'] = {n: {k: v for k, v in e.items() if k in
            ('label', 'step', 'source_products', 'source_product_id', 'source_occurrence_ids', 'placements_in_source_arena_frame', 'local_up_axis')}
            for n, e in manifest['assets'].items() if 'step' in e}
        cad_manifest_path = work / (name + '-cad-manifest.json')
        dump(cad_manifest_path, cad_manifest)
        files['cad'][name + '/manifest.json'] = cad_manifest_path
        for p in (raw / 'cad').rglob('*'):
            if p.is_file():
                files['cad'][name + '/' + str(p.relative_to(raw))] = p
        for p in optimized.iterdir():
            if p.is_file():
                files['glb'][name + '/' + p.name] = p
        for p in (raw / 'simulators').rglob('*'):
            if p.is_file():
                files['simulators'][name + '/' + str(p.relative_to(raw / 'simulators'))] = p
        for model in json.loads((raw / 'models/catalog.json').read_text())['models']:
            model['file'] = name + '/' + model['file']
            path = raw / 'models' / Path(model['file']).name
            if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != model['sha256']:
                raise ValueError('viewer model hash mismatch')
            files['viewer']['models/' + model['file']] = path
            catalog['models'].append(model)
    output.mkdir(parents=True)
    dump(work / 'viewer-catalog.json', catalog)
    files['viewer']['models/catalog.json'] = work / 'viewer-catalog.json'
    summary = {'schema_version': 1, 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'configuration_sha256': sha256(ROOT / 'rules/sources-2027.json'), 'sources': checks,
        'viewer_models': len(catalog['models']),
        'limitations': ['2027 mechanical joint bindings and match controllers are not authored.',
            'No 2026 equipment grafts, hidden-geometry reconstructions, texture selections or joint limits are reused.',
            'Simulator checks cover file structure, paths and USD stages; no dynamics or target simulator runtime calibration.',
            'Optimized GLBs use 1 mm simplification error, locked borders, component preservation and 2 mm sampled deviation limits.',
            'Source-rest-pose simulator and viewer meshes are unsimplified; optimized GLBs are a separate runtime representation.']}
    for key, filename in [('cad', 'rm2027-cad-step.zip'), ('glb', 'rm2027-glb-optimized.zip'),
                          ('simulators', 'rm2027-simulators.zip'), ('viewer', 'docs-viewer-models.zip')]:
        print('packaging ' + filename, flush=True)
        archive(output / filename, files[key])
    dump(output / 'validation-summary.json', summary)
    (output / 'SHA256SUMS.txt').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(output.iterdir()) if p.is_file()))
    print(f'Verified release artifacts: {output}', flush=True)


if __name__ == '__main__':
    main()
