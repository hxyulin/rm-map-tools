# SPDX-License-Identifier: MIT OR Apache-2.0
"""Deterministic bidirectional point-to-triangle samples, per bound primitive.

This is sampled validation, not a Hausdorff proof. Report coordinates in mm.
"""
import argparse,json,sys
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from gltf_scene import read_glb,accessor,scene_nodes


def arrays(d,b,p):
    v=accessor(d,b,p['attributes']['POSITION']).astype(float)
    t=(accessor(d,b,p['indices']) if 'indices' in p else np.arange(len(v))).reshape(-1,3)
    return v,t


def samples(v,t):
    area=np.linalg.norm(np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]]),axis=1)
    t=t[area>1e-20]
    if not len(t):return np.empty((0,3))
    selected=t[np.linspace(0,len(t)-1,min(1024,len(t)),dtype=int)]
    p=v[selected]
    return np.vstack([p.mean(axis=1),p[:,0],(p[:,0]+p[:,1])/2])


def distance(points,v,t):
    area=np.linalg.norm(np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]]),axis=1)
    t=t[area>1e-20]
    if not len(t):
        from scipy.spatial import cKDTree
        return (cKDTree(v).query(points)[0]*1000).tolist()
    pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(np.ascontiguousarray(v),deep=True))
    cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(t),3),t]).astype(np.int64).ravel(),deep=True))
    poly=vtk.vtkPolyData();poly.SetPoints(pts);poly.SetPolys(cells)
    locator=vtk.vtkStaticCellLocator();locator.SetDataSet(poly);locator.BuildLocator()
    closest=[0.,0.,0.];cell=vtk.reference(0);sub=vtk.reference(0);dist2=vtk.reference(0.)
    errors=[]
    for p in points:
        locator.FindClosestPoint(p,closest,cell,sub,dist2)
        errors.append(float(dist2)**.5*1000)
    return errors


parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('before',type=Path);parser.add_argument('after',type=Path);parser.add_argument('output',type=Path)
a=parser.parse_args();report={}
for scope in ('','equipment'):
    manifest=json.load(open(a.after/scope/'manifest.json'))
    for name,entry in manifest['assets'].items():
        if not entry.get('mesh_simplification'):continue
        for kind in ('visual','collision'):
            d,b=read_glb(a.before/scope/entry[kind]);e,c=read_glb(a.after/scope/entry[kind])
            worst=[];values=[];seen=set()
            for i,world,_ in scene_nodes(d):
                n=d['nodes'][i];new=e['nodes'][i]
                if 'mesh' not in n:continue
                for pi,p in enumerate(d['meshes'][n['mesh']]['primitives']):
                    key=(n['mesh'],pi)
                    if key in seen:continue
                    seen.add(key)
                    q=e['meshes'][new['mesh']]['primitives'][pi]
                    v,t=arrays(d,b,p);w,u=arrays(e,c,q)
                    if len(t)==len(u) and np.array_equal(v[t],w[u]):continue
                    v=v@world[:3,:3].T+world[:3,3];w=w@world[:3,:3].T+world[:3,3]
                    errors=distance(samples(v,t),w,u)+distance(samples(w,u),v,t)
                    values.extend(errors)
                    worst.append({'node':i,'primitive':pi,'max_mm':max(errors),'before':len(t),'after':len(u)})
            key=name+'/'+kind
            report[key]={'sample_count':len(values),'max_mm':max(values,default=0),'p99_mm':float(np.percentile(values,99)) if values else 0,'worst':sorted(worst,key=lambda x:-x['max_mm'])[:10]}
            print(key,report[key]['sample_count'],report[key]['max_mm'],report[key]['p99_mm'],flush=True)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
