# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Trials limited to analytic native cylinder supports, preserving patch boundaries."""
from experiment import *
def run():
 report=json.load(open(ROOT/'out/rmuc2027-runtime-opportunities/refined.json'));supports=json.load(open(ROOT/'out/rmuc2027-curve-trial/native-supports.json'));results=[]
 for role in ['visual','collision']:
  source=ROOT.parent/'rm-simulator/field-2027/equipment'/('tech-core'+('-collision' if role=='collision' else '')+'.glb');row=report['assets']['tech-core/'+role];baseline=ROOT/'out/rmuc2027-runtime-opportunities'/row['output'];sd,sb=read_glb(source);bd,bb=read_glb(baseline);scopes={};nodes={}
  for i,w,par in scene_nodes(sd):
   n=sd['nodes'][i];e=n.get('extras',{});cid=e.get('component_id') or e.get('composition_occurrence',{}).get('component_id') or scopes.get(par);scopes[i]=cid;shell=e.get('native_shell_index',e.get('source_native_shell_index'))
   if shell is not None and 'mesh' in n:nodes[cid,shell]=i
  for cid in ['technology-core/arm-and-shared','technology-core/pedestal-and-shoulder']:
   seen=set();group=0 if 'arm-and' in cid else 1;cg=geometry(bd,bb,1672+group)
   for sup in supports[cid]['cylinders']:
    shell=sup['shell'];key=(shell,round(sup['radius'],2),tuple(np.round(sup['axis'],3)))
    if key in seen or (cid,shell) not in nodes:continue
    seen.add(key)
    # Native shell 1 and larger arm housings; exclude every gripper owner.
    if cid.endswith('arm-and-shared') and shell not in [1,13,18,22,26,33]:continue
    sg=geometry(sd,sb,nodes[cid,shell]);axis=np.array(sup['axis']);anchor=np.array(sup['anchor']);r=sup['radius'];a,u,v=frame(axis)
    def mask(g):
     x=g-anchor;rad=np.hypot(x@u,x@v);ang=np.unwrap(np.arctan2(x@v,x@u),axis=1)
     return (abs(rad-r).max(1)<.05)&(np.ptp(x@a,axis=1)>.005)&(np.ptp(ang,axis=1)<.6)
    sm=mask(sg);cm=mask(cg)
    if sm.sum()<8 or cm.sum()<8:continue
    ids=np.flatnonzero(cm);dd=distances(surface_samples(cg.reshape(-1,3),np.arange(len(cg)*3).reshape(-1,3))[ids].reshape(-1,3),sg.reshape(-1,3),np.arange(len(sg)*3).reshape(-1,3)).reshape(-1,7).max(1);cm[ids[dd>1.2]]=False
    if cm.sum()<8:continue
    rec={'role':role,'component':cid,'shell':shell,'source_node':nodes[cid,shell],'baseline_node':1672+group,'native_support':sup,'source_patch_triangles':int(sm.sum()),'baseline_patch_triangles':int(cm.sum()),'source':str(source.resolve()),'source_sha256':digest(source),'baseline':str(baseline.resolve()),'baseline_sha256':digest(baseline),'trials':[]};results.append(rec)
    for sectors in [1,8,16,24]:
     tr={'sectors':sectors};rec['trials'].append(tr)
     try:
      q,meta=retriangulate(cg[cm],axis=axis,anchor=anchor,radius=r,sectors=sectors);tr.update(meta);tr['triangles']=len(q);tr['saving_per_scene']=int(cm.sum()-len(q));tr['boundary']=boundary_error(cg[cm],q)
      if tr['boundary']['maximum_sampled_boundary_mm']>.01:tr['rejected']='patch boundary not preserved';continue
      if len(q)>=cm.sum():tr['rejected']='not cheaper';continue
      out=np.concatenate([cg[~cm],q]);forward=distances(samples(sg[sm],1),out.reshape(-1,3),np.arange(len(out)*3).reshape(-1,3));reverse=distances(samples(q,1),sg.reshape(-1,3),np.arange(len(sg)*3).reshape(-1,3));tr['source_to_output_mm']=float(forward.max());tr['output_to_source_mm']=float(reverse.max());tr['max_mm']=float(max(forward.max(),reverse.max()));tr['accepted_1mm']=tr['max_mm']<=1.2;tr['accepted_4mm_exception']=tr['max_mm']<=4;tr['samples']=len(forward)+len(reverse)
     except Exception as e:tr['rejected']=str(e)
    print(role,cid,shell,round(r,2),sm.sum(),cm.sum(),[(t.get('triangles'),round(t.get('max_mm',999),2),t.get('rejected')) for t in rec['trials']],flush=True)
 (ROOT/'out/rmuc2027-curve-trial/pure-cylinder-experiments.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':run()
