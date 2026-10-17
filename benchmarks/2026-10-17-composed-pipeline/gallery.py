#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build the complete-field/equipment review and separate Energy profile trials."""
import argparse, json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args(); out=a.out.resolve()
    report=json.loads((out/'review.json').read_bytes()); rows=[]
    names={'field':'Complete field','outpost':'Outpost','rune':'Rune','technology-core':'Tech Core','resource-area':'Resource area','dart-station':'Dart station + enclosure','energy-unit':'Energy Unit · composed pipeline'}
    for group in report['groups']:
        cid=group['group']; rows.append({'id':cid,'label':names[cid],'before':group['reference_triangles'],'after':group['candidate_triangles'],'count':2,'column':1,'beforeLabel':'Previous approved composition','afterLabel':'Composed candidate','views':[r['view'] for r in group['views']],'paths':{r['view']:str(out/'review'/cid/(r['view']+'.webp')) for r in group['views']},'note':f"Maximum checked silhouette change: {group['maximum_foreground_difference']*100:.3f}%. Source poses, colors and embedded artwork; static visual inspection."})
    energy=out.parent/'rmuc2027-energy-profile'; trials=json.loads((energy/'summary.json').read_bytes()); review=json.loads((energy/'review.json').read_bytes())
    for i,candidate in enumerate(trials['candidates']):
        name=candidate['name']; views=[v['view'] for v in review['views'] if v['stage']==name]
        rows.append({'id':name,'label':'Energy Unit · '+str(candidate['angular_segments'])+'-segment trial','before':candidate['composed_reference_triangles'],'after':candidate['triangles'],'count':3,'column':i+1,'beforeLabel':'Composed Energy Unit','afterLabel':'Separate profile trial · unpromoted','views':views,'paths':{v:str(energy/'review'/(v+'.webp')) for v in views},'note':'Not included in the full field. '+('Count regression. ' if candidate['placed_saving']<0 else '')+'Deep socket retained, but underside occlusion/color slivers still differ. A single radial envelope does not preserve all undercuts.'})
    html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px var(--font-sans,system-ui);color:var(--foreground,#222);margin:0}p{line-height:1.45;margin:10px 0}.controls{display:flex;gap:12px;flex-wrap:wrap}label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted-foreground,#666)}select{font:14px var(--font-sans,system-ui);padding:7px;max-width:100%;color:var(--foreground,#222);background:var(--background,#fff);border:1px solid var(--border,#bbb);border-radius:6px}.controls label:first-child{flex:2;min-width:210px}.controls label:last-child{flex:1;min-width:110px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.caption{font-size:12px;line-height:1.3;min-height:32px;color:var(--muted-foreground,#666)}.image{position:relative;aspect-ratio:1;overflow:hidden;background:#c2d1df}.image img{height:100%;position:absolute;max-width:none}#stats{font-variant-numeric:tabular-nums;font-size:15px;font-weight:600}#note{font-size:12px;color:var(--muted-foreground,#666)}.note{font-size:12px;color:var(--muted-foreground,#666)}
</style></head><body><div class="controls"><label>Model / experiment<select id="model"></select></label><label>Camera<select id="camera"></select></label></div><p id="stats"></p><div class="pair"><div><div class="caption" id="beforeLabel"></div><div class="image"><img id="before" alt="Reference"></div></div><div><div class="caption" id="afterLabel"></div><div class="image"><img id="after" alt="Candidate"></div></div></div><p id="note"></p><p class="note">Full-field count includes all 171 placements. Instancing shares storage; it does not subtract placed triangles. Collision and installed runtime assets are unchanged.</p><script>
const rows=__DATA__;const model=document.getElementById('model'),camera=document.getElementById('camera');let current;
for(const row of rows){let option=new Option(row.label,row.id);model.add(option)}
function frame(){const path=current.paths[camera.value];for(const id of ['before','after']){const image=document.getElementById(id);image.src=path;image.style.width=(100*current.count)+'%';image.style.left=(id==='before'?0:-100*current.column)+'%'}}
function update(){current=rows.find(r=>r.id===model.value);const previous=camera.value;camera.replaceChildren();for(const v of current.views)camera.add(new Option(v,v));if(current.views.includes(previous))camera.value=previous;const saving=current.before-current.after;document.getElementById('stats').textContent=current.before.toLocaleString()+' → '+current.after.toLocaleString()+' triangles · '+(saving>=0?'−':'+')+Math.abs(saving/current.before*100).toFixed(1)+'%';document.getElementById('beforeLabel').textContent=current.beforeLabel;document.getElementById('afterLabel').textContent=current.afterLabel;document.getElementById('note').textContent=current.note;frame()}
model.addEventListener('change',update);camera.addEventListener('change',frame);update();console.log('Review models:',rows.length);
</script></body></html>'''.replace('__DATA__',json.dumps(rows))
    (out/'gallery.html').write_text(html)

if __name__=='__main__':main()
