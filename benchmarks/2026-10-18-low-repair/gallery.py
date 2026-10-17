#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare both repairs with the approved source and original Low."""
import argparse
import json
from pathlib import Path
from build import ROOT


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-low-repair')
    a = ap.parse_args(); out = a.out.resolve()
    review = json.loads((out / 'review.json').read_text())
    original = json.loads((ROOT / 'out/rmuc2027-ultra-lod/summary.json').read_text())
    levels = [r for r in original['levels'] if r['level'] in ['approved', 'low']]
    for name in ['sealed', 'tight']:
        r = json.loads((out / (('budget-sealed' if name == 'sealed' else name) + '.json')).read_text())
        levels.append({'level': name, **{k: r[k] for k in ['placed_triangles', 'stored_triangles', 'bytes']}})
    data = {'levels': levels, 'views': [{k: v[k] for k in ['group', 'view', 'level', 'triangles', 'image']} for v in review['views']]}
    for r in data['views']: r['image'] = str(out / r['image'])
    html = '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;font:14px var(--font-sans,system-ui);color:var(--foreground,#ddd)}h3{margin:0 0 10px;font-size:19px}p{font-size:13px;line-height:1.5;color:var(--muted-foreground,#aaa)}select,button{background:var(--secondary,#333);color:var(--foreground,#ddd);border:1px solid var(--border,#666);border-radius:5px;padding:7px}label{display:inline-flex;gap:6px;align-items:center;margin:0 12px 12px 0}table{width:100%;border-collapse:collapse;font-size:12px;margin:12px 0 18px}th,td{text-align:right;padding:5px;border-bottom:1px solid var(--border,#444);font-variant-numeric:tabular-nums}th:first-child,td:first-child{text-align:left}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}img{display:block;width:100%;border-radius:5px}.caption{padding:7px 0;font-size:13px}.thumbs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.thumbs button{padding:3px;cursor:pointer}.thumbs button[aria-pressed=true]{outline:2px solid var(--primary,#709cff)}.thumbs span{display:block;padding:6px 0;font-size:12px}@media(max-width:480px){th,td{padding:5px 2px}table{font-size:11px}.thumbs span{font-size:10px}}
</style></head><body><h3>Low LOD · selective surface repairs</h3><p>Repairs restore broad surfaces, rims and light-region shapes. Other pieces keep their original Low geometry. Whole-arena totals include every instance.</p><table><thead><tr><th>Version</th><th>Placed triangles</th><th>Stored triangles</th><th>Saving vs approved</th><th>GLB MB</th></tr></thead><tbody id="stats"></tbody></table><label>Subject <select id="group"></select></label><label>View <select id="view"></select></label><label>Compare against <select id="against"><option value="approved">Approved</option><option value="low">Original Low</option></select></label><div class="pair"><div><img id="before"><div class="caption" id="bc"></div></div><div><img id="after"><div class="caption" id="ac"></div></div></div><div class="thumbs" id="thumbs"></div><p>Repaired Low uses Budget checks (8 mm structural / 1 mm chromatic, up to 5% bad area) plus 1,407 original triangles to cover residual interior gaps. Tight: 4 mm / 0.5 mm, up to 2%. Both retain closure of originally closed repaired pieces and reject new unanchored boundary loops. Gap patches may overlap same-material coarse faces. These are finite checks, not maximum-error certificates.</p><p>Inspection candidates only; collision and the installed runtime package are unchanged. Seven matched 1200px source-pose views per subject, using source colors and embedded artwork. Runtime PBR and animated poses remain unverified.</p><script>
const data=__DATA__;let level='sealed';const names={field:'Full arena',base:'Base',outpost:'Outpost','dart-station':'Dart station',rune:'Rune','technology-core':'Tech Core','energy-unit':'Energy unit','resource-area':'Resource area'};const titles={approved:'Approved',low:'Original Low',sealed:'Repaired Low',tight:'Tight trial'};const fmt=n=>n.toLocaleString();const group=document.getElementById('group'),view=document.getElementById('view'),against=document.getElementById('against');group.innerHTML=Object.entries(names).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('');group.value='base';view.innerHTML=['oblique','reverse','top','front','back','side','bottom'].map(v=>'<option value="'+v+'">'+v[0].toUpperCase()+v.slice(1)+'</option>').join('');document.getElementById('stats').innerHTML=data.levels.map(r=>'<tr><td>'+titles[r.level]+'</td><td>'+fmt(r.placed_triangles)+'</td><td>'+fmt(r.stored_triangles)+'</td><td>'+(100*(1-r.placed_triangles/data.levels[0].placed_triangles)).toFixed(1)+'%</td><td>'+(r.bytes/1e6).toFixed(2)+'</td></tr>').join('');function row(s){return data.views.find(r=>r.group===group.value&&r.view===view.value&&r.level===s)}function update(){for(const [id,stage]of[['before',against.value],['after',level]]){const r=row(stage);document.getElementById(id).src=r.image;document.getElementById(id).alt=titles[stage]+' '+names[group.value];document.getElementById(id==='before'?'bc':'ac').textContent=titles[stage]+' · '+fmt(r.triangles)+' triangles'}document.getElementById('thumbs').innerHTML=['low','sealed','tight'].map(s=>{const r=row(s);return '<button data-level="'+s+'" aria-pressed="'+(level===s)+'"><img src="'+r.image+'" alt="'+titles[s]+' preview"><span>'+titles[s]+' · '+fmt(r.triangles)+'</span></button>'}).join('');document.querySelectorAll('[data-level]').forEach(b=>b.onclick=()=>{level=b.dataset.level;update()})}group.onchange=update;view.onchange=update;against.onchange=update;update();
</script></body></html>'''.replace('__DATA__', json.dumps(data))
    (out / 'review.html').write_text(html)


if __name__ == '__main__': main()
