from build import *

def verify(target,selected):
 d,b=read_glb(source);a,ab=read_glb(target);unchanged=0
 assert len(d['nodes'])==len(a['nodes']);assert d['materials']==a['materials'];assert d['scenes']==a['scenes']
 for ni,(n,nn)in enumerate(zip(d['nodes'],a['nodes'])):
  assert {k:v for k,v in n.items()if k!='mesh'}=={k:v for k,v in nn.items()if k!='mesh'}
  if 'mesh'not in n:continue
  pp=d['meshes'][n['mesh']]['primitives'];qq=a['meshes'][nn['mesh']]['primitives']
  if ni in selected:
   for pr in qq:
    p=accessor(a,ab,pr['attributes']['POSITION']);t=accessor(a,ab,pr['indices']).reshape(-1,3);assert np.isfinite(p).all();assert t.min()>=0 and t.max()<len(p)
    g=p[t];assert np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-14
   continue
  assert len(pp)==len(qq)
  for x,y in zip(pp,qq):
   assert {k:v for k,v in x.items()if k not in ['attributes','indices']}=={k:v for k,v in y.items()if k not in ['attributes','indices']}
   assert set(x['attributes'])==set(y['attributes'])
   for key in x['attributes']:
    aa=accessor(d,b,x['attributes'][key]);bb=accessor(a,ab,y['attributes'][key]);assert aa.dtype==bb.dtype and aa.shape==bb.shape and aa.tobytes()==bb.tobytes()
   assert accessor(d,b,x['indices']).tobytes()==accessor(a,ab,y['indices']).tobytes()
  unchanged+=1
 return {'changed_nodes':selected,'unchanged_mesh_nodes_exact':unchanged,'scene_triangles':scene_triangles(a),'sha256':digest(target),'all_node_names_extras_ancestry_transforms_exact':True,'materials_scenes_exact':True}
if __name__=='__main__':
 checks={'profiles':verify(OUT/'tech-core-collision.glb',[17,1284]),'joint_envelope':verify(OUT/'joint-cylinder-comparison.glb',[22])}
 for p,h in ref['pins'].items():assert digest(Path(p))==h
 checks['installed_inputs_unchanged']=True
 (OUT/'verification.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks,indent=2))
