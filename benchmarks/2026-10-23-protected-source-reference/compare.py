#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Measure current installed visuals against independent unsimplified references.

Finite deterministic samples establish witnessed differences only; not an upper
error bound or a visibility/appearance judgment. Reference coordinates are mm.
"""
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,mesh_instances
from mesh_quality import sample_points,distances
from plan_cad_lods import digest
OUT=ROOT/'out/rmuc2027-protected-source-reference'


def main():
    ledger=json.loads((OUT/'ledger.json').read_bytes());results=[]
    for r in ledger['references']:
        source=ROOT/r['reference_glb'];assert digest(source)==r['reference_glb_sha256']
        runtime=ROOT.parent/r['runtime']['file'];assert digest(runtime)==r['runtime']['sha256']
        d,b=read_glb(runtime);selected={n['index'] for n in r['runtime']['mesh_nodes']}
        positions=[];triangles=[];offset=0;colors=[];textured=0
        for index,pi,p,t,mat in mesh_instances(d,b):
            if index not in selected:continue
            positions.append(p*1000);triangles.append(t+offset);offset+=len(p)
            material=d['materials'][mat];rgb=material.get('extras',{}).get('step_colour_srgb')
            key=','.join(f'{x:.4f}' for x in rgb) if rgb is not None else None
            colors.extend([key]*len(t))
            if 'baseColorTexture' in material.get('pbrMetallicRoughness',{}):textured+=len(t)
        p=np.concatenate(positions);t=np.concatenate(triangles)
        original=np.load(source.with_suffix('.npz'));sp=original['positions_mm'];st=original['triangles'];palette=original['palette'].tolist();sc=np.array([palette[int(k)] or None for k in original['material_ids']],object);colors=np.array(colors,object)
        samples=sample_points(sp,st,8192);forward=distances(samples,p,t);reverse=distances(sample_points(p,t,8192),sp,st)
        colorchecks=[]
        for color in dict.fromkeys(sc.tolist()):
            src=st[sc==color];target=t[colors==color]
            if color is None:continue
            values=distances(sample_points(sp,src,2048),p,target)
            colorchecks.append({'source_srgb_key':color,'reference_triangles':len(src),'runtime_triangles':len(target),'source_to_same_color_max_mm':float(values.max()) if len(target) else None,'no_matching_source_color_material':not len(target)})
        worst=int(np.argmax(forward))
        row={'id':r['id'],'reference_triangles':len(st),'runtime_triangles':len(t),'source_to_runtime_samples':len(samples),'source_to_runtime_max_mm':float(forward.max()),'source_to_runtime_p99_mm':float(np.percentile(forward,99)),'runtime_to_source_max_mm':float(reverse.max()),'runtime_to_source_p99_mm':float(np.percentile(reverse,99)),'worst_source_sample_local_mm':samples[worst].tolist(),'source_samples_over_1mm':int((forward>1).sum()),'source_samples_over_0_1mm':int((forward>.1).sum()),'color_checks':colorchecks,'runtime_textured_triangles':textured}
        results.append(row);print(r['id'],len(st),'->',len(t),'max mm',row['source_to_runtime_max_mm'],flush=True)
    report={'scope':'Current installed visual GLBs only, read-only; deterministic point-to-triangle samples against independently tessellated source. Differences are witnessed surface discrepancies, not certified CAD tolerances or proofs of visible loss. Same-color checks compare material source-color metadata and do not sample textures.','ledger_sha256':digest(OUT/'ledger.json'),'results':results}
    for dest in [OUT/'comparison.json',Path(__file__).with_name('comparison.json')]:dest.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
