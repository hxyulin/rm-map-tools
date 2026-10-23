# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Pin curve rejection evidence, verify all inputs, and recount live geometry."""
import sys,json,hashlib,subprocess,platform
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,accessor,scene_nodes
from simplify_package import scene_triangles
OUT=ROOT/'out/rmuc2027-curve-trial'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def count(path):
 d,b=read_glb(path);live={d['nodes'][i]['mesh'] for i,w,par in scene_nodes(d) if 'mesh' in d['nodes'][i]}
 return {'scene_triangles':scene_triangles(d),'stored_live_triangles':sum(len(accessor(d,b,p['indices']))//3 for i in live for p in d['meshes'][i]['primitives']),'bytes':path.stat().st_size,'nodes':len(d['nodes'])}
def main():
 ref=json.load(open(ROOT/'out/rmuc2027-runtime-opportunities/refined.json'));sources={};placements={};pkg=ROOT.parent/'rm-simulator/field-2027'
 for relative in ['manifest.json','equipment/manifest.json']:
  path=pkg/relative
  for name,a in json.load(open(path))['assets'].items():
   for role in ['visual','collision']:sources[name+'/'+role]=(path.parent/a[role]).resolve();placements[name+'/'+role]=max(1,len(a['placements_in_source_arena_frame']))
 files={}
 for name,row in ref['assets'].items():
  source=sources[name];baseline=(ROOT/'out/rmuc2027-runtime-opportunities'/row['output']).resolve();assert digest(source)==row['source_sha256'];assert digest(baseline)==row['sha256'];sc=count(source);bc=count(baseline);assert bc['scene_triangles']==row['after'];copies=placements[name]
  files[name]={'source_path':str(source),'source_sha256':digest(source),'source':{**sc,'placed_triangles':sc['scene_triangles']*copies},'accepted1mm_path':str(baseline),'accepted1mm_sha256':digest(baseline),'accepted1mm':{**bc,'placed_triangles':bc['scene_triangles']*copies},'external_placements':copies,'output_path':None,'output_sha256':None,'decision':'retain accepted1mm; no qualifying curve candidate','retained_path':str(baseline),'retained_sha256':digest(baseline),'output_placed_triangles':bc['scene_triangles']*copies,'placed_saving':0}
 experiments={n:json.load(open(OUT/(n+'.json'))) for n in ['tech-experiments','pure-cylinder-experiments','energy-experiments']};trials=[t for rows in experiments.values() for r in rows for t in r.get('trials',[])];assert not any(t.get('accepted_1mm') or t.get('accepted_4mm_exception') for t in trials)
 reasons=Counter()
 for t in trials:
  reasons[t.get('rejected') or ('exceeds 4 mm sampled distance' if t.get('max_mm',0)>4 else 'unclassified')]+=1
 result=subprocess.run([str(ROOT/'ocpenv/bin/python'),'-m','unittest','discover','-s',str(Path(__file__).parent),'-p','test_curve.py'],capture_output=True,text=True,check=True)
 tests={'command':'ocpenv/bin/python -m unittest discover -s benchmarks/2026-10-23-curve-trial -p test_curve.py','returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr};(OUT/'tests.json').write_text(json.dumps(tests,indent=2)+'\n')
 totals={role:{'source_placed_triangles':sum(x['source']['placed_triangles'] for k,x in files.items() if k.endswith('/'+role)),'accepted1mm_placed_triangles':sum(x['accepted1mm']['placed_triangles'] for k,x in files.items() if k.endswith('/'+role)),'retained_placed_triangles':sum(x['output_placed_triangles'] for k,x in files.items() if k.endswith('/'+role)),'placed_saving':0,'stored_live_triangles':sum(x['accepted1mm']['stored_live_triangles'] for k,x in files.items() if k.endswith('/'+role))} for role in ['visual','collision']}
 producers={str(p.resolve()):digest(p) for p in Path(__file__).parent.glob('*.py')}
 native=json.load(open(OUT/'native-supports.json'))
 for entry in native.values():assert digest(entry['path'])==entry['sha256']
 ledger={'schema_version':1,'ledger_path':str((OUT/'ledger.json').resolve()),'result':'rejected; no candidate GLB exported','source_authority':'Full original installed per-file geometry, bound native source STEP cylinder axes and shell IDs. Accepted1mm supplies the protected patch integration boundary; it is not the original shape authority. No compact omission.','policy':{'nominal_mm':1,'nominal_sample_guard_mm':1.2,'localized_rounded_housing_exception_mm':4,'boundary_sample_guard_mm':.01,'sampling':'28 samples per source/output triangle: subdivide once, seven deterministic samples per subtriangle. Boundary endpoint/midpoint samples, both directions. Finite samples only; not continuous Hausdorff or clearance proof.','protected':'No edits to chromatic, emissive, textured/UV or optical arrays; no edits to gripper. No convex hull. No cross-component/part/joint merge. Energy chromatic diagnostic collider retained.','losses_tested':'Angular faceting and flattening intermediate axial bevel/profile rings on structural curved patches. Boundary failures and undercuts reject; manufacturing compact detail deletion excluded.'},'totals':totals,'files':files,'trial_count':len(trials),'trial_rejections':dict(reasons),'experiments':experiments,'native_supports':native,'producer_sha256':producers,'tests':tests,'input_and_baseline_hashes_rechecked':True,'geometry_outputs':[],'runtime_installation':False,'runtime_timing':None,'environment':{'python':platform.python_version()}}
 (OUT/'ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
 summary={k:ledger[k] for k in ['result','totals','trial_count','trial_rejections','producer_sha256']};summary['full_ledger_path']=str((OUT/'ledger.json').resolve());summary['full_ledger_sha256']=digest(OUT/'ledger.json');summary['inputs']={k:{x:v for x,v in r.items() if x in ['source_path','source_sha256','accepted1mm_path','accepted1mm_sha256','placed_saving','output_path']} for k,r in files.items()};summary['tests_passed']=4
 (Path(__file__).parent/'results.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ['result','totals','trial_count','trial_rejections']},indent=2))
if __name__=='__main__':main()
