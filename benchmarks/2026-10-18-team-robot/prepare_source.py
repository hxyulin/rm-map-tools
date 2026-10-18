# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Prepare checksum-pinned source-derived robot mesh tiers; original CAD terms apply."""
import sys,json,hashlib,time
from pathlib import Path
import numpy as np
import argparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from validate_parts import read_part,analyse
from mesh_parts import tessellate
from referee_hardware import solid_membership,assemble
from simplify_package import simplify_mesh
from export_field_package import GlbWriter
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sources',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--low-only',action='store_true',help='Use the reference tessellation for centering, without exporting its large review mesh.')
parser.add_argument('--recipe',type=Path,default=Path(__file__).with_name('recipe.json'))
parser.add_argument('--split-shells',action='store_true',help='Separate non-solid faces by audited source leaf; requires --hierarchy.')
parser.add_argument('--hierarchy',type=Path)
parser.add_argument('source_id', help='Source key in the checksum-pinned recipe.')
args=parser.parse_args()
recipe=json.loads(args.recipe.read_text());binding=recipe['sources'][args.source_id]
name=binding['source_model_id'];source=args.sources/(name+'.step');out=args.out/(name+'-pilot')
if out.exists():raise ValueError('output directory must be new')
source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()
if source_sha256!=binding['cad_sha256']:raise ValueError('STEP checksum mismatch')
out.mkdir(parents=True)
article={'url':binding['original_article_url'],'id':binding['source_article'].rsplit('/',1)[1]};credit=binding['credit']
start=time.monotonic();doc,reader,error=read_part(str(source));assert error is None,error
stats=analyse(doc);print(name,stats,flush=True)
owners=solid_membership(doc);outputs={};reference=None;center=None
leaf_paths={}
if args.split_shells:
 if args.hierarchy is None:raise ValueError('--split-shells requires a face-membership hierarchy')
 rows=json.loads(args.hierarchy.read_text())
 for leaf,row in enumerate(rows,1):
  if 'children' in row:continue
  if 'native_faces' not in row:raise ValueError('audit hierarchy with --faces first')
  for face in row['native_faces']:
   if face not in owners:owners[face]=-leaf;leaf_paths[-leaf]=row['path']
for variant,linear,angular in [('source',.25,.3),('low',1.,.8)]:
 owner=[];p,t,c,palette=tessellate(doc,linear,angular,face_observer=lambda i,f,n:owner.extend([owners.get(i,0)]*n));owner=np.array(owner)
 if center is None:center=(p.min(0)+p.max(0))/2
 if args.low_only and variant=='source':
  outputs[variant]={'triangles':len(t),'exported':False,'linear_mm':linear,'angular_rad':angular}
  continue
 parts=[];counts=[]
 for sid in np.unique(owner):
  entries=[]
  for color in np.unique(c[owner==sid]):
   selected=t[(owner==sid)&(c==color)];used,inv=np.unique(selected,return_inverse=True);q=p[used];faces=inv.reshape(-1,3)
   if variant=='low':q,faces,err=simplify_mesh(q,faces,1.,lock_borders=False)
   entries.append((q,faces,[int(color)]*len(faces)))
  q,faces,colors=assemble(entries);parts.append((q,faces,colors));counts.append((int(sid),len(faces)))
 p,t,c=assemble(parts)
 np.savez_compressed(out/(variant+'.npz'),positions_mm=p-center,triangles=t,material_ids=c,palette=np.array([v or '' for v in palette]))
 writer=GlbWriter(name,{'version':'2.0','copyright':credit+'; original CAD terms apply. Local visual experiment, not an official model.'})
 for (q,faces,colors),(sid,count) in zip(parts,counts):
  writer.add_node('source-solid-'+str(sid),(q-center)/1000,faces,[palette[k] for k in colors],extras={'source_sha256':source_sha256,'native_solid_index':max(0,sid),**({'source_leaf_path':leaf_paths.get(sid)} if args.split_shells else {}),'source_article':article['url'],'credit':credit,'semantic_role':'unclassified','collision_eligible':False,'articulation_bound':False})
 writer.write(out/(variant+'.glb'))
 outputs[variant]={'triangles':len(t),'bytes':(out/(variant+'.glb')).stat().st_size,'mesh_groups':len(counts),'native_solid_groups':sum(sid>0 for sid,count in counts),'source_shell_groups':sum(sid<0 for sid,count in counts),'linear_mm':linear,'angular_rad':angular,'decimation_error_mm':1. if variant=='low' else None}
 print(variant,outputs[variant],flush=True)
report={'source':source.name,'sha256':source_sha256,'author_credit':credit,'article_url':article['url'],'archive_url':'https://bbs.herkules.dev/articles/'+article['id'],'source_stats':stats,'outputs':outputs,'elapsed_seconds':time.monotonic()-start,'policy':'Local visual review only. Source-solid and material boundaries retained. No semantic removal, hole filling, convex hulls, inferred physics or articulated binding. Meshoptimizer metric is not a certified deviation bound. CAD rights remain with original authors; intended use is noncommercial RoboMaster team exchange.'}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
notice=(f"# Source-derived robot candidate\n\n{credit}\n\n"
        f"Source article: {binding['source_article']}\nOriginal article: {binding['original_article_url']}\n\n"
        f"Source STEP SHA-256: {binding['cad_sha256']}\n\n"
        + binding.get('terms', 'Original CAD rights and source terms remain with the authors; noncommercial RoboMaster team exchange only.')
        + '\n\nGeometry is simplified for visual review, retaining native solid/material boundaries. '
        'No robot compliance, source joint bindings, mass/inertia or collision behavior is inferred. '
        'Third-party geometry is not relicensed under the simulator/exporter software license.\n')
(out/'CAD-NOTICE.md').write_text(notice)
print('done',flush=True)
