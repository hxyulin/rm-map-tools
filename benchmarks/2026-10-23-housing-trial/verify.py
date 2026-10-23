# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent reopen, untouched-payload, topology and optical contact checks."""
import json,sys
from pathlib import Path
import numpy as np
import trial
from trial import read_glb,accessor,scene_nodes,load,digest,refine,scene_triangles
from cad_collision_profiles import mesh_metrics

def contacts(a,b):
 import vtk
 from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
 def poly(g):
  p=vtk.vtkPoints();p.SetData(numpy_to_vtk(g.reshape(-1,3),deep=True));c=vtk.vtkCellArray();c.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(g),3),np.arange(g.size//3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True));d=vtk.vtkPolyData();d.SetPoints(p);d.SetPolys(c);return d
 if not len(a) or not len(b):return 0
 op=vtk.vtkCollisionDetectionFilter();op.SetInputData(0,poly(a));op.SetInputData(1,poly(b));matrix=vtk.vtkMatrix4x4();matrix.Identity();op.SetMatrix(0,matrix);op.SetMatrix(1,matrix);op.SetCollisionModeToFirstContact();op.SetBoxTolerance(0);op.SetCellTolerance(0);op.Update();return op.GetNumberOfContacts()
def topology(g):
 p,inv=np.unique(np.round(g.reshape(-1,3),5),axis=0,return_inverse=True);return mesh_metrics(p,inv.reshape(-1,3))
def verify(path):
 report=json.loads(path.read_text());checks=[]
 for key,row in report['assets'].items():
  source=Path(row['input']);base=Path(row['baseline']);target=Path(row['output']);assert digest(source)==row['input_sha256'];assert digest(base)==row['baseline_sha256'];assert digest(target)==row['output_sha256']
  sd,sb=read_glb(source);bd,bb=read_glb(base);cd,cb=read_glb(target);assert bd['materials']==cd['materials'];assert len(bd['nodes'])==len(cd['nodes']);changed={(p['target_node'],p['target_primitive']) for p in row['changed_pieces']};protected=[];worlds={i:w for i,w,_ in scene_nodes(sd)}
  for i,w,parent in scene_nodes(sd):
   if 'mesh' not in sd['nodes'][i]:continue
   for p in sd['meshes'][sd['nodes'][i]['mesh']]['primitives']:
    if not refine.structural(sd['materials'][p['material']],p):protected.append(load(sd,sb,p)@w[:3,:3].T+w[:3,3]*1000)
  pg=np.concatenate(protected) if protected else np.empty((0,3,3));cw={i:w for i,w,_ in scene_nodes(cd)};untouched=0;pieces=[]
  for i,(bn,cn) in enumerate(zip(bd['nodes'],cd['nodes'])):
   assert {k:v for k,v in bn.items() if k!='mesh'}=={k:v for k,v in cn.items() if k!='mesh'}
   if 'mesh' not in bn:assert 'mesh' not in cn;continue
   bp=bd['meshes'][bn['mesh']]['primitives'];cp=cd['meshes'][cn['mesh']]['primitives'];assert len(bp)==len(cp)
   for pi,(b,c) in enumerate(zip(bp,cp)):
    for name,ai in c['attributes'].items():assert np.isfinite(accessor(cd,cb,ai)).all()
    if (i,pi) not in changed:
     assert b.keys()==c.keys();assert b['attributes'].keys()==c['attributes'].keys()
     for name,ai in b['attributes'].items():np.testing.assert_array_equal(accessor(bd,bb,ai),accessor(cd,cb,c['attributes'][name]))
     np.testing.assert_array_equal(accessor(bd,bb,b['indices']),accessor(cd,cb,c['indices']));untouched+=1;continue
    before=load(bd,bb,b);after=load(cd,cb,c);area=np.linalg.norm(np.cross(after[:,1]-after[:,0],after[:,2]-after[:,0]),axis=1);assert (area>1e-9).all()
    oldkeys={t.tobytes() for t in before};delta=np.array([t for t in after if t.tobytes() not in oldkeys]);count=contacts(delta@cw[i][:3,:3].T+cw[i][:3,3]*1000,pg);assert count==0,(key,i,'protected contact')
    pieces.append({'node':i,'primitive':pi,'baseline_topology':topology(before),'candidate_topology':topology(after),'protected_source_triangle_contacts':count,'finite_attributes':True,'zero_area_faces':0})
  def images(d,b):
   return [b[d['bufferViews'][im['bufferView']].get('byteOffset',0):d['bufferViews'][im['bufferView']].get('byteOffset',0)+d['bufferViews'][im['bufferView']]['byteLength']] for im in d.get('images',[])]
  assert images(bd,bb)==images(cd,cb);assert scene_triangles(cd)==row['candidate_scene_triangles'];checks.append({'asset':key,'untouched_primitive_payloads_equal':untouched,'embedded_images_equal':True,'materials_equal':True,'node_indices_hierarchy_and_frames_equal':True,'pieces':pieces})
 total={role:sum(scene_triangles(read_glb(Path(s['candidate']))[0])*max(1,len(s['placements'])) for s in report['stage_inputs'] if s['role']==role) for role in ['visual','collision']}
 for s in report['stage_inputs']:
  assert digest(Path(s['input']))==s['input_sha256'];assert digest(Path(s['baseline']))==s['baseline_sha256'];assert digest(Path(s['candidate']))==s['candidate_sha256']
 result={'ledger':str(path.resolve()),'ledger_sha256':digest(path),'assets':checks,'placed_totals':total,'scope':'Finite triangle intersection test with assembled source chromatic/emissive/UV/protected primitives plus exact unchanged payloads. Zero contacts does not prove rendered mask equality; Base artwork backing 4268930 is excluded completely. Open source-group topology is reported, not treated as a closed-solid certificate.'}
 (path.parent/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'placed_totals':total,'assets_verified':len(checks)}))
if __name__=='__main__':verify(Path(sys.argv[1]) if len(sys.argv)>1 else trial.OUT/'coarse/ledger.json')
