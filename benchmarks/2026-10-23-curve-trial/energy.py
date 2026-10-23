# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measure repeated Energy structural shoulder lofts and exact cylinders."""
from experiment import *
def run():
 source=ROOT.parent/'rm-simulator/field-2027/arena-static.glb';baseline=ROOT/'out/rmuc2027-runtime-opportunities/refined/visual-1mm/arena-static.glb';sd,sb=read_glb(source);bd,bb=read_glb(baseline);pr=sd['meshes'][sd['nodes'][660]['mesh']]['primitives'][1];p=accessor(sd,sb,pr['attributes']['POSITION']).astype(float)*1000;t=accessor(sd,sb,pr['indices']).reshape(-1,3);sg=p[t];cg=geometry(bd,bb,1218);results=[]
 configs=[('upper-rounded-housing',None),('native-cylinder-47.5',47.5),('native-cylinder-42.5',42.5),('native-cylinder-40',40),('native-cylinder-34.5',34.5),('native-cylinder-30',30)]
 for name,r in configs:
  def mask(g):
   if r is None:return side(g,[0,1,0],[0,0,0],120,150,41)
   rad=np.linalg.norm(g[:,:,[0,2]],axis=2);ang=np.unwrap(np.arctan2(g[:,:,2],g[:,:,0]),axis=1)
   return (abs(rad-r).max(1)<.05)&(np.ptp(g[:,:,1],axis=1)>.005)&(np.ptp(ang,axis=1)<.6)
  sm=mask(sg);cm=mask(cg);rec={'name':name,'source':str(source.resolve()),'source_sha256':digest(source),'baseline':str(baseline.resolve()),'baseline_sha256':digest(baseline),'source_node':660,'source_primitive':1,'baseline_node':1218,'material':18,'component':'energy-unit/unit','placed_copies':12,'axis':[0,1,0],'anchor_mm':[0,0,0],'radius_mm':47.5 if r is None else r,'source_patch_triangles':int(sm.sum()),'baseline_patch_triangles':int(cm.sum()),'trials':[]};results.append(rec)
  if sm.sum()<3 or cm.sum()<3:rec['rejected']='insufficient eligible patch';continue
  for sectors in [1,4,8,12,16,24]:
   tr={'sectors':sectors};rec['trials'].append(tr)
   try:
    q,meta=retriangulate(cg[cm],axis=[0,1,0],anchor=[0,0,0],radius=rec['radius_mm'],sectors=sectors);tr.update(meta);tr['triangles']=len(q);tr['hypothetical_placed_saving']=int((cm.sum()-len(q))*12);tr['boundary']=boundary_error(cg[cm],q)
    if tr['boundary']['maximum_sampled_boundary_mm']>.01:tr['rejected']='patch boundary not preserved'
    if len(q)>=cm.sum():tr['rejected']='not cheaper';continue
    out=np.concatenate([cg[~cm],q]);forward=distances(samples(sg[sm],1),out.reshape(-1,3),np.arange(len(out)*3).reshape(-1,3));reverse=distances(samples(q,1),sg.reshape(-1,3),np.arange(len(sg)*3).reshape(-1,3));tr['source_to_output_mm']=float(forward.max());tr['output_to_source_mm']=float(reverse.max());tr['max_mm']=float(max(forward.max(),reverse.max()));tr['accepted_1mm']=tr['max_mm']<=1.2 and not tr.get('rejected');tr['accepted_4mm_exception']=tr['max_mm']<=4 and not tr.get('rejected');tr['samples']=len(forward)+len(reverse)
   except Exception as e:tr['rejected']=str(e)
  print(name,sm.sum(),cm.sum(),[(t.get('triangles'),round(t.get('max_mm',999),2),t.get('rejected')) for t in rec['trials']],flush=True)
 results.append({'role':'collision','component':'energy-unit/unit','source':str((ROOT.parent/'rm-simulator/field-2027/arena-static-collision.glb').resolve()),'baseline':str((ROOT/'out/rmuc2027-runtime-opportunities/refined/collision-1mm/arena-static-collision.glb').resolve()),'rejected':'Installed Energy collider is an already-authored chromatic blue proxy. Strict chromatic protection excludes edits to its material/position/index arrays. No optical identity inferred from visual similarity.'})
 (ROOT/'out/rmuc2027-curve-trial/energy-experiments.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':run()
