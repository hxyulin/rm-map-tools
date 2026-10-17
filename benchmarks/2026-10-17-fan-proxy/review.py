#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Draw exact fan locations and compare the authorized hollow-box proxy."""
import argparse,importlib.util,itertools,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import digest
from gltf_scene import read_glb,accessor

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();report=json.loads((out/'summary.json').read_bytes());terrain=json.loads((ROOT/'out/rmuc2027-terrain-cost-full/audit.json').read_bytes());centre=np.array(report['field_centre_source_xy_mm']);import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from scipy.spatial import ConvexHull
    fig,ax=plt.subplots(figsize=(13,7));fig.patch.set_facecolor('#f4f6f9');ax.set_facecolor('#f4f6f9')
    for c in terrain['components']:
        name=c['id'];selected=name.startswith(('floor/body-23736','assembly-area/','central-deck/','central-tunnel-side','red-trapezoid','blue-trapezoid','red-high-point','blue-high-point','base-footing/','outpost-footing/')) or name.endswith(('shell-3797315','shell-3813137'))
        if not selected:continue
        bounds=np.array(c['bbox_mm']);corners=np.array(list(itertools.product(*zip(bounds[0],bounds[1]))))
        for use in c['occurrences']:
            m=np.array(use['world_matrix_mm']);p=corners@m[:3,:3].T+m[:3,3];xy=(p[:,:2]-centre)/1000;unique=np.unique(np.round(xy,7),axis=0)
            if len(unique)<3:continue
            polygon=unique[ConvexHull(unique).vertices];floor=name.startswith('floor/');high='high-point' in name;color='#98b1c4' if high else '#cbd3dc';ax.add_patch(Polygon(polygon,facecolor='none' if floor else color,edgecolor='#8391a2',lw=1.2 if floor else .6,alpha=1 if floor else .6))
    for fan in report['placements']:
        x,y=fan['centre_field_xy_m'];high=fan['context']!='standalone fixture';colour='#d54b33' if high else '#2165b0';ax.scatter([x],[y],s=105,c=colour,edgecolors='white',linewidths=1.2,zorder=8)
        # Offset close pairs in opposite directions, without moving their dots.
        dx=.15 if fan['id'] in [1,3,5,7,9,10] else -.15;dy=.65 if fan['id'] in [1,3,5,7,9,10] else -.75;ax.annotate(str(fan['id']),(x,y),(x+dx,y+dy),ha='center',va='center',color=colour,fontsize=11,fontweight='bold',arrowprops={'arrowstyle':'-','color':colour,'lw':.8},zorder=9)
    ax.scatter([],[],c='#d54b33',s=80,label='High-point assembly fans (4)');ax.scatter([],[],c='#2165b0',s=80,label='Standalone source fixtures (6)');ax.set(xlim=(-15,15),ylim=(-9,9),xlabel='Field-centred CAD x (m)',ylabel='Field-centred CAD y (m)',title='All ten fan placements — dots are actual transformed mesh centres');ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend(loc='upper center',bbox_to_anchor=(.5,-.13),ncol=2,frameon=False);fig.text(.5,.015,'Background is a schematic of projected source component bounds, not an exact field outline.',ha='center',fontsize=9,color='#566070');fig.tight_layout(rect=(0,.06,1,1));fig.savefig(out/'locations.png',dpi=150);fig.savefig(out/'locations.svg');plt.close(fig)
    source=ROOT/'out/rmuc2027-equipment-pipeline/fan/body-2717086';native=np.load(source/'native.npz');proxy=np.load(out/'geometry.npz');origin=np.array(report['source_origin_mm']);frame=np.array(report['source_frame_rows']);old=((native['positions_mm'][native['triangles']]-origin)@frame.T)[:,:,[1,2,0]]/1000;new=((proxy['positions_mm'][proxy['triangles']]-origin)@frame.T)[:,:,[1,2,0]]/1000;colour=np.array([.6275,.6275,.6275]);raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');views=[('front',(0,.000001,1)),('rear',(0,.000001,-1)),('oblique',(1,.6,1.5)),('reverse',(-1,.6,-1.5)),('side',(1,.000001,0)),('top',(0,1,.000001)),('bottom',(0,-1,.000001))];checks=[]
    before,_=read_glb(source/'native.glb');after,blob=read_glb(out/'fan-proxy.glb')
    if before['materials']!=after['materials']:raise ValueError('proxy changed fallback appearance')
    count=sum(accessor(after,blob,p['indices']).size//3 for n in after['nodes'] if 'mesh' in n for p in after['meshes'][n['mesh']]['primitives'])
    if count!=56:raise ValueError('proxy exported count mismatch')
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for name,view in views:
            images={stage:raster.raster(g,np.tile(colour,(len(g),1)),old,view,helper,tmp,out/(stage+'-'+name+'.png')) for stage,g in [('source',old),('proxy',new)]};checks.append({'view':name,**metrics.metric(images['source'],images['proxy'])})
    result={'proxy_glb_sha256':digest(out/'fan-proxy.glb'),'exported_triangles':count,'fallback_material_exact':True,'views':checks,'producer_sha256':digest(Path(__file__)),'scope':'Location dots use actual transformed source mesh bounds; background is schematic projected component bounds. Proxy intentionally changes apertures and removes end panels. Pixel differences are reported, not a small-error acceptance test. Source/rest pose flat diagnostics only; original collision remains unchanged.'};(out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
