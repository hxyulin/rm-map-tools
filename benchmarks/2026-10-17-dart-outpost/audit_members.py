#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Inspect expensive source-owned Dart and Outpost members before fitting."""
import importlib.util
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image, ImageDraw

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

audit = module('audit', ROOT / 'benchmarks/2026-10-17-collision-solids/audit.py')
TARGETS = {'dart-station/deck-and-shared-hardware': [302,39], 'outpost/rotor/module-0': [3,6], 'outpost/fixed/lower-cluster': [1,10], 'outpost/fixed/column-cluster': [1], 'outpost/fixed/upper-cluster': [1]}
if __name__ == '__main__':
    out = ROOT / 'out/rmuc2027-dart-outpost'; out.mkdir(parents=True, exist_ok=True)
    audit.TARGETS = TARGETS
    sys.argv = [sys.argv[0], '--out', str(out)]; audit.main()
    raster = module('raster', ROOT / 'benchmarks/2026-10-17-base-passes/validate_render.py').raster
    cells = []
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'; subprocess.run([shutil.which('clang++'), '-O3', str(ROOT / 'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'), '-o', str(helper)], check=True)
        for cid, units in TARGETS.items():
            data = np.load(ROOT / 'out/rmuc2027-composed-pipeline' / cid / 'candidate.npz'); p,t,m,u = [data[k] for k in ['positions_mm','triangles','material_ids','unit_ids']]; palette = [[float(x) for x in v.split(',')] if v else [.6275]*3 for v in data['palette']]
            for unit in units:
                mask = u == unit; g = p[t[mask]] @ np.array([[1,0,0],[0,0,1],[0,-1,0]]).T / 1000; c = np.array(palette)[m[mask]]
                sheet = Image.new('RGB', (900,330)); draw = ImageDraw.Draw(sheet); draw.text((8,8), cid+' member '+str(unit)+' '+str(len(g))+' triangles',fill='white')
                for j,view in enumerate([(1,.7,1.5),(-1,.7,-1.5),(0,1,.000001)]):
                    frame = raster(g,c,g,view,helper,tmp,tmp/'frame.png'); sheet.paste(Image.fromarray(frame).resize((300,300)),(300*j,30))
                cells.append(sheet)
        sheet = Image.new('RGB',(900,330*len(cells)))
        for i,cell in enumerate(cells):sheet.paste(cell,(0,330*i))
        sheet.save(out/'inspection.png')
