#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build a compact interactive per-component before/removal comparison gallery."""
import argparse,json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out.resolve();source=json.loads((out/'summary.json').read_bytes());review=json.loads((out/'review.json').read_bytes());by_id={r['id']:r for r in review['components']};source_by_id={r['id']:r for r in source['components']};data=[]
    def applied(row,stage):
        detail=row['stages'][stage]
        if 'proof' in detail:
            return [sum(p['removed_inner_wires'] for p in detail['proof']['rebuilt_faces']),0 if stage=='holes' else row['fastener_candidates']-len(row['bindings']['withheld_source_fastener_unit_ids']),len(detail['proof']['withheld_hole_faces'])]
        values=[applied(source_by_id[p['id']],stage) for p in detail['members'] if p['id'] in source_by_id]
        return [sum(v[k] for v in values) for k in range(3)]
    for row in source['components']:
        cid=row['id'];inspection=by_id[cid];data.append({'id':cid,'holes':row['opening_candidates'],'withheld':row['withheld_openings'],'fasteners':row['fastener_candidates'],'triangles':{s:r['triangles'] for s,r in row['stages'].items()},'sheets':{v:str(out/cid/'review'/(v+'.webp')) for v in inspection['view_names']},'mask_change':inspection['maximum_whole_foreground_difference'],'applied':{stage:applied(row,stage) for stage in ['holes','fasteners','combined']}})
    html='''<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font:14px var(--font-sans,system-ui);color:var(--foreground,#222)}label{display:flex;flex-direction:column;gap:5px;color:var(--muted-foreground,#666);font-size:12px}select{font:14px var(--font-sans,system-ui);padding:9px;border:1px solid var(--border,#bbb);background:var(--card,#f4f4f4);color:var(--foreground,#222);border-radius:8px;max-width:100%;min-width:0}.controls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px;margin-bottom:12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.crop{position:relative;overflow:hidden;aspect-ratio:1;border-radius:8px}.crop img{position:absolute;width:400%;height:100%;max-width:none;top:0}.caption{font-size:12px;color:var(--muted-foreground,#666);margin:4px 0 6px}p{font-size:12px;line-height:1.5;color:var(--muted-foreground,#666)}#stats{padding:16px;background:var(--card,#f4f4f4);border-radius:10px;margin-top:12px;font-variant-numeric:tabular-nums}@media(max-width:520px){.controls{grid-template-columns:1fr 1fr}.controls label:first-child{grid-column:1/-1}}
</style></head><body><div class="controls"><label>Individual component<select id="part"></select></label><label>Removal candidate<select id="variant"><option value="combined">Holes + fasteners</option><option value="holes">Round holes only</option><option value="fasteners">Fasteners only</option></select></label><label>Camera<select id="view"></select></label></div><div class="pair"><div><div class="caption">Original source CAD</div><div class="crop"><img id="before" alt="Original source geometry"></div></div><div><div id="after-label" class="caption">Removal candidate</div><div class="crop"><img id="after" alt="Removal candidate"></div></div></div><div id="stats"></div><p>Original source comparison, including details already handled by earlier optimizations. Non-round slots/windows are withheld. Possible fasteners remain unconfirmed; use the separate variant to check them. Original native face paint and untouched triangles are retained exactly. Visual-only previews; current approved candidates, installed assets and collision are unchanged.</p><script>
const rows=__DATA__;const part=document.getElementById('part'),variant=document.getElementById('variant'),view=document.getElementById('view');
rows.forEach((r,i)=>part.add(new Option(r.id,i)));
function cameras(){const r=rows[+part.value],old=view.value;view.replaceChildren();Object.keys(r.sheets).forEach(v=>view.add(new Option(v.replaceAll('-',' '),v)));if(r.sheets[old])view.value=old;show()}
function show(){const r=rows[+part.value],stage=variant.value,src=r.sheets[view.value],index={holes:1,fasteners:2,combined:3}[stage];document.getElementById('before').src=src;document.getElementById('after').src=src;document.getElementById('after').style.left=(-100*index)+'%';document.getElementById('after-label').textContent=variant.selectedOptions[0].textContent;document.getElementById('stats').textContent=r.applied[stage][0].toLocaleString()+' round mouths filled · '+r.applied[stage][1].toLocaleString()+' possible fasteners removed · '+r.withheld.toLocaleString()+' non-round openings held · '+r.applied[stage][2]+' invalid profiles held. Triangles: '+r.triangles.before.toLocaleString()+' → '+r.triangles[stage].toLocaleString()+'. Max whole-view mask change: '+(100*r.mask_change[stage]).toFixed(3)+'%.'}
part.addEventListener('change',cameras);variant.addEventListener('change',show);view.addEventListener('change',show);cameras();console.log('gallery components',rows.length);
</script></body></html>'''.replace('__DATA__',json.dumps(data,separators=(',',':')))
    (out/'gallery.html').write_text(html);print(out/'gallery.html')
if __name__=='__main__':main()
