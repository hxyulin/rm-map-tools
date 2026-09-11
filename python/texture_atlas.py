# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bake explicitly selected planar GLB primitives into PNG atlases and a sidecar."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from gltf_scene import accessor, local_matrix, scene_nodes, read_glb, write_glb


def group_artwork(document, binary, selections, gap, tolerance, density, size):
    """Merge nearby coplanar sibling primitives in their shared parent frame.

    Sibling grouping preserves independently moving assembly boundaries. Material
    equality keeps alpha and sidedness intact. Groups are capped by tile size.
    """
    doc = copy.deepcopy(document)
    parents = {ni: parent for ni, _, parent in scene_nodes(doc)}
    items, selected = [], set()
    for selection in selections:
        matches = []
        for ni, node in enumerate(doc['nodes']):
            if ni not in parents or node.get('name') != selection['node'] or 'mesh' not in node:
                continue
            for pi, pr in enumerate(doc['meshes'][node['mesh']]['primitives']):
                if doc['materials'][pr['material']].get('name') == selection['material']:
                    matches.append((ni, pi, pr))
        if len(matches) != 1:
            raise ValueError(f'selection must match exactly once: {selection}')
        ni, pi, pr = matches[0]
        if (ni, pi) in selected:
            raise ValueError('duplicate texture selection')
        selected.add((ni, pi))
        if pr.get('mode', 4) != 4 or 'targets' in pr or 'skin' in doc['nodes'][ni]:
            raise ValueError('only rigid triangles can be baked')
        points = accessor(doc, binary, pr['attributes']['POSITION']).astype(float)
        triangles = (accessor(doc, binary, pr['indices']) if 'indices' in pr else np.arange(len(points))).reshape(-1, 3)
        matrix = local_matrix(doc['nodes'][ni])
        points = points @ matrix[:3, :3].T + matrix[:3, 3]
        if np.linalg.det(matrix[:3, :3]) < 0:
            triangles = triangles[:, [0, 2, 1]]
        used = points[np.unique(triangles)]
        _, basis = np.linalg.eigh((used-used.mean(0)).T @ (used-used.mean(0)))
        normal = basis[:, 0]
        if np.ptp(used @ normal) > tolerance:
            raise ValueError(f'selected artwork is not planar within {tolerance} m: {selection}')
        items.append(dict(ni=ni, pi=pi, points=points, triangles=triangles, used=used,
                          normal=normal, parent=parents[ni], material=pr['material'], source=selection))
    groups = []
    for item in items:
        groups.append([item])
    # Merge connected neighbours, testing the entire resulting patch each time.
    changed = True
    while changed:
        changed = False
        for i, group in enumerate(groups):
            a = group[0]
            normal = a['normal']
            axis = np.eye(3)[np.argmin(np.abs(normal))]
            u = axis - normal * (axis @ normal)
            u /= np.linalg.norm(u)
            v = np.cross(normal, u)
            for j in range(i+1, len(groups)):
                other = groups[j]
                b = other[0]
                if a['parent'] != b['parent'] or a['material'] != b['material']:
                    continue
                if any(abs(normal @ q['normal']) < 0.9999 for q in other):
                    continue
                points = np.vstack([q['used'] for q in group+other])
                if np.ptp(points @ normal) > tolerance:
                    continue
                projected = points @ np.column_stack((u, v))
                if np.any(np.ceil(np.ptp(projected, axis=0)*density)+5 > size):
                    continue
                nearby = False
                for left in group:
                    lp = left['used'] @ np.column_stack((u, v))
                    for right in other:
                        rp = right['used'] @ np.column_stack((u, v))
                        separation = np.maximum(0, np.maximum(lp.min(0)-rp.max(0), rp.min(0)-lp.max(0)))
                        if np.linalg.norm(separation) <= gap:
                            nearby = True
                            break
                    if nearby:
                        break
                if nearby:
                    groups[i] += groups.pop(j)
                    changed = True
                    break
            if changed:
                break
    # Replace the original selections with parent-local merged temporary meshes.
    for ni, node in enumerate(doc['nodes']):
        if 'mesh' not in node:
            continue
        mesh = copy.deepcopy(doc['meshes'][node['mesh']])
        mesh['primitives'] = [pr for pi, pr in enumerate(mesh['primitives']) if (ni, pi) not in selected]
        if mesh['primitives']:
            node['mesh'] = len(doc['meshes'])
            doc['meshes'].append(mesh)
        else:
            node.pop('mesh')
    packed = bytearray(binary)
    def append_array(array, kind, component):
        packed.extend(b'\0' * (-len(packed) % 4))
        doc['bufferViews'].append(dict(buffer=0, byteOffset=len(packed), byteLength=array.nbytes))
        packed.extend(array.tobytes())
        doc['accessors'].append(dict(bufferView=len(doc['bufferViews'])-1, componentType=component,
                                     count=len(array), type=kind))
        return len(doc['accessors'])-1
    new_selections, sources = [], {}
    existing_names = {node.get('name') for node in doc['nodes']}
    for i, group in enumerate(groups):
        name = f'artwork_patch_{i}'
        while name in existing_names:
            name += '_'
        existing_names.add(name)
        points = np.vstack([q['points'] for q in group]).astype('<f4')
        offsets = np.cumsum([0]+[len(q['points']) for q in group[:-1]])
        triangles = np.vstack([q['triangles']+offset for q, offset in zip(group, offsets)]).astype('<u4').reshape(-1)
        pa = append_array(points, 'VEC3', 5126)
        ta = append_array(triangles, 'SCALAR', 5125)
        doc['meshes'].append(dict(primitives=[dict(attributes={'POSITION':pa}, indices=ta, material=group[0]['material'])]))
        ni = len(doc['nodes'])
        doc['nodes'].append(dict(name=name, mesh=len(doc['meshes'])-1))
        parent = group[0]['parent']
        if parent is None:
            doc['scenes'][doc.get('scene', 0)]['nodes'].append(ni)
        else:
            doc['nodes'][parent].setdefault('children', []).append(ni)
        new_selections.append(dict(node=name, material=doc['materials'][group[0]['material']]['name']))
        sources[name] = [q['source'] for q in group]
    doc['buffers'][0]['byteLength'] = len(packed)
    return doc, bytes(packed), new_selections, sources


