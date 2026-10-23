# SPDX-License-Identifier: MIT OR Apache-2.0
"""Matched source-framed before/after views of the Tech Core strip repair."""
import sys,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'));sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review'))
import numpy as np
from PIL import Image
from gltf_scene import read_glb
from cad_component_detail import connected_pieces
from trace import r,projected,pick,OUT

def main():
 mapping=json.loads((ROOT/'out/rmuc2027-protected-source-reference/technology-core/tool-head/mapping.json').read_text());placement=json.loads((ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json').read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0];sp=ROOT/mapping['reference_glb'];doc,_=read_glb(sp);source=r.load(sp,placement,wrapper=mapping['runtime']['component_rest_matrix_m']);unitnode=next(i for i,n in enumerate(doc['nodes'])if n.get('extras',{}).get('source_unit_id')==1505813)
 ws=(source[4]==unitnode)&np.all(source[1]==1,axis=1);ids=np.flatnonzero(ws);white=source[0][ws];labels=connected_pieces(white.reshape(-1,3),np.arange(white.size//3).reshape(-1,3));ti=pick(projected(source[0],source[0]),220,355);label=int(labels[np.flatnonzero(ids==ti)[0]]);bar=white[labels==label];print('Selected actual bar triangles',len(bar),flush=True)
 stages={'source':source};paths={'source':str(sp),'before':str(ROOT/'out/rmuc2027-visual-fidelity-review/protected-1mm/tech-core.glb'),'bars':str(OUT/'bars-restored.glb')}
 profile=OUT/'source-profile.glb'
 if profile.exists():paths['source-profile']=str(profile)
 combined=OUT/'combined.glb'
 if combined.exists():paths['combined']=str(combined)
 for stage,path in paths.items():
  if stage=='source-profile':stages[stage]=r.load(Path(path),placement,wrapper=mapping['runtime']['component_rest_matrix_m'])
  elif stage!='source':stages[stage]=r.load(Path(path),placement,r.select(Path(path),'tech-core','technology-core/tool-head'))
 cameras={'face':source[0],'grill':white,'bar':bar}
 views=[('oblique',(1,.5,1)),('reverse',(-1,.5,-1)),('front',(0,.000001,1)),('top',(0,1,.000001)),('side',(1,.000001,0))]
 raster=r.module('bar_raster','benchmarks/2026-10-17-base-panel-textures/review.py').raster;report={'stages':paths,'views':[],'scope':'Source-framed 1200px flat source-color geometry diagnostics. The white strip is non-emissive in Tech Core runtime material. Not Bevy PBR.'}
 with tempfile.TemporaryDirectory()as temp:
  tmp=Path(temp);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
  for subject,camera in cameras.items():
   for view,dir in views:
    images={}
    for stage,data in stages.items():
     folder=OUT/'renders'/subject;folder.mkdir(parents=True,exist_ok=True);path=folder/f'{stage}-{view}.webp';im=raster(data,camera,dir,helper,tmp,tmp/'frame.png');Image.fromarray(im).save(path,lossless=True);images[stage]=im;report['views'].append({'subject':subject,'stage':stage,'view':view,'image':str(path),'triangles':len(data[0]),'metrics':None if stage=='source'else r.metrics(images['source'],im)})
   print('Rendered',subject,flush=True)
 (OUT/'review.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
