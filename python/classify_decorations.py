# SPDX-License-Identifier: MIT OR Apache-2.0
"""Classify reviewed text/logo primitives and remove their collision geometry.

Exact node/material selectors work on walls and elevated surfaces without a
height or orientation cutoff. Visual geometry and source node indices stay intact.
"""
import argparse
import copy
import json
import shutil
from pathlib import Path

from collision_artwork import strip
from deploy_field import asset_path, digest, read_manifest
from gltf_scene import mesh_instances, read_glb, write_glb
from simplify_package import check_bindings, scene_triangles


def classify(document, binary, selections):
    doc = copy.deepcopy(document)
    lookup = {}
    for ni, pi, _, _, material in mesh_instances(doc, binary):
        key = (doc['nodes'][ni].get('name'), doc['materials'][material].get('name'))
        lookup.setdefault(key, []).append((ni, pi))
    selected = set()
    records = []
    for selection in selections:
        key = (selection['node'], selection['material'])
        matches = lookup.get(key, [])
        if len(matches) != 1 or matches[0] in selected:
            raise ValueError(f'missing, ambiguous or duplicate decoration: {key}')
        ni, pi = matches[0]
        selected.add((ni, pi))
        node = doc['nodes'][ni]
        # Isolate this occurrence when source meshes are shared.
        if not any(r['node_index'] == ni for r in records):
            mesh = copy.deepcopy(doc['meshes'][node['mesh']])
            node['mesh'] = len(doc['meshes'])
            doc['meshes'].append(mesh)
        primitive = doc['meshes'][node['mesh']]['primitives'][pi]
        meta = primitive.setdefault('extras', {}).setdefault('rm', {})
        meta.update(layer='decoration', collision=False, kind=selection['kind'])
        meta['roles'] = sorted(set(meta.get('roles', [])) | {'decoration'})
        records.append(dict(selection, node_index=ni, primitive=pi))
    return doc, records


def compose(source, output, rules):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError('output must be a new directory outside source')
    manifest = read_manifest(source)
    if manifest.get('decoration_layer'):
        raise ValueError('package already classified')
    art = manifest.get('articulation')
    sidecar = None
    if art:
        path = asset_path(source, art['file'])
        if digest(path) != art['sha256']:
            raise ValueError('articulation checksum mismatch')
        sidecar = json.loads(path.read_text())
    prepared, report = [], {}
    for name, selections in rules['assets'].items():
        entry = manifest['assets'][name]
        docs = {}
        for kind in ('visual', 'collision'):
            path = asset_path(source, entry[kind])
            if digest(path) != entry[kind + '_sha256']:
                raise ValueError(f'checksum mismatch: {path}')
            docs[kind] = read_glb(path)
        if entry['visual'] == entry['collision']:
            raise ValueError('separate collision file required')
        visual, records = classify(*docs['visual'], selections)
        collision_selections = [dict(node=s['node'], material=s['material'])
                                for s in selections if not s.get('collision_absent', False)]
        # Absence is reviewed explicitly, never silently accepted after a failed match.
        cd, cb = docs['collision']
        keys = {(cd['nodes'][ni].get('name'), cd['materials'][m].get('name'))
                for ni, _, _, _, m in mesh_instances(cd, cb)}
        for s in selections:
            if s.get('collision_absent') and (s['node'], s['material']) in keys:
                raise ValueError('decoration expected absent from collision is present')
        collision, packed, removed = strip(cd, cb, collision_selections)
        visual_binary = docs['visual'][1]
        backing = None
        if name in rules.get('backing_repairs', {}):
            from decoration_backing import repair
            visual, visual_binary, collision, packed, backing = repair(
                visual, visual_binary, collision, packed, rules['backing_repairs'][name])
        report[name] = dict(selections=records, removed_triangles=sum(r['triangles'] for r in removed),
                            before_collision_triangles=scene_triangles(cd), removed=removed)
        if backing:
            report[name]['backing_repair'] = backing
        report[name]['net_collision_triangles_removed'] = scene_triangles(cd) - scene_triangles(collision)
        for kind, doc, binary in [('visual', visual, visual_binary), ('collision', collision, packed)]:
            binding = sidecar['assets'].get(name, {}).get('files', {}).get(kind) if sidecar else None
            if binding:
                if binding['sha256'] != entry[kind + '_sha256']:
                    raise ValueError('semantic checksum mismatch')
                check_bindings(doc, binding)
            prepared.append((name, kind, doc, binary, binding))
    shutil.copytree(source, output)
    for name, kind, doc, binary, binding in prepared:
        entry = manifest['assets'][name]
        path = asset_path(output, entry[kind])
        write_glb(path, doc, binary)
        entry[kind + '_sha256'] = digest(path)
        entry[kind + '_bytes'] = path.stat().st_size
        entry['triangles' if kind == 'visual' else 'collision_triangles'] = scene_triangles(doc)
        if binding:
            binding['sha256'] = digest(path)
    if sidecar:
        sidecar.setdefault('layers', {})['decoration'] = dict(visible_by_default=True,
            purpose='Reviewed text and logos at any elevation; excluded from collision.')
        path = asset_path(output, art['file'])
        path.write_text(json.dumps(sidecar, indent=2) + '\n')
        art['sha256'] = digest(path)
    report_path = output / 'decoration-layer.json'
    report_path.write_text(json.dumps(dict(schema_version=1, layer='decoration',
        source_manifest_sha256=digest(source/'manifest.json'), assets=report), indent=2) + '\n')
    manifest['decoration_layer'] = dict(file=report_path.name, sha256=digest(report_path),
        visible_by_default=True, collision=False)
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--rules', required=True, type=Path)
    args = parser.parse_args()
    report = compose(args.source, args.output, json.loads(args.rules.read_text()))
    print(json.dumps({name: r['removed_triangles'] for name, r in report.items()}, indent=2))
