# SPDX-License-Identifier: MIT OR Apache-2.0
"""Render source-connected Tech Core pieces for explicit manual review."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image, ImageDraw
from gltf_scene import read_glb, local_matrix


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


detail = module('detail', 'benchmarks/2026-10-23-detail-trial/run.py')
raster = module('raster', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
OUT = ROOT / 'out/rmuc2027-tech-core-review'


def data(g, colors=None):
    n = len(g)
    return (g, np.full((n, 3), .6) if colors is None else colors,
            np.zeros((n, 3, 2)), np.zeros(n, np.int32), np.zeros(n, np.int32), np.zeros((1, 1, 3), np.uint8))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    placement = json.loads((ROOT.parent / 'rm-simulator/field-2027/equipment/manifest.json').read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0]
    rotation = local_matrix({'rotation': placement['rotation_xyzw']})[:3, :3]
    frame = np.array([[1,0,0],[0,0,1],[0,-1,0]]) @ rotation
    records = []
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'
        subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for role in ('visual','collision'):
            source = ROOT / f'out/rmuc2027-detail-trial/aggressive-17mm/{role}-1mm' / ('tech-core' + ('-collision' if role == 'collision' else '') + '.glb')
            doc, blob = read_glb(source); rows, _ = detail.prepare(doc, blob)
            for row in rows:
                if len(row['g']) < 500: continue
                pieces = sorted(np.unique(row['labels']),key=lambda label:np.count_nonzero(row['labels']==label),reverse=True)[:18]
                canvas = Image.new('RGB',(1500,1800),'#191919'); draw = ImageDraw.Draw(canvas)
                for slot, label in enumerate(pieces):
                    g = row['g'][row['labels']==label]
                    rec = {'role':role,'node':row['node'],'piece':int(label),'triangles':len(g),'bounds_mm':[g.min((0,1)).tolist(),g.max((0,1)).tolist()]}
                    rec['images'] = []
                    for vi, view in enumerate([(1,.65,1),(-1,.65,-1)]):
                        image_path = OUT / f'{role}-{row["node"]}-{label}-{vi}.png'
                        image = raster(data(g @ frame.T),g @ frame.T,view,helper,tmp,image_path)
                        thumb = Image.fromarray(image).resize((245,245))
                        x=(slot%3)*500+vi*245; y=(slot//3)*300+35
                        canvas.paste(thumb,(x,y)); rec['images'].append(str(image_path))
                    draw.text(((slot%3)*500+8,(slot//3)*300+8),f'node {row["node"]} piece {label}: {len(g)} tris',fill='white')
                    records.append(rec)
                canvas.save(OUT/f'atlas-{role}-{row["node"]}.jpg')
    (OUT/'audit.json').write_text(json.dumps(records,indent=2)+'\n')


if __name__ == '__main__': main()
