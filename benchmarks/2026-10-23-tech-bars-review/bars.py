# SPDX-License-Identifier: MIT OR Apache-2.0
"""Restore source white grill strips with few planar triangles and full side faces."""
import copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'));sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review'))
import numpy as np
from gltf_scene import read_glb,write_glb,accessor,scene_nodes
from simplify_package import append_accessor,compact,scene_triangles
from mesh_quality import distances
from cad_planar_panels import rebuild_panels
from audit_current import scopes
OUT=ROOT/'out/rmuc2027-tech-bars-review'
UNITS=[1505813,1532402,1565338,1568579]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def samples(g):return np.concatenate([g[:,0],g[:,1],g[:,2],g.mean(1)])
def main():
 source=ROOT/'out/rmuc2027-visual-fidelity-review/protected-1mm/tech-core.glb';doc,blob=read_glb(source);changed=copy.deepcopy(doc);binary=bytearray(blob)
 native=ROOT/'out/rmuc2027-protected-source-reference/technology-core/tool-head/reference.npz';z=np.load(native);g=z['positions_mm'][z['triangles']];units=z['source_unit_ids'];white=z['palette'][z['material_ids']]=='1.0000,1.0000,1.0000';sel=np.isin(units,UNITS)&white;original=g[sel];flat=original.reshape(-1,3);indices=np.arange(len(flat)).reshape(-1,3)
 worlds={i:w for i,w,_ in scene_nodes(doc)};root=78;inverse=np.linalg.inv(worlds[root]);owners=scopes(doc,'tech-core');removed=[];matid=None
 for i,world,parent in scene_nodes(doc):
  n=doc['nodes'][i]
  if 'mesh'not in n or owners[i][0]!='technology-core/tool-head':continue
  mesh=doc['meshes'][n['mesh']];prims=[];changed_node=False
  for pi,pr in enumerate(mesh['primitives']):
   material=doc['materials'][pr['material']]
   if material.get('extras',{}).get('step_colour_srgb')!=[1.,1.,1.]:prims.append(copy.deepcopy(pr));continue
   p=accessor(doc,blob,pr['attributes']['POSITION']);t=accessor(doc,blob,pr['indices']).reshape(-1,3);matrix=inverse@world;q=((p@matrix[:3,:3].T+matrix[:3,3])*1000)[t]
   error=distances(samples(q),flat,indices).reshape(4,-1).max(0);drop=error<1.1
   if not drop.any():prims.append(copy.deepcopy(pr));continue
   matid=pr['material'];changed_node=True;removed.append({'node':i,'primitive':pi,'triangles':int(drop.sum()),'triangle_indices':np.flatnonzero(drop).tolist(),'max_sample_to_source_mm':float(error[drop].max())})
   if not drop.all():
    cp=copy.deepcopy(pr);cp['indices']=append_accessor(changed,binary,np.ascontiguousarray(t[~drop].ravel(),dtype=np.uint32),'SCALAR',5125);prims.append(cp)
  if changed_node:
   if prims:changed['nodes'][i]['mesh']=len(changed['meshes']);changed['meshes'].append({**copy.deepcopy(mesh),'primitives':prims})
   else:changed['nodes'][i].pop('mesh',None)
 assert matid is not None
 records=[];pieces=[]
 for unit in UNITS:
  old=g[(units==unit)&white]
  keep,patches,proofs=rebuild_panels(old,old,plane_tolerance_mm=.001,boundary_tolerance_mm=.005,minimum_area_mm2=.01,minimum_source_triangles=2)
  new=np.concatenate([old[keep],patches]) if len(patches) else old.copy()
  # Never expand a small exact source shape merely to change triangulation.
  if len(new)>len(old):new=old.copy();proofs=[]
  errors=distances(samples(old),new.reshape(-1,3),np.arange(new.size//3).reshape(-1,3))
  reverse=distances(samples(new),old.reshape(-1,3),np.arange(old.size//3).reshape(-1,3))
  assert errors.max()<.01 and reverse.max()<.01
  pieces.append(new)
  records.append({'source_unit_id':unit,'before_source_triangles':len(old),'after_triangles':len(new),'forward_sample_max_mm':float(errors.max()),'reverse_sample_max_mm':float(reverse.max()),'planar_checks':proofs})
 combined=np.concatenate(pieces);p=(combined/1000).reshape(-1,3).astype(np.float32);normal=np.cross(combined[:,1]-combined[:,0],combined[:,2]-combined[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
 pr={'attributes':{'POSITION':append_accessor(changed,binary,p,'VEC3',5126),'NORMAL':append_accessor(changed,binary,np.repeat(normal,3,axis=0).astype(np.float32),'VEC3',5126)},'indices':append_accessor(changed,binary,np.arange(len(p),dtype=np.uint32),'SCALAR',5125),'material':matid}
 mi=len(changed['meshes']);changed['meshes'].append({'name':'source-grill-strips','primitives':[pr]});ni=len(changed['nodes']);changed['nodes'].append({'name':'source-grill-strips','mesh':mi,'extras':{'source_unit_ids':UNITS,'visual_fidelity_repair':True,'source_kind':'surface-shell-faces','source_color':[1.,1.,1.]}});changed['nodes'][root].setdefault('children',[]).append(ni)
 changed['asset'].setdefault('extras',{}).update(inspection_only=True,bar_repair='Source white strip faces restored; includes missing sides, all four units; no emission/material change.')
 payload=compact(changed,binary);target=OUT/'bars-restored.glb';write_glb(target,changed,payload);actual,ab=read_glb(target);report={'input':str(source),'input_sha256':digest(source),'source_npz':str(native),'source_npz_sha256':digest(native),'output':str(target),'sha256':digest(target),'before_core_triangles':scene_triangles(doc),'after_core_triangles':scene_triangles(actual),'removed':removed,'strips':records,'scope':'Source-coordinate planar white grill-strip repair only. Does not fill slots, change dark panel, materials or emission. Per-unit planar surface checks; no claim of runtime PBR equivalence.'};(OUT/'bars.json').write_text(json.dumps(report,indent=2)+'\n');print(report['before_core_triangles'],'->',report['after_core_triangles'],'removed',sum(x['triangles']for x in removed),'new',sum(x['after_triangles']for x in records))
if __name__=='__main__':main()
