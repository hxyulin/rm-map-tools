#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Attach baked artwork as native textured GLB primitives after simplification."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from gltf_scene import read_glb, write_glb


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attach(document, binary, pages, patches, offset_m=0.0005):
    """PNG bytes and sidecar patches become embedded images and node-local quads."""
    if not np.isfinite(offset_m) or not 0 <= offset_m <= 0.02:
        raise ValueError('patch offset must be between 0 and 0.02 metres')
    doc = copy.deepcopy(document)
    if doc.get('extras', {}).get('artwork_embedded'):
        raise ValueError('artwork is already embedded')
    packed = bytearray(binary)
    def view(data, target=None):
        packed.extend(b'\0' * (-len(packed) % 4))
        record = dict(buffer=0, byteOffset=len(packed), byteLength=len(data))
        if target is not None:
            record['target'] = target
        doc.setdefault('bufferViews', []).append(record)
        packed.extend(data)
        return len(doc['bufferViews'])-1
    def array(values, kind, component, target):
        a = dict(bufferView=view(values.tobytes(), target), componentType=component,
                 count=len(values), type=kind)
        if kind == 'VEC3':
            a.update(min=values.min(0).tolist(), max=values.max(0).tolist())
        doc.setdefault('accessors', []).append(a)
        return len(doc['accessors'])-1
    sampler = len(doc.setdefault('samplers', []))
    # No mipmaps: tightly packed transparent atlas gutters are only two pixels.
    doc['samplers'].append(dict(magFilter=9729, minFilter=9729, wrapS=33071, wrapT=33071))
    textures = []
    for page in pages:
        if not page.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('atlas pages must be PNG images')
        image = len(doc.setdefault('images', []))
        doc['images'].append(dict(bufferView=view(page), mimeType='image/png'))
        textures.append(len(doc.setdefault('textures', [])))
        doc['textures'].append(dict(source=image, sampler=sampler))
    materials = {}
    for patch in patches:
        matches = [n for n in doc['nodes'] if n.get('name') == patch['node']]
        if len(matches) != 1:
            raise ValueError('patch anchor must match exactly once')
        node = matches[0]
        key = (patch['page'], bool(patch['double_sided']))
        if key not in materials:
            materials[key] = len(doc.setdefault('materials', []))
            doc['materials'].append(dict(name=f'artwork_atlas_{key[0]}_{int(key[1])}',
                pbrMetallicRoughness=dict(baseColorFactor=[1,1,1,1],
                    baseColorTexture=dict(index=textures[key[0]], texCoord=0),
                    metallicFactor=0, roughnessFactor=0.8),
                alphaMode='MASK', alphaCutoff=0.5, doubleSided=key[1]))
        corners = np.asarray(patch['corners_node_m'], dtype=float)
        uv = np.asarray(patch['uv_corners'], dtype='<f4')
        if corners.shape != (4,3) or uv.shape != (4,2) or not np.isfinite(corners).all() or not np.isfinite(uv).all():
            raise ValueError('invalid patch quad')
        normal = np.cross(corners[1]-corners[0], corners[3]-corners[0])
        length = np.linalg.norm(normal)
        if length <= 1e-12:
            raise ValueError('degenerate patch quad')
        normal /= length
        positions = np.asarray(corners+normal*offset_m, dtype='<f4')
        normals = np.tile(normal, (4,1)).astype('<f4')
        indices = np.array([0,1,2,0,2,3], dtype='<u4')
        primitive = dict(attributes=dict(POSITION=array(positions,'VEC3',5126,34962),
            NORMAL=array(normals,'VEC3',5126,34962), TEXCOORD_0=array(uv,'VEC2',5126,34962)),
            indices=array(indices,'SCALAR',5125,34963), material=materials[key], mode=4,
            extras={'rm': {'layer':'markings'}, 'artwork_sources':patch.get('sources', [])})
        mesh = copy.deepcopy(doc['meshes'][node['mesh']]) if 'mesh' in node else dict(primitives=[])
        mesh['primitives'].append(primitive)
        node['mesh'] = len(doc.setdefault('meshes', []))
        doc['meshes'].append(mesh)
    used = sorted({node['mesh'] for node in doc['nodes'] if 'mesh' in node})
    remap = {old:new for new,old in enumerate(used)}
    doc['meshes'] = [doc['meshes'][i] for i in used]
    for node in doc['nodes']:
        if 'mesh' in node:
            node['mesh'] = remap[node['mesh']]
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            for index in primitive['attributes'].values():
                doc['bufferViews'][doc['accessors'][index]['bufferView']]['target'] = 34962
            if 'indices' in primitive:
                doc['bufferViews'][doc['accessors'][primitive['indices']]['bufferView']]['target'] = 34963
    doc['buffers'] = [dict(byteLength=len(packed))]
    doc.setdefault('extras', {})['artwork_embedded'] = dict(patches=len(patches), offset_m=offset_m)
    return doc, bytes(packed)


def attach_package(package, offset_m=0.0005):
    """Finalize a new package. Call after backing mesh simplification."""
    root = Path(package).resolve()
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    descriptor = manifest['texture_atlas']
    if descriptor.get('embedded'):
        raise ValueError('package artwork already embedded')
    def local(name):
        p = (root/name).resolve()
        if not p.is_relative_to(root):
            raise ValueError('atlas path escapes package')
        return p
    sidepath = local(descriptor['sidecar'])
    if digest(sidepath) != descriptor['sha256']:
        raise ValueError('atlas sidecar checksum mismatch')
    sidecar = json.loads(sidepath.read_text())
    bindings = None
    if manifest.get('articulation'):
        art = manifest['articulation']
        artpath = local(art['file'])
        if digest(artpath) != art['sha256']:
            raise ValueError('articulation checksum mismatch')
        bindings = json.loads(artpath.read_text())
    prepared = []
    for filename, entry in sidecar['files'].items():
        pages = []
        for page in entry['pages']:
            p = local(page['file'])
            if digest(p) != page['sha256']:
                raise ValueError('atlas PNG checksum mismatch')
            pages.append(p.read_bytes())
        path = local(filename)
        matching = [a for a in manifest['assets'].values() if a.get('visual') == filename]
        if not matching or any(digest(path) != a['visual_sha256'] for a in matching):
            raise ValueError('visual GLB manifest checksum mismatch')
        doc, binary = read_glb(path)
        prepared.append((path, *attach(doc,binary,pages,entry['patches'],offset_m)))
    for path, doc, binary in prepared:
        write_glb(path, doc, binary)
    for entry in manifest['assets'].values():
        if entry.get('visual') in sidecar['files']:
            entry['visual_sha256'] = digest(local(entry['visual']))
            entry['visual_bytes'] = local(entry['visual']).stat().st_size
            entry['triangles'] += 2*len(sidecar['files'][entry['visual']]['patches'])
    # Original semantic anchors remain intact; refresh the file pins.
    if manifest.get('articulation'):
        art = manifest['articulation']
        path = local(art['file'])
        for name, entry in manifest['assets'].items():
            binding = bindings['assets'].get(name, {}).get('files', {}).get('visual')
            if binding and entry.get('visual') in sidecar['files']:
                binding['sha256'] = entry['visual_sha256']
        path.write_text(json.dumps(bindings,indent=2)+'\n')
        art['sha256'] = digest(path)
    descriptor.update(embedded=True, render_sidecar_required=False, offset_m=offset_m)
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--offset-m', type=float, default=0.0005)
    args = parser.parse_args()
    attach_package(args.package, args.offset_m)
