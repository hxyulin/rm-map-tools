# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compare complete static Core geometry with the disposable demo rig at rest. Run from the repository root."""
import sys,json,numpy as np,vtk
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gltf_scene import read_glb,scene_nodes,mesh_instances
from export_semantics import digest
from preview.render_joints import actor_for_primitive,vtk_matrix
from preview.tech_core_demo import prepare_demo
from verify_reference_motion import triangle_records
from vtk.util.numpy_support import vtk_to_numpy
from PIL import Image
out=Path('docs/previews/core-audit');out.mkdir(parents=True,exist_ok=True)
p=Path('../assets/rm2026-reference/equipment');d,b=read_glb(p/'tech-core.glb');binding=json.loads((p/'articulation.json').read_text())['assets']['tech-core']['files']['visual'];demo,db,*_,report=prepare_demo(d,b,binding)
source,sb=read_glb(Path('../assets/rm2026-field/equipment/tech-core.glb'))
np.testing.assert_array_equal(triangle_records(source,sb),triangle_records(d,b))
hidden=report['hidden_shared_hardware_node'];counts={}
for i,_,x,t,_ in mesh_instances(d,b):counts[i]=counts.get(i,0)+len(t)
result={'source_sha256':digest(Path('../assets/rm2026-field/equipment/tech-core.glb')),'reference_sha256':digest(p/'tech-core.glb'),'source_reference_triangle_material_match':True,'source_triangles':sum(counts.values()),'preview_hidden_node':d['nodes'][hidden]['name'],'previous_preview_hidden_triangles':counts[hidden], 'preview_hidden_triangles':report['hidden_hardware_triangles'], 'restored_tool_enclosure_triangles':report['restored_tool_enclosure_triangles'], 'partition': {'primitive': 0, 'triangle_ranges': [[91775,118288]], 'mesh_sha256': report['tool_enclosure_partition_sha256']},'source_parts':[{'name':d['nodes'][i]['name'],'triangles':n} for i,n in counts.items()],'culling':'Disabled for every audit actor; open areas are not backface culling.'}
xyz=np.vstack([x for _,_,x,_,_ in mesh_instances(d,b)]);center=(xyz.min(0)+xyz.max(0))/2;size=max(np.ptp(xyz,axis=0))
for angle,view in [('front',[-1.6,-1.2,.8]),('rear',[1.6,1.2,.8]),('side',[-1.2,1.6,.5])]:
 imgs=[]
 for label,doc,data in [('source',d,b),('demo',demo,db)]:
  ren=vtk.vtkRenderer();ren.SetBackground(.08,.09,.11);win=vtk.vtkRenderWindow();win.SetOffScreenRendering(1);win.SetSize(640,640);win.AddRenderer(ren)
  for i,w,_ in scene_nodes(doc):
   n=doc['nodes'][i]
   if 'mesh' not in n:continue
   for pr in doc['meshes'][n['mesh']]['primitives']:
    actor=actor_for_primitive(doc,data,pr);actor.SetUserMatrix(vtk_matrix(w));ren.AddActor(actor)
  cam=ren.GetActiveCamera();cam.SetPosition(*(center+np.array(view)*size*2));cam.SetFocalPoint(*center);cam.SetViewUp(0,0,1);cam.ParallelProjectionOn();cam.SetParallelScale(size*.68);ren.ResetCameraClippingRange();win.Render()
  cap=vtk.vtkWindowToImageFilter();cap.SetInput(win);cap.ReadFrontBufferOff();cap.Update();pix=vtk_to_numpy(cap.GetOutput().GetPointData().GetScalars()).reshape(640,640,3)[::-1].copy();imgs.append(pix);win.Finalize()
 Image.fromarray(np.hstack(imgs)).save(out/f'{angle}-source-left-demo-right.png')
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
