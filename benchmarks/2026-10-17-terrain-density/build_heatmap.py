#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Placed native terrain triangle-density maps with approved wall substitutions."""
import argparse,hashlib,json,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,mesh_instances
from triangle_density import centroid_grid
from cad_collision_roles import CollisionRoles
from plan_cad_lods import build_plan,digest


def triangles(path,matrix):
    doc,binary=read_glb(path);chunks=[];m=np.array(matrix)
    for _,_,p,t,_ in mesh_instances(doc,binary):
        p=p*1000@m[:3,:3].T+m[:3,3]
        chunks.append(p[t]/1000)
    if not chunks:raise ValueError('empty source geometry')
    return np.concatenate(chunks)


def sparse(grid):
    return [[int(i),int(v)] for i,v in enumerate(grid.ravel()) if v]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--walls',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    hierarchy=ROOT/'out/rmuc2027-hierarchy/hierarchy.json';catalog=json.loads(hierarchy.read_bytes());native=json.loads((a.native/'audit.json').read_bytes());walls=json.loads((a.walls/'summary.json').read_bytes())
    source_sha=catalog['files_sha256']['field.step'];hierarchy_sha=digest(hierarchy)
    if any(r['source_sha256']!=source_sha or r['hierarchy_sha256']!=hierarchy_sha for r in (native,walls)):raise ValueError('source/hierarchy mismatch')
    if digest(ROOT/'rules/wall-fills-rmuc2027.json')!=walls['policy_sha256']:raise ValueError('wall policy changed')
    roles=CollisionRoles.read(ROOT/'rules/roles-rmuc2027-terrain.json',hierarchy)
    uses={}
    for n in build_plan(catalog)['nodes']:
        if n['component_id']:uses.setdefault(n['component_id'],[]).append(n)
    candidates={c['component_id']:c for c in walls['components']};sources={c['id']:c for c in native['components']}
    floor=sources['floor/body-23736'];center=np.mean(np.array(floor['bbox_mm']),axis=0)[:2]/1000
    lower=np.array([-14.5,-8.5]);upper=np.array([14.5,8.5]);cell=.5
    components=[];native_total=0;substitution_total=0
    for cid in sorted(set(sources)|set(candidates)):
        source=sources.get(cid);replacement=candidates.get(cid);name=cid.split('/')[0]
        if source:
            original=a.native/cid/'visual.glb';expected=source['visual_sha256'];expected_triangles=source['triangles']
        else:
            original=a.walls/name/'source.glb';expected=replacement['before']['sha256'];expected_triangles=replacement['before']['triangles']
        if digest(original)!=expected:raise ValueError('source mesh checksum mismatch')
        current=a.walls/name/'candidate.glb' if replacement else original
        if replacement and digest(current)!=replacement['after']['sha256']:raise ValueError('wall candidate checksum mismatch')
        grids=[]
        for path in (original,current):
            all_triangles=[]
            for use in uses[cid]:
                geometry=triangles(path,use['world_matrix_mm']);geometry[:,:,:2]-=center;all_triangles.append(geometry)
            geometry=np.concatenate(all_triangles)
            grids.append(centroid_grid(geometry,lower_m=lower,upper_m=upper,cell_size_m=cell))
        if int(grids[0].sum())!=expected_triangles*len(uses[cid]):raise ValueError('source placed triangles mismatch')
        if replacement and (len(uses[cid])!=replacement['placed_uses'] or grids[1].sum()!=replacement['after']['triangles']*len(uses[cid])):raise ValueError('replacement placement/count mismatch')
        road=name in ('red-road-surface','blue-road-surface')
        components.append({'id':cid,'placed_uses':len(uses[cid]),'road':road,'collision':roles.collision_enabled(cid),
                           'native_triangles':int(grids[0].sum()),'candidate_triangles':int(grids[1].sum()),
                           'native_grid':sparse(grids[0]),'candidate_grid':sparse(grids[1]),'source_mesh_sha256':expected,'candidate_mesh_sha256':digest(current)})
        native_total+=int(grids[0].sum());substitution_total+=int(grids[1].sum())
    assert native_total==native['summary']['placed_triangles']+sum(c['before']['triangles']*c['placed_uses'] for cid,c in candidates.items() if cid not in sources)
    assert native_total-substitution_total==walls['placed_triangles_before']-walls['placed_triangles_after']
    shape=(int((upper[1]-lower[1])/cell),int((upper[0]-lower[0])/cell))
    def grid(c,revision):
        out=np.zeros(np.prod(shape),dtype=np.int64)
        for i,v in c[revision+'_grid']:out[i]=v
        return out.reshape(shape)
    scenarios={};render_grids={}
    for revision in ('native','candidate'):
        for channel in ('visual','collision'):
            for roads in (True,False):
                selected=[c for c in components if (channel=='visual' or c['collision']) and (roads or not c['road'])]
                image=sum((grid(c,revision) for c in selected),np.zeros(shape,dtype=np.int64));key=f'{revision}-{channel}-'+('all' if roads else 'without-roads');render_grids[key]=image
                hot=[]
                for index in np.argsort(image.ravel())[::-1][:10]:
                    y,x=divmod(int(index),shape[1]);value=int(image[y,x])
                    if not value:continue
                    contributors=sorted([{'id':c['id'],'triangles':int(grid(c,revision)[y,x])} for c in selected],key=lambda x:x['triangles'],reverse=True)
                    hot.append({'xy_center_m':(lower+(np.array([x,y])+.5)*cell).tolist(),'triangles':value,'contributors':[c for c in contributors[:5] if c['triangles']]})
                ranked=sorted([{'id':c['id'],'placed_triangles':c[revision+'_triangles']} for c in selected],key=lambda r:r['placed_triangles'],reverse=True)
                scenarios[key]={'triangles':int(image.sum()),'occupied_cells':int(np.count_nonzero(image)),'max_triangles_per_cell':int(image.max()),'top_10_cells_fraction':float(np.sort(image.ravel())[-10:].sum()/image.sum()),'hot_cells':hot,'ranked_components':ranked}
    a.out.mkdir(parents=True)
    data={'shape_yx':shape,'lower_m':lower.tolist(),'upper_m':upper.tolist(),'cell_size_m':cell,'source_xy_center_m':center.tolist(),'components':components}
    (a.out/'density.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    fig,axes=plt.subplots(2,2,figsize=(16,10),constrained_layout=True)
    panels=[('native-visual-all','Native visual baseline'),('candidate-visual-all','Visual: approved wall fills'),('candidate-collision-all','Collision: wall fills + whole-marking exclusions'),('candidate-collision-without-roads','Collision: same selection, road groups hidden')]
    maximum=max(g.max() for g in render_grids.values());cmap=plt.get_cmap('inferno').copy();cmap.set_bad('#e9eef3')
    for ax,(key,title) in zip(axes.flat,panels):
        values=render_grids[key];im=ax.imshow(np.ma.masked_equal(values,0),origin='lower',extent=[lower[0],upper[0],lower[1],upper[1]],norm=LogNorm(vmin=1,vmax=maximum),cmap=cmap,interpolation='nearest');ax.set_title(f'{title}\n{values.sum():,} placed triangles');ax.set_xlabel('Field-centered CAD x (m)');ax.set_ylabel('CAD y (m)');ax.set_aspect('equal');ax.grid(alpha=.12)
    fig.colorbar(im,ax=axes.ravel().tolist(),label='Triangle centroids per 0.5 × 0.5 m cell (log scale)',shrink=.8)
    fig.suptitle('Terrain plus four grilles · native 0.4 mm / 0.25 rad · road LOD pending',fontsize=14)
    fig.savefig(a.out/'heatmap.png',dpi=160);fig.savefig(a.out/'heatmap.svg');plt.close(fig)
    summary={'source_sha256':source_sha,'hierarchy_sha256':hierarchy_sha,'native_audit_sha256':digest(a.native/'audit.json'),'wall_report_sha256':digest(a.walls/'summary.json'),
             'wall_policy_sha256':walls['policy_sha256'],'roles_sha256':digest(ROOT/'rules/roles-rmuc2027-terrain.json'),'grid':{k:data[k] for k in ('shape_yx','lower_m','upper_m','cell_size_m','source_xy_center_m')},
             'definitions':len(components),'placed_uses':sum(c['placed_uses'] for c in components),'scenarios':scenarios,
             'scope':'Native meshing + source-pinned approved wall fills and whole-component collision exclusions. All placed uses counted. Main road LOD and separate one-border vector experiment are not substituted; embedded markings retain backing triangles. Equipment entities other than footings and four selected grilles excluded. Centroid density is not GPU cost or covered area.',
             'producer_sha256':{str(f.relative_to(ROOT)):digest(f) for f in [Path(__file__),ROOT/'python/triangle_density.py']},'outputs_sha256':{name:digest(a.out/name) for name in ('density.json','heatmap.png','heatmap.svg')}}
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({key:value['triangles'] for key,value in scenarios.items()},indent=2))
if __name__=='__main__':main()
