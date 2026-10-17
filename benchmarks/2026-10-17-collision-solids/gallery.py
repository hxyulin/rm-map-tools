#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Generate matched views of complete and source-owned profile colliders."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve(); review = json.loads((out / 'review.json').read_bytes()); data = []
    for r in review['entries']:
        data.append({'id': r['id'], 'stages': r['stages'], 'triangles': r['triangles'], 'images': {view: str(out / r['images'] / (view + '.webp')) for view in ['oblique', 'reverse', 'top', 'front', 'back', 'bottom', 'side']}})
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:var(--font-sans,system-ui);color:var(--foreground,#222);margin:0}p{line-height:1.5;margin:0 0 14px}.muted,small{color:var(--muted-foreground,#666)}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}.stats>div{border-top:2px solid var(--border,#ccc);padding-top:10px}.stats b{font-size:22px;display:block}table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}td,th{text-align:right;border-bottom:1px solid var(--border,#ddd);padding:8px 4px}td:first-child,th:first-child{text-align:left}label{display:block;font-size:13px}select{font:inherit;color:inherit;background:var(--background,white);border:1px solid var(--border,#ccc);padding:8px;border-radius:5px;max-width:100%}.controls{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,1fr);gap:12px;margin:20px 0 12px}#labels{display:grid;text-align:center;font-size:13px;gap:6px;margin-bottom:6px}img{display:block;width:100%;height:auto;border-radius:6px}.note{font-size:13px;margin-top:12px}@media(max-width:480px){.stats b{font-size:18px}.controls{grid-template-columns:1fr}}
</style></head><body>
<p><b>Source-profile collision candidates</b><br><span class="muted">Complete native Energy section and separate Dart panel prisms. Visual models are unchanged.</span></p>
<div class="stats"><div><b>−188,202</b>placed collision triangles<br><small>−42.8% vs previous trial, in scope</small></div><div><b>1,056</b>triangles per Energy unit<br><small>was 11,036 · −90.4%</small></div><div><b>6 mm</b>sampled surface guard<br><small>Energy measured max 5.744 mm</small></div></div>
<table><thead><tr><th>One definition</th><th>Previous collider</th><th>Profile collider</th></tr></thead><tbody><tr><td>Energy unit ×12</td><td>11,036</td><td>1,056</td></tr><tr><td>Dart frame ×2</td><td>66,099</td><td>45,985</td></tr><tr><td>Dart deck / hardware ×2</td><td>61,670</td><td>55,552</td></tr><tr><td>Dart door ×2</td><td>26,116</td><td>18,127</td></tr><tr><td><b>Placed subtotal</b></td><td>440,202</td><td><b>252,000</b></td></tr></tbody></table>
<p class="note">The Energy profile retains the deep socket and annular recess; the cutaway exposes both. It deliberately simplifies collars, knurling and small hardware. Three folded Dart deck panels together reduce from 7,140 to 1,022 triangles.</p>
<div class="controls"><label>Part / scope<select id="part"></select></label><label>View<select id="view"><option>oblique</option><option>reverse</option><option>top</option><option>front</option><option>back</option><option>bottom</option><option>side</option></select></label></div><div id="labels"></div><img id="image" alt="Matched approved visual surface, previous collider, and source-profile collider"><p id="note" class="note muted"></p>
<p class="note muted">Neutral collision geometry only. Native-pose views and finite geometric/clearance checks; runtime speed has not been measured. Existing visual assets, scoring targets, source CAD and installed runtime colliders remain unchanged.</p>
<script>const data=__DATA__;const part=document.getElementById('part'),view=document.getElementById('view');data.forEach((r,i)=>part.add(new Option(r.id,i)));part.value=data.findIndex(r=>r.id==='energy-cutaway');view.value='side';function show(){const r=data[+part.value],labels=document.getElementById('labels');labels.style.gridTemplateColumns=`repeat(${r.stages.length},1fr)`;labels.replaceChildren(...r.stages.map(s=>{const el=document.createElement('span');el.textContent=({reference:'Approved visual surface',previous:'Previous collider',profile:'Profile collider'}[s]||s)+' · '+r.triangles[s].toLocaleString()+' tris';return el}));document.getElementById('image').src=r.images[view.value];document.getElementById('note').textContent=r.id==='energy-cutaway'?'Matched cutaway at source X=0, without added cut faces. The socket stop remains roughly 100 mm deep; small stop retainer relief changes by at most 1.2 mm in the checked rays.':'Each native rigid member stays separate. Profiles preserve large openings; uncovered contact geometry remains.'}part.onchange=view.onchange=show;show();</script></body></html>'''
    (out / 'review.html').write_text(html.replace('__DATA__', json.dumps(data))); print(out / 'review.html')


if __name__ == '__main__': main()
