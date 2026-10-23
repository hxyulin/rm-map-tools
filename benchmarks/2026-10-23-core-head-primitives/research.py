"""Bounded box/cylinder/hull fit screen against the accepted head collision."""
import importlib.util,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.optimize import minimize
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('head_vectors_survey',ROOT/'benchmarks/2026-10-23-core-head-back-trial/survey.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
p=previous.p;scan=p.scan
OUT=ROOT/'out/rmuc2027-core-head-primitives'

def cylinder_fits(g):
    pts=np.unique(g.reshape(-1,3),axis=0);axes=[]
    for frame in scan.frames(g):
        for axis in frame.T:
            if not any(abs(axis@other)>.9999 for other in axes):axes.append(axis)
    fits=[]
    for axis in axes[:14]:
        a,u,v=p.basis(axis);q=pts@np.column_stack([u,v,a]);origin=q[:,:2].mean(0);scale=np.ptp(q[:,:2],axis=0).max()
        xy=(q[:,:2]-origin)/scale
        opt=minimize(lambda c:np.sum((xy-c)**2,axis=1).max(),[0.,0.],method='Nelder-Mead',options={'maxiter':200,'xatol':1e-9})
        c=opt.x*scale+origin;radius=np.linalg.norm(q[:,:2]-c,axis=1).max();lo,hi=q[:,2].min(),q[:,2].max()
        if hi-lo<.01:continue
        shape=p.shape(c[0]*u+c[1]*v+(lo+hi)/2*a,a,radius,hi-lo)
        # Uniform analytic cylinder side/cap points, not polygon-only samples.
        phi=np.arange(48)*2*np.pi/48;rad=np.cos(phi)[:,None]*u+np.sin(phi)[:,None]*v;center=np.array(shape['center_m'])*1000
        surface=np.concatenate([(center+z*a+radius*rad)for z in np.linspace(-(hi-lo)/2,(hi-lo)/2,13)]+[
            center+sign*(hi-lo)/2*a+r*rad for sign in [-1,1]for r in np.linspace(0,radius,9)])
        sdf=p.solid_dist(pts,[shape]);rev=p.distances(surface,g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3))
        forward=float(abs(sdf).max());reverse=float(rev.max())
        fits.append(dict(kind='cylinder',parameters=shape,source_surface_max_mm=forward,reverse_max_mm=reverse,score_mm=max(forward,reverse)))
    return sorted(fits,key=lambda r:r['score_mm'])

def main():
    OUT.mkdir(exist_ok=True);report_path=ROOT/'out/rmuc2027-core-head-back-trial/compact-12mm/verification.json';report=json.loads(report_path.read_text());source=Path(report['candidate_collision'])
    assert scan.digest(source)==report['candidate_sha256'];d,c,n=scan.load_nodes(source)
    candidates=sorted([(len(g),i)for i,g in n.items()if c[i]=='technology-core/tool-head'and len(g)>=60 and i!=1668],reverse=True)[:65]
    rows=[]
    for count,ni in candidates:
        g=n[ni];pts=np.unique(g.reshape(-1,3),axis=0);row=dict(node=ni,name=d['nodes'][ni]['name'],source_triangles=count,bounds_mm=[pts.min(0).tolist(),pts.max(0).tolist()],trials=[])
        # Boxes with area-ranked source face axes, coarse maxima before refinement.
        fits=[f for f in scan.fit_boxes(g)if f['mode']=='enclosing']
        if fits:
            fit=fits[0];center=np.array(fit['center_mm']);frame=np.array(fit['axes_columns']);half=np.array(fit['half_extents_mm'])
            grid=scan.box_grid(center,frame,half,max(.5,float(half.max())/12),20000)
            reverse=p.distances(grid,g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3)) if grid is not None else np.array([1e9])
            row['trials'].append(dict(kind='box',parameters=fit,source_surface_max_mm=fit['source_surface_max_mm'],reverse_max_mm=float(reverse.max()),score_mm=max(fit['source_surface_max_mm'],float(reverse.max()))))
        try:
            hull=ConvexHull(pts);h=pts[hull.simplices]
            sample=np.concatenate([h.reshape(-1,3),h.mean(1),scan.area_samples(h,2000,seed=33)])
            rd=p.distances(sample,g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3));fd=p.distances(pts,h.reshape(-1,3),np.arange(len(h)*3).reshape(-1,3))
            row['trials'].append(dict(kind='convex-hull',vertices_mm=pts[hull.vertices].tolist(),preview_triangles=len(h),source_surface_max_mm=float(fd.max()),reverse_max_mm=float(rd.max()),score_mm=float(max(fd.max(),rd.max()))))
        except Exception as error:row['hull_error']=type(error).__name__
        # Cylinder screening is bounded to compact parts and roughly round cases.
        ext=np.sort(np.ptp(pts,axis=0));roundish=ext[-1]<130 and (ext[-1]/max(ext[-2],.01)<3 or ext[1]/max(ext[0],.01)<2)
        if roundish:
            fits=cylinder_fits(g)
            if fits:row['trials'].append(fits[0])
        best=min(row['trials'],key=lambda x:x['score_mm']);row['best']=best['kind'];row['best_score_mm']=best['score_mm'];rows.append(row)
        print(ni,count,best['kind'],round(best['score_mm'],3),flush=True)
    result=dict(source=str(source),source_sha256=scan.digest(source),accepted_head_report=str(report_path),accepted_head_report_sha256=scan.digest(report_path),
        screened_nodes=len(rows),rows=rows,limits='Coarse finite fit screen. Full refinement and preserved-interface ray checks are required before selection; large holes and sockets cannot be inferred safe from shape appearance.')
    (OUT/'screen.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
