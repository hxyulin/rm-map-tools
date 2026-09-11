# SPDX-License-Identifier: MIT OR Apache-2.0
"""Remove explicitly selected artwork from collider meshes before simplification."""
import copy
import json
from pathlib import Path

import numpy as np
from gltf_scene import mesh_instances, read_glb, write_glb
from simplify_package import check_bindings, compact, digest, scene_triangles, simplify_glb


def strip(document, binary, selections, tolerance_m=0.006):
    """Match node/material names independently of visual primitive indices."""
    if not selections or not np.isfinite(tolerance_m) or tolerance_m < 0:
        raise ValueError('expected nonempty selections and a finite nonnegative tolerance')
    doc = copy.deepcopy(document)
    lookup = {}
    for ni, pi, points, triangles, material in mesh_instances(doc, binary):
        name = doc['materials'][material].get('name') if material is not None else None
        key = (doc['nodes'][ni].get('name'), name)
        lookup.setdefault(key, []).append((ni,pi,points,triangles))
    selected, removed = set(), []
    for selection in selections:
        key = (selection['node'],selection['material'])
        matches = lookup.get(key, [])
        if len(matches) != 1:
            raise ValueError(f'collision artwork must match exactly once: {key}')
        ni,pi,points,triangles = matches[0]
        if (ni,pi) in selected:
            raise ValueError('duplicate collision artwork selection')
        centered = points-points.mean(0)
        _,basis = np.linalg.eigh(centered.T @ centered)
        thickness = float(np.ptp(centered @ basis[:,0]))
        if not np.isfinite(thickness) or thickness > tolerance_m:
            raise ValueError(f'collision artwork is not planar within tolerance: {key}')
        selected.add((ni,pi))
        removed.append(dict(**selection, primitive=pi, triangles=len(triangles), thickness_m=thickness))
    for ni,node in enumerate(doc['nodes']):
        if 'mesh' not in node:
            continue
        mesh = copy.deepcopy(doc['meshes'][node['mesh']])
        mesh['primitives'] = [p for pi,p in enumerate(mesh['primitives']) if (ni,pi) not in selected]
        if mesh['primitives']:
            node['mesh'] = len(doc['meshes'])
            doc['meshes'].append(mesh)
        else:
            node.pop('mesh')
    return doc, compact(doc,binary), removed


def export_collision_artwork(package, visual_file, selections, settings=None):
    """Modify a newly exported package; input collider must be unsimplified."""
    root = Path(package).resolve()
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    matches = [(n,e) for n,e in manifest['assets'].items() if e.get('visual') == visual_file]
    if len(matches) != 1:
        raise ValueError('expected one asset for collision artwork extraction')
    name,entry = matches[0]
    if entry.get('mesh_simplification', {}).get('collision'):
        raise ValueError('restore the unsimplified source collider before stripping artwork')
    path = (root/entry['collision']).resolve()
    if not path.is_relative_to(root) or entry['collision'] == entry['visual']:
        raise ValueError('expected separate collider inside package')
    before_hash = digest(path)
    if before_hash != entry['collision_sha256']:
        raise ValueError('collision input checksum mismatch')
    doc,binary = read_glb(path)
    before = scene_triangles(doc)
    doc,binary,removed = strip(doc,binary,selections)
    art = manifest.get('articulation')
    binding = None
    if art:
        artpath = root/art['file']
        if not artpath.resolve().is_relative_to(root) or digest(artpath) != art['sha256']:
            raise ValueError('articulation checksum mismatch')
        sidecar = json.loads(artpath.read_text())
        binding = sidecar['assets'].get(name, {}).get('files', {}).get('collision')
        if binding:
            if binding['sha256'] != before_hash:
                raise ValueError('collision semantic checksum mismatch')
            check_bindings(doc,binding)
    write_glb(path,doc,binary)
    report = dict(input_sha256=before_hash,before_triangles=before,removed=removed,
                  removed_triangles=sum(r['triangles'] for r in removed))
    if settings is not None:
        report['simplification'] = simplify_glb(path,binding=binding,**settings)
        entry.setdefault('mesh_simplification', {})['collision'] = {
            k:v for k,v in report['simplification'].items() if k != 'primitives'}
        entry['collision_method'] = report['simplification']['method']
    doc,_ = read_glb(path)
    entry['collision_triangles'] = scene_triangles(doc)
    entry['collision_bytes'] = path.stat().st_size
    entry['collision_sha256'] = digest(path)
    report['after_triangles'] = entry['collision_triangles']
    entry['collision_artwork_removed'] = report
    if binding:
        binding['sha256'] = entry['collision_sha256']
        artpath.write_text(json.dumps(sidecar,indent=2)+'\n')
        art['sha256'] = digest(artpath)
    if manifest.get('texture_atlas'):
        descriptor = manifest['texture_atlas']
        atlaspath = root/descriptor['sidecar']
        if not atlaspath.resolve().is_relative_to(root) or digest(atlaspath) != descriptor['sha256']:
            raise ValueError('atlas sidecar checksum mismatch')
        atlas = json.loads(atlaspath.read_text())
        atlas['collision'] = 'Selected artwork removed; see asset collision_artwork_removed in manifest.'
        atlaspath.write_text(json.dumps(atlas,indent=2)+'\n')
        descriptor['sha256'] = digest(atlaspath)
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    return report
