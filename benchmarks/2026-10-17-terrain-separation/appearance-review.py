# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reproduce source appearance audit, complete compositions and matched views.

Run from rm-map-tools after inventory.py. Outputs are disposable; source CAD,
this script and rules/compositions-rmuc2027.json reproduce the review.
"""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'python'))
from cad_document import CadDocument
from cad_components import select_components, export_selection
from cad_composition import compile_compositions, product_occurrences, export_composition, verify_composition
from cad_partition import _validate_mesh_stats
from export_field_package import GlbWriter
from export_step_elements import shape_counts
from mesh_parts import tessellate
from p21split import Splitter
from validate_parts import read_part
import provenance

spec = importlib.util.spec_from_file_location('render_review', Path(__file__).with_name('render-review.py'))
render = importlib.util.module_from_spec(spec); spec.loader.exec_module(render)


def main():
    catalog = json.loads((REPO/'out/terrain-review/catalog.json').read_text())
    policy = json.loads((REPO/'rules/compositions-rmuc2027.json').read_text())
    recipes = compile_compositions(catalog, policy)
    out = REPO/'out/appearance-review-v2'; out.mkdir(exist_ok=True)
    names = {p['product_id']: p['name'] for p in catalog['assemblies']}
    definitions = {}
    with CadDocument.from_index(REPO/'out/terrain-review/source.npz', expected_sha256=policy['source_sha256']) as d:
        splitter = Splitter(d.index, d.model)
        style_types = Counter(d.index.tname(d.model.styled[s][0]) for s in d.model.styled)
        for product in sorted({c['product_id'] for c in catalog['components']}):
            name = names[product]; folder = out/'definitions'/name
            record_path = folder/'appearance.json'
            if record_path.exists():
                record = json.loads(record_path.read_text()); definitions[product] = {**record, 'glb': folder/'visual.glb'}
                continue
            export_selection(d, select_components(catalog, name), folder, splitter=splitter)
            native, reader, error = read_part(str(folder/'source.step'))
            if error: raise ValueError(error)
            native_solids, native_faces = shape_counts(native)
            stats = {}; points, triangles, ci, keys = tessellate(native, .4, .25, stats=stats)
            _validate_mesh_stats(stats)
            writer = GlbWriter(name, provenance.glb_asset('appearance-review.py', d.source_path, d.source_sha256))
            writer.add_node(name, points/1000, triangles, [keys[int(i)] for i in ci])
            writer.write(folder/'visual.glb')
            colors, levels = Counter(), Counter()
            for component in catalog['components']:
                if component['product_id'] != product: continue
                body = d.index.r(component['body_id'])
                for face, shell in d.model.body_faces_shells(body):
                    fc, sc, bc = d.model.surface_colour(face), d.model.surface_colour(shell) if shell >= 0 else None, d.model.surface_colour(body)
                    colors[fc or sc or bc or 'unstyled'] += 1
                    levels['face' if fc else 'shell' if sc else 'body' if bc else 'unstyled'] += 1
            record = {'product_id': product, 'name': name, 'native_faces': native_faces, 'native_solids': native_solids,
                      'triangles': len(triangles), 'triangle_colors': dict(Counter(keys[int(i)] or 'fallback' for i in ci)),
                      'source_face_colors': dict(colors), 'source_style_levels': dict(levels), 'tessellation_stats': stats}
            record_path.write_text(json.dumps(record, indent=2)+'\n')
            definitions[product] = {**record, 'glb': folder/'visual.glb'}
            print(name, len(triangles), 'triangles', dict(levels), flush=True)
            del native, reader, writer, points, triangles
        reports = []
        for recipe in recipes:
            target = out/'compositions'/recipe['name']
            if target.exists():
                report = json.loads((target/'composition.json').read_text())
                if report['occurrences'] != recipe['occurrences']:
                    raise ValueError('cached composition recipe changed; remove its generated output before rebuilding')
                report['step_glb_bounds_error_m'] = verify_composition(target, d.source_sha256)
            else: report = export_composition(d, recipe, definitions, target, splitter)
            reports.append(report)
            print('composition', recipe['name'], report['native_faces'], 'faces', flush=True)
        d.verify_source()
    views = out/'renders'; views.mkdir(exist_ok=True)
    compiler = shutil.which('clang++') or shutil.which('g++')
    with tempfile.TemporaryDirectory() as tmp:
        temporary = Path(tmp); raster = temporary/'raster'
        cpp = REPO/'benchmarks/2026-10-17-source-separation/scratch-source/cad-audit/non-base/depth-raster.cpp'
        source = cpp.read_text().replace('im(w*h*3,245);', 'im(w*h*3,245);for(int k=0;k<w*h;k++){im[k*3]=192;im[k*3+1]=208;im[k*3+2]=224;}')
        (temporary/'raster.cpp').write_text(source)
        subprocess.run([compiler, '-O3', str(temporary/'raster.cpp'), '-o', str(raster)], check=True)
        for recipe in recipes:
            render.rasterize(render.chunks(out/'compositions'/recipe['name']/'visual.glb'), views/(recipe['name']+'.png'), raster, temporary)
        # Native STEP has no texture/emission. These are source diffuse colors
        # with illustrative lighting, not an assertion about real materials.
        yup = np.array([[1.,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
        terrain, secondary, full = [], [], []
        excluded = {1354629,1751926,2603236,3749800,3998852,4056216,4774244}
        occurrence_report = []
        for occurrence in product_occurrences(catalog):
            product = occurrence['product_id']
            world = np.array(occurrence['source_world_matrix'], float); world[:3,3] /= 1000
            chunks = render.chunks(definitions[product]['glb'], yup@world)
            full.extend(chunks)
            if product in excluded: continue
            terrain.extend(chunks)
            if product in policy['secondary_product_ids']: secondary.extend(chunks)
            occurrence_report.append({'name': names[product], **occurrence})
        forward = np.array((1,1.2,1.4)); forward /= np.linalg.norm(forward)
        right = np.cross([0,1,0],forward); right /= np.linalg.norm(right)
        up = np.cross(forward,right); basis = np.column_stack((right,up,forward))
        projected = [p@basis for p,_ in terrain]
        framing = (np.min([p.min((0,1)) for p in projected],axis=0), np.max([p.max((0,1)) for p in projected],axis=0))
        keep = []
        for occurrence in product_occurrences(catalog):
            product = occurrence['product_id']
            if product in excluded or product in policy['secondary_product_ids']: continue
            world = np.array(occurrence['source_world_matrix'],float); world[:3,3] /= 1000
            keep.extend(render.chunks(definitions[product]['glb'],yup@world))
        counts = {}
        for name, chunks in [('terrain-all',terrain),('terrain-no-secondary',keep),('secondary-only',secondary),('full-field',full)]:
            counts[name] = render.rasterize(chunks, views/(name+'.png'), raster, temporary, view=(1,1.2,1.4), width=1600,height=1000,framing=None if name=='full-field' else framing)
            print('render',name,counts[name],flush=True)
        for product in [1751926,2650147,4070010,2717102,1754789,1800898]:
            # Reuse first exact occurrence rotation, remove world translation
            # and let orthographic framing center the standalone part.
            occurrence = next(o for o in product_occurrences(catalog) if o['product_id']==product)
            world=np.array(occurrence['source_world_matrix'],float); world[:3,3]=0
            render.rasterize(render.chunks(definitions[product]['glb'],yup@world),views/(names[product]+'.png'),raster,temporary,
                             view=(-1,.6,-1.4) if product==4070010 else (1,.6,1.4))
    report = {'source_sha256': policy['source_sha256'], 'style_target_types':dict(style_types),
              'secondary_selection':policy['secondary_scope'], 'secondary_product_ids':policy['secondary_product_ids'],
              'placed_triangles':counts,'occurrences':occurrence_report,'compositions':reports,
              'definitions':[{k:v for k,v in record.items() if k!='glb'} for record in definitions.values()]}
    (out/'review.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__': main()
