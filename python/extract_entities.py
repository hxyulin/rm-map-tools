#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Extract checksum-pinned triangle selections into independently placed GLB assets.

Selections are explicit half-open triangle ranges, separately audited for visual
and collision inputs. Extraction preserves every triangle and material. Run before
any subsequent simplification, which can then use a policy for each new asset.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np
from gltf_scene import accessor, read_glb, scene_nodes, write_glb
from simplify_package import append_accessor, compact, scene_triangles


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def partition(document, binary, entities):
    """Return remainder and entity GLBs; each entity's origin is in scene metres."""
    if document.get('animations') or document.get('skins'):
        raise ValueError('only rigid unanimated assets can be extracted')
    worlds = {i: m for i, m, _ in scene_nodes(document)}
    names = {}
    for i in worlds:
        names.setdefault(document['nodes'][i].get('name'), []).append(i)
    selected = {}
    masks = [{} for _ in entities]
    for ei, entity in enumerate(entities):
        origin = np.asarray(entity['origin_m'], float)
        if origin.shape != (3,) or not np.isfinite(origin).all():
            raise ValueError('origin_m must be three finite metres')
        for part in entity['parts']:
            matches = names.get(part['node'], [])
            if len(matches) != 1:
                raise ValueError('node selector must match exactly once')
            ni = matches[0]
            node = document['nodes'][ni]
            if 'weights' in node:
                raise ValueError('morphed nodes are unsupported')
            pi = part['primitive']
            if type(pi) is not int or not 0 <= pi < len(document['meshes'][node['mesh']]['primitives']):
                raise ValueError('invalid primitive index')
            primitive = document['meshes'][node['mesh']]['primitives'][pi]
            if primitive.get('mode', 4) != 4 or 'targets' in primitive:
                raise ValueError('only rigid triangles are supported')
            count = (document['accessors'][primitive['indices']]['count'] if 'indices' in primitive
                     else document['accessors'][primitive['attributes']['POSITION']]['count']) // 3
            key = ni, pi
            mask = masks[ei].setdefault(key, np.zeros(count, bool))
            occupied = selected.setdefault(key, np.zeros(count, bool))
            for lo, hi in part['triangle_ranges']:
                if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= count:
                    raise ValueError('invalid triangle range')
                if occupied[lo:hi].any():
                    raise ValueError('overlapping entity selections')
                mask[lo:hi] = occupied[lo:hi] = True
        if not any(mask.any() for mask in masks[ei].values()):
            raise ValueError('empty entity selection')

    def build(which):
        doc = copy.deepcopy(document)
        doc['meshes'] = []
        payload = bytearray(binary)
        if which is None:
            for node in doc['nodes']:
                node.pop('mesh', None)
        else:
            doc['nodes'] = [{'name': entities[which]['id'], 'children': []}]
            doc['scenes'] = [{'nodes': [0]}]
            doc['scene'] = 0
        for ni, world in worlds.items():
            node = document['nodes'][ni]
            if 'mesh' not in node:
                continue
            primitives = []
            for pi, source in enumerate(document['meshes'][node['mesh']]['primitives']):
                if source.get('mode', 4) != 4 or 'targets' in source:
                    raise ValueError('only rigid triangles are supported')
                indices = (accessor(document, binary, source['indices']) if 'indices' in source
                           else np.arange(document['accessors'][source['attributes']['POSITION']]['count']))
                triangles = indices.reshape(-1, 3)
                key = ni, pi
                mask = (~selected[key] if key in selected else np.ones(len(triangles), bool)) if which is None else masks[which].get(key, np.zeros(len(triangles), bool))
                if not mask.any():
                    continue
                kept = triangles[mask]
                used, remapped = np.unique(kept, return_inverse=True)
                p = copy.deepcopy(source)
                p['indices'] = append_accessor(doc, payload, remapped.astype('<u4').ravel(), 'SCALAR', 5125)
                for semantic, ai in source['attributes'].items():
                    a = document['accessors'][ai]
                    new = append_accessor(doc, payload, accessor(document, binary, ai)[used], a['type'], a['componentType'])
                    if a.get('normalized'):
                        doc['accessors'][new]['normalized'] = True
                    p['attributes'][semantic] = new
                primitives.append(p)
            if not primitives:
                continue
            mi = len(doc['meshes'])
            doc['meshes'].append({'name': node.get('name', ''), 'primitives': primitives})
            if which is None:
                doc['nodes'][ni]['mesh'] = mi
            else:
                local = world.copy()
                local[:3, 3] -= entities[which]['origin_m']
                doc['nodes'][0]['children'].append(len(doc['nodes']))
                doc['nodes'].append({'name': node.get('name', ''), 'mesh': mi,
                                     'matrix': local.flatten(order='F').tolist()})
        return doc, compact(doc, bytes(payload))
    result = [build(None)] + [build(i) for i in range(len(entities))]
    if sum(scene_triangles(d) for d, _ in result) != scene_triangles(document):
        raise ValueError('partition changed triangle count')
    return result


