# SPDX-License-Identifier: MIT OR Apache-2.0
"""Matched whole, arm and tool views of manually selected Tech Core trials."""
import json
from pathlib import Path
import subprocess
import tempfile
from audit import module, OUT, ROOT, raster
import numpy as np
from PIL import Image, ImageDraw


def main():
    loader=module('load_runtime','benchmarks/2026-10-23-runtime-opportunities/render.py')
    trial=json.loads((OUT/'ledger.json').read_text())['trials']
    placement=json.loads((ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json').read_text())['assets']['tech-core']['placements_in_source_arena_frame'][:1]
    levels=[]
    for role in ('visual','collision'):
        row=next(r for r in trial if r['role']==role)
        levels.append({'id':role+'-baseline','role':role,'label':'Reviewed detail baseline','baseline':True,'path':row['source'],'triangles':row['before_per_core']})
    labels={'vents':'Restored baseline','housings':'Coarse arm housings (review)','combined':'Housings only; top restored'}
    for row in trial:
        levels.append({'id':row['role']+'-'+row['policy'],'role':row['role'],'label':labels[row['policy']],
                       'path':row['output'],'triangles':row['after_per_core']})
    stages={}
    for level in levels:
        stages[level['id']]=loader.load_stage([('tech-core',Path(level['path']),placement)])[0]
    reference,owners=loader.load_stage([('tech-core',Path(levels[0]['path']),placement)])
    groups={'whole':np.ones(len(reference[0]),bool)}
    for group,prefix in [('arm','technology-core/arm'),('tool','technology-core/tool'),('pedestal','technology-core/pedestal')]:
        groups[group]=np.isin(reference[4],[v['index'] for v in owners.values() if v['component_id'].startswith(prefix)])
    report={'levels':levels,'views':[],'scope':'Source-color diagnostic renders at rest, not runtime PBR or articulated collision approval.'}
    directions=[('oblique',(1,.5,1)),('reverse',(-1,.5,-1)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('side',(1,.000001,0)),('top',(0,1,.000001)),('bottom',(0,-1,.000001))]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster'
        subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for group,mask in groups.items():
            camera=reference[0][mask]
            for level in levels:
                stage=stages[level['id']]
                if group=='whole':d=stage
                else:
                    # Original component ownership and traversal are preserved.
                    owner_ids=np.unique(reference[4][mask]);select=np.isin(stage[4],owner_ids)
                    d=tuple(a[select]for a in stage[:5])+(stage[5],)
                for name,view in directions:
                    path=OUT/'renders'/f'{group}-{level["id"]}-{name}.webp';path.parent.mkdir(exist_ok=True)
                    image=raster(d,camera,view,helper,tmp,tmp/'frame.png');Image.fromarray(image).save(path,lossless=True)
                    report['views'].append({'group':group,'stage':level['id'],'view':name,'image':str(path),'triangles':len(d[0])})
            print('rendered',group,flush=True)
    (OUT/'review.json').write_text(json.dumps(report,indent=2)+'\n')
    # Full-size assets remain available; this sheet is only a quick human scan.
    canvas=Image.new('RGB',(1800,1500),'#171717');draw=ImageDraw.Draw(canvas)
    for y,(group,view) in enumerate([('whole','oblique'),('tool','front'),('arm','reverse')]):
        for x,stage in enumerate(['visual-baseline','visual-vents','visual-combined']):
            row=next(r for r in report['views'] if (r['group'],r['view'],r['stage'])==(group,view,stage))
            canvas.paste(Image.open(row['image']).resize((490,450)),(x*600,y*500+35));draw.text((x*600+8,y*500+8),f'{group} {stage}',fill='white')
    canvas.save(OUT/'contact-sheet.jpg')


if __name__=='__main__':main()
