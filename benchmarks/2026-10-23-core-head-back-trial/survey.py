"""Read-only head ownership survey and source-colored matched inspection views."""
import importlib.util,json,sys,tempfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('head_arm_helpers',ROOT/'benchmarks/2026-10-23-core-arm-proxies/build.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review'))
f=p.module('head_reference_renderer','benchmarks/2026-10-23-visual-fidelity-review/render.py')
import collision_review_render as raster
from gltf_scene import local_matrix
OUT=ROOT/'out/rmuc2027-core-head-back-trial'

def main():
    OUT.mkdir(exist_ok=True);ref=json.loads(p.scan.REF.read_text());source=Path(ref['roles']['collision']['assets']['tech-core']['path'])
    d,c,n=p.scan.load_nodes(source);head={i for i in n if c[i]=='technology-core/tool-head'}
    manifest=ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json'
    placement=json.loads(manifest.read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0]
    ids=[1266,1268,1270,1272,1284,1296,1297,1501,1662,1668,1254,1255,1262,1263,287,111]
    sheet=Image.new('RGB',(1600,1600),'white');draw=ImageDraw.Draw(sheet);views=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        for k,ni in enumerate(ids):
            data=f.load(source,placement,{ni});image=Image.fromarray(raster.raster(data,data[0],(1,.65,1),helper,tmp));target=OUT/f'node-{ni}.webp';image.save(target,lossless=True)
            x=(k%4)*400;y=(k//4)*400;sheet.paste(image.resize((390,355)),(x,y+35));draw.text((x+8,y+9),f'node {ni}: {len(n[ni])} triangles',fill='black')
        sheet.save(OUT/'head-parts.jpg')
        data=f.load(source,placement,head);matrix=local_matrix(dict(translation=placement['translation_m'],rotation=placement['rotation_xyzw']))
        frame=matrix[:3,:3].T@f.FRAME.T
        for name,di in [('front',(0,-.2,-1)),('back',(0,-.2,1)),('left',(1,-.2,.3)),('right',(-1,-.2,.3))]:
            direction=np.array(di)@frame;target=OUT/f'head-{name}-installed.webp'
            Image.fromarray(raster.raster(data,data[0],direction,helper,tmp)).save(target,lossless=True)
            views.append(dict(camera=name,direction=direction.tolist(),path=str(target),sha256=p.scan.digest(target)))
    owners=[dict(node=i,name=d['nodes'][i]['name'],triangles=len(n[i]),bounds_mm=[n[i].min((0,1)).tolist(),n[i].max((0,1)).tolist()],
        material_ids=[pr['material']for pr in d['meshes'][d['nodes'][i]['mesh']]['primitives']])for i in sorted(head)]
    result=dict(source=str(source),source_sha256=p.scan.digest(source),head_triangles=sum(len(n[i])for i in head),owners=owners,views=views,
        source_name='Pinned installed Core collision; front camera looks from negative source Z; back from positive source Z.',placement=placement)
    (OUT/'survey.json').write_text(json.dumps(result,indent=2)+'\n');print('Head survey:',len(head),'owners,',result['head_triangles'],'triangles.')

if __name__=='__main__':main()
