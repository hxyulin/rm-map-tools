"""Complete unsimplified original native reference. No LOD/omission operations."""
import sys,json,copy,gc,re,mmap,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import build_plan,digest
from gltf_scene import read_glb,write_glb,scene_nodes,accessor
from export_field_package import GlbWriter
from mesh_parts import tessellate
from validate_parts import read_part
from cad_partition import _validate_mesh_stats
OUT=ROOT/'out/rmuc2027-full-source-field-review';PIPE=ROOT/'out/rmuc2027-equipment-pipeline'
def read(p):return json.loads(p.read_text())
def faces(path):
 with path.open('rb') as f:
  with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as m:return set(map(int,re.findall(rb'#(\d+)\s*=\s*ADVANCED_FACE\s*\(',m)))
def main():
 hpath=ROOT/'out/rmuc2027-hierarchy/hierarchy.json';h=read(hpath);inv=read(PIPE/'inventory.json');assert digest(hpath)==inv['hierarchy_sha256']
 original=ROOT/'source/RMUC2027_V1.0.0.stp';assert digest(original)==h['source_sha256']=='a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0'
 assert digest(hpath.with_name('field.step'))==h['files_sha256']['field.step']
 source_faces=faces(original);all_faces=set(f for c in h['components'] for f in c['face_ids']);assert source_faces==all_faces and len(all_faces)==h['source_face_definitions']
 plan=build_plan(h);byid={c['id']:c for c in h['components']};records=[];paths={}
 for item in inv['components']:
  cid=item['id'];c=byid[cid];source=PIPE/cid/'source.step';assert digest(source)==item['source_step_sha256'];assert faces(source)==set(c['face_ids'])
  if item['selected']:
   path=PIPE/cid/'native.glb';assert digest(path)==item['native_glb_sha256'];assert digest(PIPE/cid/'native.npz')==item['native_npz_sha256'];stats=item['stats'];method='inventory-pinned original native cache; shell mappings in native.npz'
  else:
   folder=OUT/'native'/cid;folder.mkdir(parents=True,exist_ok=True);path=folder/'native.glb';record=folder/'native.json'
   if record.exists():
    r=read(record);assert r['source_step_sha256']==digest(source) and digest(path)==r['sha256'];stats=r['stats']
   else:
    doc,reader,error=read_part(str(source));assert not error,error;stats={};observed=[]
    p,t,m,palette=tessellate(doc,.4,.25,stats,lambda i,f,n:observed.append((i,n)))
    _validate_mesh_stats(stats);assert len(observed)==c['face_count'] and len(t)==item['native_triangles'];assert sum(n for _,n in observed)==len(t)
    # Preserve native ordinal -> triangle ranges and per-triangle effective source colors.
    counts=np.array(observed,dtype=np.int64);np.savez_compressed(folder/'face-map.npz',native_face_ordinal=counts[:,0],triangle_count=counts[:,1],triangle_start=np.r_[0,np.cumsum(counts[:-1,1])],material_ids=m,palette=np.array([v or '' for v in palette]),source_step_face_ids=np.array(c['face_ids']))
    w=GlbWriter(cid,{'version':'2.0','generator':'full-source-field-review native OCCT .4mm/.25rad, no simplification'});w.add_node(cid,p/1000,t,[palette[k] for k in m],extras={'component_id':cid,'source_face_count':c['face_count'],'unsimplified':True});w.write(path)
    record.write_text(json.dumps({'source_step_sha256':digest(source),'sha256':digest(path),'stats':stats,'native_faces':len(observed),'triangles':len(t)},indent=2)+'\n');del doc,reader,p,t,m,w;gc.collect()
   method='fresh complete OCCT .4mm/.25rad; native face ordinal/range/color map'
  _validate_mesh_stats(stats);d,b=read_glb(path);count=sum(d['accessors'][p['indices']]['count']//3 for i,_,_ in scene_nodes(d) if 'mesh' in d['nodes'][i] for p in d['meshes'][d['nodes'][i]['mesh']]['primitives']);assert count==item['native_triangles']
  records.append({'id':cid,'path':str(path),'sha256':digest(path),'source_step':str(source),'source_step_sha256':digest(source),'source_face_ids':c['face_ids'],'source_faces':c['face_count'],'triangles':count,'uses':item['uses'],'stats':stats,'method':method});paths[cid]=path;print('verified',cid,count,flush=True)
 # Concatenate original GLB payloads; only remap indices and add hierarchy-derived occurrence matrices.
 combined={'asset':{'version':'2.0','generator':'full-source-field-review; unsimplified original STEP-derived native tessellations'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'materials':[],'accessors':[],'bufferViews':[]};binary=bytearray();roots={}
 for cid,path in paths.items():
  d,b=read_glb(path);off={k:len(combined[k]) for k in ('nodes','meshes','materials','accessors','bufferViews')};bo=len(binary);binary.extend(b);binary.extend(b'\0'*(-len(binary)%4))
  for v in d['bufferViews']:
   v=copy.deepcopy(v);v['byteOffset']=v.get('byteOffset',0)+bo;combined['bufferViews'].append(v)
  for a in d['accessors']:
   a=copy.deepcopy(a);a['bufferView']+=off['bufferViews'];combined['accessors'].append(a)
  combined['materials'].extend(copy.deepcopy(d['materials']))
  for mesh in copy.deepcopy(d['meshes']):
   for p in mesh['primitives']:
    p['indices']+=off['accessors'];p['material']+=off['materials'];p['attributes']={k:v+off['accessors'] for k,v in p['attributes'].items()}
   combined['meshes'].append(mesh)
  for n in copy.deepcopy(d['nodes']):
   if 'mesh' in n:n['mesh']+=off['meshes']
   if 'children' in n:n['children']=[v+off['nodes'] for v in n['children']]
   combined['nodes'].append(n)
  roots[cid]=[i+off['nodes'] for i in d['scenes'][d.get('scene',0)]['nodes']]
 # Each occurrence needs distinct nodes, sharing immutable meshes/accessors/materials.
 prototype_nodes=combined['nodes'];combined['nodes']=[]
 for occurrence in plan['nodes']:
  cid=occurrence['component_id']
  if not cid:continue
  def clone(i):
   n=copy.deepcopy(prototype_nodes[i]);children=n.pop('children',[]);index=len(combined['nodes']);combined['nodes'].append(n)
   if children:n['children']=[clone(c) for c in children]
   return index
  child=[clone(i) for i in roots[cid]];matrix=np.array(occurrence['world_matrix_mm']);matrix[:3,3]/=1000
  index=len(combined['nodes']);combined['nodes'].append({'name':occurrence['id'],'children':child,'matrix':matrix.flatten(order='F').tolist(),'extras':{'component_id':cid,'source_face_count':byid[cid]['face_count']}});combined['scenes'][0]['nodes'].append(index)
 combined['buffers']=[{'byteLength':len(binary)}];target=OUT/'original-full-native.glb';write_glb(target,combined,bytes(binary))
 report={'source_sha256':h['source_sha256'],'hierarchy_sha256':digest(hpath),'hierarchy_field_step_sha256':digest(hpath.with_name('field.step')),'hierarchy_geometry_record_sha256':h['geometry_record_sha256'],'original_source_face_ids_exactly_partitioned':True,'summary':plan['summary'],'components':records,'placed_triangles':sum(c['triangles']*c['uses'] for c in records),'reference':str(target),'sha256':digest(target),'tessellation':{'linear_mm':.4,'angular_rad':.25,'simplification':False,'omissions':False},'mapping_limit':'Exact original STEP face sets retained per component. Native face ordinals are not asserted to equal STEP face IDs. Cached equipment additionally retains shell-to-triangle mappings; fresh terrain/Base retains native face ordinal-to-triangle ranges and colors.','coordinate_frame':'source arena Z up metres; hierarchy world placements applied once','producer_sha256':digest(Path(__file__))};(OUT/'source.json').write_text(json.dumps(report,indent=2)+'\n');print('COMPLETE',report['placed_triangles'],flush=True)
if __name__=='__main__':main()