def bake(document, binary, selections, density=1024, size=2048, tolerance=0.006, merge_distance=0, normal_hint=None):
    """Selections use stable node/material names. Coordinates remain node-local."""
    if merge_distance > 0:
        grouped, packed, merged, sources = group_artwork(document, binary, selections,
                                                        merge_distance, tolerance, density, size)
        out, packed, pages, records = bake(grouped, packed, merged, density, size, tolerance, normal_hint=normal_hint)
        for record in records:
            record['sources'] = sources[record['node']]
        return out, packed, pages, records
    doc = copy.deepcopy(document)
    pages, records, selected = [], [], set()
    x = y = row_height = 0
    for selection in selections:
        matches = []
        for ni, node in enumerate(doc['nodes']):
            if node.get('name') != selection['node'] or 'mesh' not in node:
                continue
            for pi, pr in enumerate(doc['meshes'][node['mesh']]['primitives']):
                mat = doc['materials'][pr['material']]
                if mat.get('name') == selection['material']:
                    matches.append((ni, pi, pr, mat))
        if len(matches) != 1:
            raise ValueError(f'selection must match exactly once: {selection}')
        ni, pi, pr, mat = matches[0]
        if (ni, pi) in selected:
            raise ValueError('duplicate texture selection')
        selected.add((ni, pi))
        if pr.get('mode', 4) != 4 or 'targets' in pr or 'skin' in doc['nodes'][ni]:
            raise ValueError('only rigid triangles can be baked')
        pbr = mat.get('pbrMetallicRoughness', {})
        if any('Texture' in k for k in pbr) or any('Texture' in k for k in mat):
            raise ValueError('source textures are unsupported')
        points = accessor(doc, binary, pr['attributes']['POSITION']).astype(float)
        triangles = (accessor(doc, binary, pr['indices']) if 'indices' in pr else np.arange(len(points))).reshape(-1, 3)
        used = points[np.unique(triangles)]
        center = used.mean(0)
        _, basis = np.linalg.eigh((used-center).T @ (used-center))
        normal, u = basis[:, 0], basis[:, 2]
        face_normals = np.cross(points[triangles[:, 1]]-points[triangles[:, 0]],
                                points[triangles[:, 2]]-points[triangles[:, 0]])
        reference = face_normals[np.argmax(np.linalg.norm(face_normals, axis=1))]
        if normal @ reference < 0:
            normal = -normal
        if normal_hint is not None:
            hint = np.asarray(normal_hint, dtype=float)
            if hint.shape != (3,) or not np.isfinite(hint).all() or np.linalg.norm(hint) < 1e-12:
                raise ValueError('normal_hint must be a finite nonzero 3-vector')
            if normal @ hint < 0:
                normal = -normal
        # Use a projected coordinate axis so adjacent letters share orientation.
        axis = np.eye(3)[np.argmin(np.abs(normal))]
        u = axis-normal*(axis @ normal)
        u /= np.linalg.norm(u)
        v = np.cross(normal, u)
        uv = (points-center) @ np.column_stack((u, v))
        if np.ptp((used-center) @ normal) > tolerance:
            raise ValueError(f'selected artwork is not planar within {tolerance} m: {selection}')
        lo, hi = uv[np.unique(triangles)].min(0), uv[np.unique(triangles)].max(0)
        span = hi-lo
        if np.any(span <= 1e-9):
            raise ValueError('degenerate artwork')
        w, h = np.maximum(2, np.ceil(span*density).astype(int)+1)
        if w+4 > size or h+4 > size:
            raise ValueError(f'artwork exceeds atlas size; lower pixels_per_metre or increase atlas_size: {selection}')
        if x+w+4 > size:
            x, y, row_height = 0, y+row_height, 0
        if not pages or y+h+4 > size:
            pages.append(Image.new('RGBA', (size, size)))
            x = y = row_height = 0
        tile = Image.new('RGBA', (int(w)*4, int(h)*4))
        draw = ImageDraw.Draw(tile)
        linear = pbr.get('baseColorFactor', [1, 1, 1, 1])
        rgb = mat.get('extras', {}).get('step_colour_srgb')
        if rgb is None:
            rgb = [12.92*c if c <= 0.0031308 else 1.055*c**(1/2.4)-0.055 for c in linear[:3]]
        color = tuple(round(float(np.clip(c, 0, 1))*255) for c in [*rgb, linear[3]])
        pixels = (uv-lo)/span * [w-1, h-1]
        for tri in triangles:
            q = pixels[tri]*4+1.5
            a, b = q[1]-q[0], q[2]-q[0]
            if abs(a[0]*b[1]-a[1]*b[0]) > 1e-8:
                draw.polygon([tuple(p) for p in q], fill=color)
        tile = tile.resize((int(w), int(h)), Image.Resampling.LANCZOS)
        pages[-1].paste(tile, (int(x+2), int(y+2)))
        # Place the patch at the frontmost artwork depth, not inside its thickness.
        origin = center+u*lo[0]+v*lo[1]+normal*np.max((used-center) @ normal)
        records.append(dict(node=selection['node'], material=selection['material'],
                            page=len(pages)-1, rect_px=[int(x+2), int(y+2), int(w), int(h)],
                            uv_corners=[[float(a/size), float(b/size)] for a,b in
                                        [(x+2.5,y+2.5),(x+w+1.5,y+2.5),(x+w+1.5,y+h+1.5),(x+2.5,y+h+1.5)]],
                            corners_node_m=[p.tolist() for p in [origin,origin+u*span[0],origin+u*span[0]+v*span[1],origin+v*span[1]]],
                            source_triangles=len(triangles), double_sided=mat.get('doubleSided', False)))
        x += int(w)+4
        row_height = max(row_height, int(h)+4)
    # Clone meshes per node so shared meshes retain their other occurrences.
    meshes = []
    for ni, node in enumerate(doc['nodes']):
        if 'mesh' not in node:
            continue
        mesh = copy.deepcopy(doc['meshes'][node['mesh']])
        mesh['primitives'] = [pr for pi, pr in enumerate(mesh['primitives']) if (ni, pi) not in selected]
        if mesh['primitives']:
            node['mesh'] = len(meshes)
            meshes.append(mesh)
        else:
            node.pop('mesh')
    doc['meshes'] = meshes
    # Repack referenced geometry, removing the baked geometry from the binary.
    if doc.get('animations') or doc.get('skins') or doc.get('images') or doc.get('extensionsUsed'):
        raise ValueError('atlas export currently requires untextured static GLBs without extensions')
    ids = set()
    for mesh in meshes:
        for pr in mesh['primitives']:
            ids.update(pr['attributes'].values())
            if 'indices' in pr:
                ids.add(pr['indices'])
    mapping, accessors, views, packed = {}, [], [], bytearray()
    for old in sorted(ids):
        arr = np.ascontiguousarray(accessor(doc, binary, old))
        packed.extend(b'\0' * (-len(packed) % 4))
        views.append(dict(buffer=0, byteOffset=len(packed), byteLength=arr.nbytes))
        packed.extend(arr.tobytes())
        a = copy.deepcopy(doc['accessors'][old])
        a.pop('byteOffset', None)
        a['bufferView'] = len(views)-1
        mapping[old] = len(accessors)
        accessors.append(a)
    for mesh in meshes:
        for pr in mesh['primitives']:
            pr['attributes'] = {k:mapping[v] for k,v in pr['attributes'].items()}
            if 'indices' in pr:
                pr['indices'] = mapping[pr['indices']]
    doc.update(accessors=accessors, bufferViews=views)
    if packed:
        doc['buffers'] = [dict(byteLength=len(packed))]
    else:
        doc.pop('buffers', None)
    return doc, bytes(packed), pages, records


