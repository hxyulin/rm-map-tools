# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render isolated original-CAD work selections for manual component review."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from validate_parts import read_part
from mesh_parts import tessellate
records=json.load(open('local-assets/cad-audit/non-base/work-exports.json'))
fig=plt.figure(figsize=(15,13),facecolor='#f5f6f8')
fig.suptitle('Non-base work selections — original mechanical bodies',color='#182334',fontsize=19,y=.98)
fig.text(.5,.95,'Preview tessellation: 0.4 mm / 0.25 rad. Shared surface-model shells are excluded; these are not complete assemblies.',ha='center',color='#536072',fontsize=10)
report=[]
for row,entry in enumerate(records):
 doc,reader,error=read_part(str(Path(entry['work_directory'])/'source.step'))
 if error:raise ValueError(error)
 stats={};p,t,tc,keys=tessellate(doc,.4,.25,stats=stats)
 if stats.get('unmeshed_faces'):raise ValueError(stats)
 triangles=p[t]
 rgb=np.array([[float(v) for v in k.split(',')] if k else [.62,.64,.68] for k in keys])
 normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
 light=np.array([.3,-.5,.8]);light/=np.linalg.norm(light)
 brightness=.4+.6*np.abs(normals@light)
 colors=np.clip(rgb[tc]*brightness[:,None],0,1)
 lo,hi=p.min(axis=0),p.max(axis=0);center=(lo+hi)/2;half=max((hi-lo)/2)*1.07
 for col,azim in enumerate([35,125,215]):
  ax=fig.add_subplot(3,3,row*3+col+1,projection='3d',proj_type='ortho',computed_zorder=True)
  ax.set_facecolor('#f5f6f8');ax.add_collection3d(Poly3DCollection(triangles,facecolors=colors,edgecolors='none',rasterized=True))
  ax.set_xlim(center[0]-half,center[0]+half);ax.set_ylim(center[1]-half,center[1]+half);ax.set_zlim(center[2]-half,center[2]+half)
  ax.set_box_aspect([1,1,1]);ax.view_init(elev=20,azim=azim);ax.set_axis_off()
  label=entry['selector'].replace('outpost/rotor/module-0','Outpost rotor module 0').replace('outpost/fixed/lower-cluster','Outpost lower cluster').replace('rune/banks/bank-a/arm-0','Rune bank A — arm candidate 0')
  ax.set_title(label+'\n'+str(entry['body_definitions'])+' bodies · '+str(entry['native_faces'])+' source faces',color='#182334',fontsize=10,pad=0)
 report.append({'selector':entry['selector'],'preview_triangles':len(t),'tessellation_stats':stats})
 del doc,reader
fig.subplots_adjust(left=.01,right=.99,bottom=.015,top=.91,hspace=.03,wspace=.005)
fig.savefig('local-assets/cad-audit/non-base/work-items.png',dpi=135,facecolor=fig.get_facecolor())
Path('local-assets/cad-audit/non-base/preview-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
