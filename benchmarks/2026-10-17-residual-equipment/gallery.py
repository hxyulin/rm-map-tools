#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build a per-equipment and per-shell comparison gallery for steps 3 and 4."""
import argparse,json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();report=json.loads((out/'review.json').read_bytes());rows=[]
    names={'complete-field':'Complete field','complete-rune':'Complete Rune','complete-resource-area':'Complete Resource mechanism','complete-technology-core':'Complete Tech Core'}
    for entry in report['entries']:
        cid=entry['component_id'];scope=entry['scope'];name=names.get(entry['id'])
        if name is None:
            prefix='Rune hub A' if '/bank-a/' in cid else 'Rune hub B' if '/bank-b/' in cid else 'Rune support' if cid.startswith('rune/') else 'Resource mechanism' if cid.startswith('resource-') else 'Tech Core tool head'
            suffix={'shell-4':'copper plate' if cid.startswith('technology') else 'main housing','shell-29':'repeated bracket','shell-18':'inner hub frame','shell-19':'five-spoke frame','shell-1211':'cylindrical fitting'}.get(scope,scope.replace('shell-','source shell '))
            name=prefix if scope=='component' else prefix+' · '+suffix
        complete=scope=='complete';stages=['final'] if complete else ['planar','detail','final'];paths={view:str(out/entry['images']/(view+'.webp')) for view in entry['view_names']};max_foreground={stage:max(v['foreground_difference_relative_fraction'] for v in entry['views'] if v['stage']==stage) for stage in stages}
        note='Same source poses, palette and original placement. Runtime/collision unchanged.'
        if cid=='technology-core/tool-head':note+=' Copper plate uses a native projected-profile 8 mm prism, intentionally smoothing rear relief. The intermediate plate LOD was rejected for speckling.'
        if scope=='complete' and entry['id']=='complete-rune':note+=' Ten Rune arms are unchanged.'
        rows.append({'id':entry['id'],'name':name,'category':'Complete equipment' if complete else 'Rune hubs and support' if cid.startswith('rune/') else 'Resource parts' if cid.startswith('resource-') else 'Tech Core parts','counts':entry['triangles'],'stages':stages,'columns':2 if complete else 4,'views':entry['view_names'],'paths':paths,'maximum_foreground':max_foreground,'note':note})
    order=['complete-rune','complete-resource-area','complete-technology-core','complete-field'];rows.sort(key=lambda r:(0,order.index(r['id'])) if r['id'] in order else (1,report['entries'].index(next(e for e in report['entries'] if e['id']==r['id']))))
    html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px var(--font-sans,system-ui);color:var(--foreground,#222);margin:0}.controls{display:flex;gap:10px;flex-wrap:wrap}label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted-foreground,#666)}select{padding:7px;font:14px var(--font-sans,system-ui);color:var(--foreground,#222);background:var(--background,#fff);border:1px solid var(--border,#aaa);border-radius:6px;max-width:100%}.controls label:first-child{flex:2;min-width:220px}.controls label:nth-child(2){flex:1;min-width:145px}.controls label:last-child{flex:1;min-width:110px}p{line-height:1.45;margin:10px 0}#stats{font-weight:600;font-variant-numeric:tabular-nums}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.caption{font-size:12px;min-height:22px;color:var(--muted-foreground,#666)}.crop{position:relative;aspect-ratio:1;overflow:hidden;background:#c2d1df}.crop img{height:100%;position:absolute;max-width:none}.note{font-size:12px;color:var(--muted-foreground,#666)}
</style></head><body><div class="controls"><label>Equipment / source part<select id="model"></select></label><label>Pass stage<select id="stage"></select></label><label>Camera<select id="view"></select></label></div><p id="stats"></p><div class="pair"><div><div class="caption">Current composed baseline</div><div class="crop"><img id="before" alt="Before"></div></div><div><div class="caption" id="caption"></div><div class="crop"><img id="after" alt="After"></div></div></div><p class="note" id="note"></p><p class="note">Full field: 1,573,606 → 1,495,447 placed visual triangles (−78,159). Skin omission uses finite full-sphere views within each selected rigid shell; it is not proof of invisibility. Unselected light/target geometry and materials remain exact.</p><script>
const rows=__ROWS__,model=document.getElementById('model'),stage=document.getElementById('stage'),view=document.getElementById('view');let current;const labels={planar:'Planar boundaries',detail:'Structural LOD trial',final:'Final candidate'};let groups={};for(const row of rows){if(!groups[row.category]){groups[row.category]=document.createElement('optgroup');groups[row.category].label=row.category;model.add(groups[row.category])}groups[row.category].append(new Option(row.name,row.id))}
function frame(){const s=stage.value,columns=current.columns,index=columns===2?1:({planar:1,detail:2,final:3}[s]);for(const id of ['before','after']){const image=document.getElementById(id);image.src=current.paths[view.value];image.style.width=(columns*100)+'%';image.style.left=(id==='before'?0:-index*100)+'%'}const before=current.counts.before,after=current.counts[s];document.getElementById('stats').textContent=before.toLocaleString()+' → '+after.toLocaleString()+' triangles · −'+((before-after)/before*100).toFixed(1)+'%';document.getElementById('caption').textContent=labels[s];document.getElementById('note').textContent=current.note+' Maximum checked silhouette change: '+(current.maximum_foreground[s]*100).toFixed(3)+'%.'}
function choose(){current=rows.find(r=>r.id===model.value);let oldView=view.value,oldStage=stage.value;stage.replaceChildren();for(const s of current.stages)stage.add(new Option(labels[s],s));stage.value=current.stages.includes(oldStage)?oldStage:'final';view.replaceChildren();for(const v of current.views)view.add(new Option(v,v));if(current.views.includes(oldView))view.value=oldView;frame()}
model.addEventListener('change',choose);view.addEventListener('change',frame);stage.addEventListener('change',frame);choose();console.log('Residual comparison entries:',rows.length);
</script></body></html>'''.replace('__ROWS__',json.dumps(rows));(out/'gallery.html').write_text(html)

if __name__=='__main__':main()