def export_atlas(package, rules_path):
    """Apply to a newly generated package, before it is published."""
    root = Path(package)
    config = json.loads(Path(rules_path).read_text())
    if config.get('schema_version') != 1 or not config.get('files'):
        raise ValueError('atlas rules require schema_version 1 and nonempty files')
    density, size = config.get('pixels_per_metre', 1024), config.get('atlas_size', 2048)
    tolerance = config.get('planarity_tolerance_m', 0.006)
    merge_distance = config.get('merge_distance_m', 0.15)
    if not np.isfinite(merge_distance) or merge_distance < 0:
        raise ValueError('merge_distance_m must be finite and nonnegative')
    if not isinstance(size, int) or not 16 <= size <= 8192 or not np.isfinite(density) or density <= 0 or not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError('invalid atlas resolution or planarity tolerance')
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if 'texture_atlas' in manifest:
        raise ValueError('package already has a texture atlas')
    visual_files = {e.get('visual') for e in manifest['assets'].values()}
    visual_files.update({'full-map.glb'})
    mode = config.get('render_mode', 'sidecar')
    if mode not in ('sidecar', 'embedded'):
        raise ValueError('render_mode must be sidecar or embedded')
    simplify = config.get('simplify', {})
    if not isinstance(simplify, dict) or set(simplify)-set(config['files']):
        raise ValueError('simplify must select atlas files')
    for entry in manifest['assets'].values():
        if entry.get('visual') in simplify and entry.get('mesh_simplification', {}).get('visual'):
            raise ValueError('use unsimplified source geometry for backing simplification')
    prepared = []
    for filename, selections in config['files'].items():
        if filename not in visual_files:
            raise ValueError('atlas selection must target a manifest visual or full-map.glb')
        path = (root/filename).resolve()
        if not path.is_relative_to(root.resolve()) or path.suffix != '.glb' or not selections:
            raise ValueError('atlas files must be GLBs inside the output package with nonempty selections')
        input_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        for entry in manifest['assets'].values():
            if entry.get('visual') == filename and entry.get('visual_sha256', input_hash) != input_hash:
                raise ValueError('visual input checksum mismatch')
        doc, binary = read_glb(path)
        prepared.append((filename, path, bake(doc, binary, selections, density, size, tolerance, merge_distance, config.get('normal_hint'))))
    sidecar = dict(schema_version=1, units='metres', coordinates='node local; apply the original node hierarchy then asset placement',
                   uv_origin='top left; corners correspond to corners_node_m', alpha='straight', collision='unchanged', files={})
    for fi, (filename, path, (doc, binary, pages, records)) in enumerate(prepared):
        names = []
        for pi, page in enumerate(pages):
            name = f'artwork-atlas-{fi}-{pi}.png'
            page.save(root/name)
            names.append(dict(file=name, sha256=hashlib.sha256((root/name).read_bytes()).hexdigest()))
        write_glb(path, doc, binary)
        sidecar['files'][filename] = dict(pages=names, patches=records)
        if filename in simplify:
            from simplify_package import simplify_glb
            settings = dict(simplify[filename])
            planar = settings.pop('preserve_planar_m', None)
            if planar is not None:
                if not np.isfinite(planar) or planar < 0:
                    raise ValueError('preserve_planar_m must be finite and nonnegative')
                from gltf_scene import mesh_instances
                preserve = list(settings.get('preserve', []))
                for ni, pi, points, _, _ in mesh_instances(doc, binary):
                    centered = points-points.mean(0)
                    _, basis = np.linalg.eigh(centered.T @ centered)
                    if np.ptp(centered @ basis[:,0]) <= planar:
                        preserve.append(dict(node=doc['nodes'][ni]['name'], primitive=pi))
                settings['preserve'] = preserve
            sidecar['files'][filename]['backing_simplification'] = simplify_glb(root/filename, **settings)
    sidepath = root/'texture-atlas.json'
    sidepath.write_text(json.dumps(sidecar, indent=2)+'\n')
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest['assets'].values():
        filename = entry.get('visual')
        if filename in sidecar['files']:
            entry['visual_sha256'] = hashlib.sha256((root/filename).read_bytes()).hexdigest()
            entry['visual_bytes'] = (root/filename).stat().st_size
            report = sidecar['files'][filename].get('backing_simplification')
            if report:
                entry.setdefault('mesh_simplification', {})['visual'] = {k:v for k,v in report.items() if k != 'primitives'}
            doc, _ = read_glb(root/filename)
            entry['triangles'] = sum(doc['accessors'][pr['indices']]['count']//3 for mesh in doc['meshes'] for pr in mesh['primitives'])
    if manifest.get('articulation'):
        from simplify_package import check_bindings
        art = manifest['articulation']
        artpath = root/art['file']
        if hashlib.sha256(artpath.read_bytes()).hexdigest() != art['sha256']:
            raise ValueError('articulation checksum mismatch')
        bindings = json.loads(artpath.read_text())
        for name, entry in manifest['assets'].items():
            binding = bindings['assets'].get(name, {}).get('files', {}).get('visual')
            if binding and entry.get('visual') in sidecar['files']:
                doc, _ = read_glb(root/entry['visual'])
                check_bindings(doc, binding)
                binding['sha256'] = entry['visual_sha256']
        artpath.write_text(json.dumps(bindings,indent=2)+'\n')
        art['sha256'] = hashlib.sha256(artpath.read_bytes()).hexdigest()
    manifest['texture_atlas'] = dict(sidecar=sidepath.name, sha256=hashlib.sha256(sidepath.read_bytes()).hexdigest())
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    collision = config.get('collision_simplify', {})
    if not isinstance(collision, dict) or set(collision)-set(config['files']):
        raise ValueError('collision_simplify must select atlas files')
    for filename, settings in collision.items():
        from collision_artwork import export_collision_artwork
        export_collision_artwork(root, filename, config['files'][filename], settings)
    if mode == 'embedded':
        from attach_texture_atlas import attach_package
        attach_package(root, config.get('offset_m', 0.0005))
    return json.loads(sidepath.read_text())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('rules', type=Path)
    args = parser.parse_args()
    export_atlas(args.package, args.rules)
