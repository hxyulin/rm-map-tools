"""Simplify measured outer profiles of two thin Dart collision plates."""
import json
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from PIL import Image

from scan import ROOT, OUT, REF, load_nodes, frames, area_samples, digest
from render import preview_glb, data
import collision_review_render as raster
from mesh_quality import distances


def edge_distance(points,a,b):
    delta=b-a
    v=np.clip((points-a)@delta/(delta@delta),0,1)
    return np.linalg.norm(points-a-v[:,None]*delta,axis=1)


def polygon_distance(points,poly):
    # CCW convex polygon: negative means inside. Exact 2D Euclidean outside.
    outside=np.zeros(len(points),bool);d=np.full(len(points),np.inf)
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        ab=b-a;ap=points-a
        outside |= ab[0]*ap[:,1]-ab[1]*ap[:,0] < -1e-7
        d=np.minimum(d,edge_distance(points,a,b))
    return d*outside


def simplify(poly,tol):
    original=poly.copy()
    while len(poly)>3:
        trials=[]
        for i in range(len(poly)):
            q=np.delete(poly,i,axis=0)
            error=float(polygon_distance(original,q).max())
            trials.append((error,i))
        error,i=min(trials)
        if error>tol:break
        poly=np.delete(poly,i,axis=0)
    return poly,float(polygon_distance(original,poly).max())


def main():
    ref=json.loads(REF.read_text());source=ref['roles']['collision']['assets']['arena-static']['path']
    sha=digest(__import__('pathlib').Path(source));_,components,nodes=load_nodes(source);rows=[]
    for ni in [260,493]:
        g=nodes[ni];p=np.unique(g.reshape(-1,3),axis=0)
        # Choose frame with smallest total volume, then reorder thin axis last.
        f=min(frames(g),key=lambda f:np.prod(np.ptp(p@f,axis=0)))
        order=np.argsort(np.ptp(p@f,axis=0))[::-1];f=f[:,order]
        if np.linalg.det(f)<0:f[:,1]*=-1
        q=p@f;poly=q[ConvexHull(q[:,:2]).vertices,:2]
        for tol in [.25,.5,1.0]:
            outline,error=simplify(poly,tol)
            vertices=np.concatenate([np.column_stack([outline,np.full(len(outline),z)]) for z in [q[:,2].min(),q[:,2].max()]])@f.T
            hull=ConvexHull(vertices);candidate=vertices[hull.simplices]
            probes=np.concatenate([vertices,area_samples(candidate,50000,987)])
            reverse=distances(probes,g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3))
            # Hull envelope planes measure omitted outside corners analytically.
            signed=p@hull.equations[:,:3].T+hull.equations[:,3]
            row=dict(asset='arena-static',node=ni,component=components[ni],source=source,source_sha256=sha,
                source_triangles=len(g),source_polygon_vertices=len(poly),polygon_vertices=len(outline),
                native_hull_vertices=len(vertices),preview_triangles=len(candidate),
                profile_loss_limit_mm=tol,profile_outside_max_mm=error,
                source_max_support_plane_outside_mm=float(np.maximum(signed,0).max()),
                reverse_sampled_max_mm=float(reverse.max()),reverse_samples=len(probes),
                span_mm=np.ptp(q,axis=0).tolist(),vertices_source_scene_mm=vertices.tolist(),
                frame_axes_columns=f.tolist(),status='review_only',
                caveat='Prism fills small plate openings and any thickness bevel; reverse includes these fills. Not contact qualified. Hull outside support-plane metric is not Euclidean distance.')
            key=f'arena-static-{ni}-profile-{tol:g}mm';target=OUT/(key+'-diagnostic.glb')
            preview_glb(target,candidate,source,ni);row['preview']=str(target);row['preview_sha256']=digest(target)
            rows.append(row);print(ni,tol,len(poly),len(outline),len(candidate),error,float(reverse.max()),flush=True)
    assert digest(__import__('pathlib').Path(source))==sha
    (OUT/'profiles.json').write_text(json.dumps(rows,indent=2)+'\n')


def render_profiles():
    rows=json.loads((OUT/'profiles.json').read_text());views=[]
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);helper=tmp/'raster'
        subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for row in rows:
            if row['profile_loss_limit_mm']!=.25:continue
            _,_,nodes=load_nodes(row['source']);g=nodes[row['node']]
            vertices=np.asarray(row['vertices_source_scene_mm']);candidate=vertices[ConvexHull(vertices).simplices]
            before=data(g,[.65,.65,.65]);after=data(candidate,[.3,.65,.8])
            for direction,label in [((1,.65,1),'oblique'),((-1,.65,-1),'reverse')]:
                for stage,item in [('source',before),('proxy',after)]:
                    path=OUT/f"arena-static-{row['node']}-profile-{label}-{stage}.webp"
                    Image.fromarray(raster.raster(item,before[0],direction,helper,tmp)).save(path,lossless=True)
                    views.append(dict(node=row['node'],view=label,stage=stage,path=str(path),sha256=digest(path)))
    (OUT/'profile-renders.json').write_text(json.dumps(views,indent=2)+'\n')


if __name__=='__main__':
    if '--render-only' in __import__('sys').argv:render_profiles()
    else:main()