def run(package, rules, output):
    package, output = Path(package).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(package):
        raise ValueError('output must be a new directory outside the input package')
    if rules.get('schema_version') != 1 or not rules.get('evidence'):
        raise ValueError('schema_version 1 and selection evidence are required')
    manifest = json.loads((package / 'manifest.json').read_text())
    source_name = rules['asset']
    entry = manifest['assets'][source_name]
    if entry.get('semantics'):
        raise ValueError('extract before semantic binding; bound inputs are unsupported')
    entities = rules['entities']
    ids = [e['id'] for e in entities]
    if not ids or len(set(ids)) != len(ids) or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', s) or s in manifest['assets'] for s in ids):
        raise ValueError('entity IDs must be unique new asset names')
    results = {}
    for kind in ('visual', 'collision'):
        relative = Path(entry[kind])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('asset files must use package-relative paths')
        path = (package / relative).resolve()
        if not path.is_relative_to(package) or digest(path) != rules['inputs'][kind]['sha256'] or digest(path) != entry[kind + '_sha256']:
            raise ValueError(f'{kind} input checksum mismatch or unsafe path')
        selections = [dict(e, parts=e[kind]) for e in entities]
        results[kind] = partition(*read_glb(path), selections)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.entity-extraction-', dir=output.parent) as temp:
        stage = Path(temp) / 'package'
        shutil.copytree(package, stage)
        for entity in entities:
            new = {k: copy.deepcopy(entry[k]) for k in ('collision_method', 'mesh_simplification') if k in entry}
            new['placements_in_source_arena_frame'] = []
            origin = np.asarray(entity['origin_m'])
            for placement in entry['placements_in_source_arena_frame']:
                p = copy.deepcopy(placement)
                matrix = np.asarray(p['matrix_local_to_arena'], float)
                matrix[:3, 3] += matrix[:3, :3] @ origin
                p['translation_m'] = matrix[:3, 3].tolist()
                p['matrix_local_to_arena'] = matrix.tolist()
                p['entity_id'] = f"{source_name}-{p['instance']}-{entity['id']}"
                new['placements_in_source_arena_frame'].append(p)
            new['entity_partition'] = {'source_asset': source_name, 'origin_in_source_asset_m': entity['origin_m'],
                                       'physics': 'static', 'simplification_metadata_scope': 'parent before partition'}
            manifest['assets'][entity['id']] = new
            manifest.setdefault('static_assets', []).append(entity['id'])
        for kind, partitions in results.items():
            for i, (doc, binary) in enumerate(partitions):
                target = entry if i == 0 else manifest['assets'][ids[i - 1]]
                name = entry[kind] if i == 0 else ids[i - 1] + ('-collision' if kind == 'collision' else '') + '.glb'
                write_glb(stage / name, doc, binary)
                target[kind] = name
                target[kind + '_sha256'] = digest(stage / name)
                target['triangles' if kind == 'visual' else 'collision_triangles'] = scene_triangles(doc)
                target[kind + '_bytes'] = (stage / name).stat().st_size
        entry['entity_partition'] = {'entities': ids, 'simplification_metadata_scope': 'parent before partition'}
        manifest['entity_extraction'] = {'file': 'entity-extraction.json'}
        (stage / 'entity-extraction.json').write_text(json.dumps(rules, indent=2) + '\n')
        manifest['entity_extraction']['sha256'] = digest(stage / 'entity-extraction.json')
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        stage.rename(output)
    return {name: {k: manifest['assets'][name][k] for k in ('triangles', 'collision_triangles')} for name in [source_name] + ids}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--rules', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.package, json.loads(args.rules.read_text()), args.out), indent=2))


if __name__ == '__main__':
    main()
