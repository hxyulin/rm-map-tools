# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render a CAD partition bundle, contact sheets and its original placed subset.

Run from rm-map-tools with --bundle, --catalog and --out. The existing diagnostic
C++ rasterizer supplies per-pixel depth testing; no mesh simplification occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'python'))
from gltf_scene import read_glb, mesh_instances


def chunks(path, placement=None):
    document, binary = read_glb(path)
    result = []
    for _, _, points, triangles, material in mesh_instances(document, binary, apply_transforms=placement is None):
        if placement is not None:
            points = points @ placement[:3, :3].T + placement[:3, 3]
        rgb = np.array(document['materials'][material]['pbrMetallicRoughness']['baseColorFactor'][:3])
        rgb = np.where(rgb <= .0031308, rgb*12.92, 1.055*rgb**(1/2.4)-.055)
        result.append((points[triangles], rgb))
    return result


def rasterize(meshes, target, raster, temporary, view=(1, .6, 1.4), width=1000, height=800, framing=None):
    triangles = np.concatenate([p for p, _ in meshes])
    rgb = np.concatenate([np.broadcast_to(c, (len(p), 3)) for p, c in meshes])
    forward = np.array(view, float); forward /= np.linalg.norm(forward)
    right = np.cross([0, 1, 0], forward); right /= np.linalg.norm(right)
    up = np.cross(forward, right)
    projected = triangles @ np.column_stack((right, up, forward))
    low, high = framing if framing is not None else (projected.min((0, 1)), projected.max((0, 1)))
    projected -= (low+high)/2
    factor = min((width*2-100)/max(high[0]-low[0], 1e-9),
                 (height*2-100)/max(high[1]-low[1], 1e-9))
    projected[:, :, 0] = projected[:, :, 0]*factor+width
    projected[:, :, 1] = -projected[:, :, 1]*factor+height
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-20)
    light = forward+.8*up-.3*right; light /= np.linalg.norm(light)
    colors = np.clip(rgb*(.55+.45*np.abs(normals@light))[:, None]*255, 0, 255).astype('uint8')
    records = np.empty(len(triangles), dtype=[('p', '<f4', (3, 3)), ('c', 'u1', (3,))])
    records['p'], records['c'] = projected, colors
    source, image = temporary/'input.bin', temporary/'output.ppm'
    with source.open('wb') as stream:
        stream.write(struct.pack('<iii', width*2, height*2, len(triangles)))
        stream.write(records.tobytes())
    subprocess.run([str(raster), str(source), str(image)], check=True)
    with Image.open(image) as full:
        full.resize((width, height), Image.Resampling.LANCZOS).save(target)
    return len(triangles)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.bundle/'manifest.json').read_text())
    catalog = json.loads(args.catalog.read_text())
    if manifest['source_sha256'] != catalog['source_sha256']:
        raise ValueError('bundle/catalog source mismatch')
    for relative, expected in manifest['files_sha256'].items():
        with (args.bundle/relative).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError(f'bundle checksum mismatch: {relative}')
    args.out.mkdir(parents=True, exist_ok=False)
    report, placed, identities = [], [], set()
    compiler = shutil.which('clang++') or shutil.which('g++')
    if compiler is None:
        raise RuntimeError('a C++ compiler is required for the diagnostic rasterizer')
    with tempfile.TemporaryDirectory() as tmp:
        temporary = Path(tmp); raster = temporary/'depth-raster'
        cpp = REPO/'benchmarks/2026-10-17-source-separation/scratch-source/cad-audit/non-base/depth-raster.cpp'
        # Blue-grey backdrop keeps white source marking plates visible.
        source = cpp.read_text()
        background = 'im(w*h*3,245);'
        if source.count(background) != 1:
            raise ValueError('unexpected diagnostic rasterizer source')
        source = source.replace(background, 'im(w*h*3,245);for(int k=0;k<w*h;k++){im[k*3]=192;im[k*3+1]=208;im[k*3+2]=224;}')
        working_cpp = temporary/'raster.cpp'; working_cpp.write_text(source)
        subprocess.run([compiler, '-O3', str(working_cpp), '-o', str(raster)], check=True)
        for product in manifest['products']:
            name = product['name']; directory = args.bundle/name
            full_image = args.out/(name+'.png')
            rasterize(chunks(directory/'full/visual.glb'), full_image, raster, temporary)
            parts = []
            for group in product['groups']:
                part = directory/group['directory']/'visual.glb'
                key = group['id'].split('/', 1)[1]
                image = full_image if len(product['groups']) == 1 else args.out/(name+'--'+key+'.png')
                if len(product['groups']) != 1:
                    rasterize(chunks(part), image, raster, temporary)
                parts.append({'id': key, 'image': image.name, 'faces': group['face_count']})
                bodies = set(group['solid_body_ids']) | {int(b) for b in group['shell_ids_by_body']}
                selected = {f'p{product["product_id"]}.b{b}' for b in bodies}
                for occurrence in catalog['occurrences']:
                    if occurrence['component_id'] not in selected:
                        continue
                    identity = (group['id'], occurrence['root_product_id'], tuple(occurrence['occurrence_path']))
                    if identity in identities:
                        raise ValueError('duplicate placed work unit')
                    identities.add(identity)
                    world = np.array(occurrence['source_world_matrix']); world[:3, 3] /= 1000
                    to_yup = np.array([[1.,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
                    placed.extend(chunks(part, to_yup@world))
            sheet_name = None
            if len(parts) > 1:
                columns = min(5, len(parts)); rows = (len(parts)+columns-1)//columns
                sheet = Image.new('RGB', (columns*260, rows*235), '#c0d0e0')
                draw = ImageDraw.Draw(sheet)
                for i, part in enumerate(parts):
                    with Image.open(args.out/part['image']) as image:
                        sheet.paste(image.resize((250, 200), Image.Resampling.LANCZOS), ((i%columns)*260+5, (i//columns)*235))
                    draw.text(((i%columns)*260+8, (i//columns)*235+204), part['id'], fill='#182334')
                sheet_name = name+'--parts.png'; sheet.save(args.out/sheet_name)
            report.append({'name': name, 'image': full_image.name, 'contact_sheet': sheet_name,
                           'groups': parts, 'source_faces': product['source_face_count']})
            print(name, len(parts), 'pieces', flush=True)
        placed_triangles = rasterize(placed, args.out/'overview.png', raster, temporary,
                                    view=(1, 1.2, 1.4), width=1600, height=1000)
    result = {'source_sha256': manifest['source_sha256'], 'products': report,
              'definition_pieces': sum(len(p['groups']) for p in manifest['products']),
              'placed_pieces': len(identities), 'placed_triangles': placed_triangles,
              'render': 'Per-pixel orthographic depth; 2x supersampling; source colors, illustrative shading.'}
    (args.out/'review.json').write_text(json.dumps(result, indent=2)+'\n')
    print('placed pieces', len(identities), 'triangles', placed_triangles, flush=True)


if __name__ == '__main__':
    main()
