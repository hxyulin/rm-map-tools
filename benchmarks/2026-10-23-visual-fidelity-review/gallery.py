# SPDX-License-Identifier: MIT OR Apache-2.0
"""Publish a matched STEP / simplified visual fidelity review."""
import json
import importlib.util
from audit_current import ROOT, OUT
import numpy as np
from PIL import Image


def main():
    data = json.loads((OUT / 'review.json').read_text())
    full = json.loads((ROOT / 'out/rmuc2027-full-source-field-review/renders.json').read_text())
    spec = importlib.util.spec_from_file_location('fidelity_metrics', __file__.replace('gallery.py', 'render.py'))
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    field_stages = {'original-full-native': 'source', 'refined1mm': 'refined-1mm',
                    'combined17mm': 'combined-17mm', 'protected-current': 'protected-1mm'}
    data['subjects'].insert(0, {'id': 'field', 'label': 'Full arena · original STEP',
                              'triangles': {field_stages[k]: v['placed_triangles'] for k, v in full['stages'].items()}})
    for row in full['views']:
        source = next(r for r in full['views'] if r['stage'] == 'original-full-native' and r['view'] == row['view'])
        data['views'].append({'group': 'field', 'stage': field_stages[row['stage']],
                              'view': row['view'], 'image': row['image'], 'triangles': row['triangles'],
                              'metrics': None if row['stage'] == 'original-full-native' else renderer.metrics(np.asarray(Image.open(source['image'])), np.asarray(Image.open(row['image'])))})
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px var(--font-sans,system-ui);line-height:1.5;color:var(--foreground,#ddd);margin:0}h2{font-size:21px;margin:0 0 7px}p{margin:8px 0 13px}.muted{color:var(--muted-foreground,#999)}.controls{display:flex;gap:10px 15px;flex-wrap:wrap;margin:15px 0}label{display:flex;gap:6px;align-items:center}select,button{font:inherit;color:inherit;background:var(--secondary,#333);border:1px solid var(--border,#555);border-radius:5px;padding:7px;max-width:100%}.note{padding:16px;background:var(--secondary,#222);border-radius:var(--radius,8px);font-size:13px;margin:14px 0}.counts{display:flex;gap:25px;flex-wrap:wrap}.counts b{display:block;font-size:24px}.counts span{font-size:12px;color:var(--muted-foreground,#999)}.canvas{background:#181818;padding:16px;border-radius:8px}.wipe{position:relative;aspect-ratio:1;overflow:hidden}.wipe img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}.badge{position:absolute;top:8px;color:#fff;background:#111d;padding:4px 6px;border-radius:3px;font-size:11px}.left{left:8px}.right{right:8px}.seam{position:absolute;top:0;bottom:0;width:2px;background:#f1a137}.slider{display:flex;gap:10px;align-items:center;margin:9px 0;color:white;font-size:12px}.slider input{flex:1;accent-color:#f1a137}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pair img{width:100%;display:block}.pair p{font-size:12px;color:white}.hidden{display:none}.small{font-size:12px}.stats{font-size:12px;margin-top:12px}details{font-size:12px;margin:16px 0}table{border-collapse:collapse;width:100%}td,th{text-align:right;padding:6px;border-bottom:1px solid var(--border,#555)}td:first-child,th:first-child{text-align:left}button{cursor:pointer}@media(max-width:480px){label,select{font-size:12px}.controls{gap:8px}.badge{font-size:9px}.counts b{font-size:20px}}
</style></head><body><h2>Visual fidelity · original STEP comparison</h2><p class="muted">The original source is the reference. Protect the Tech Core face, complete armor modules and the Power Rune.</p>
<div class="note">The latest 17 mm trial removed detail inside these protected scopes. The interim candidate restores those areas to the accepted 1 mm version. STEP close-ups also show earlier faceting and edge differences. This interim is not fidelity-approved; no installed simulator files have changed.</div>
<div class="controls"><label>Subject <select id="group"></select></label><label>Candidate <select id="stage"></select></label><label>View <select id="view"></select></label><label>Layout <select id="layout"><option value="wipe">Wipe</option><option value="pair">Side by side</option></select></label></div>
<div class="counts"><div><span>STEP subject triangles</span><b id="before"></b></div><div><span>Candidate subject triangles</span><b id="after"></b></div></div><p class="small muted" id="caption"></p>
<div class="canvas"><div id="wipe" class="wipe"><img id="wb" alt="Original STEP tessellation"><img id="wa" alt="Candidate visual"><div id="seam" class="seam"></div><span class="badge left">Original STEP</span><span class="badge right" id="badge"></span></div><div id="pair" class="pair hidden"><div><img id="pb" alt="Original STEP"><p>Original STEP</p></div><div><img id="pa" alt="Candidate"><p id="pairlabel"></p></div></div><div id="slider" class="slider"><span>STEP</span><input id="position" type="range" min="0" max="100" value="50" aria-label="Comparison divider"><span>Candidate</span></div></div>
<div class="stats" id="metrics"></div><p class="small muted">Fresh, unsimplified STEP tessellation at 0.4 mm / 0.25 rad. Matched 1200 × 1200 orthographic source-color views, with fixed STEP framing. Flat, two-sided diagnostic shading. Geometry and color visibility differences need review; these renders do not establish runtime PBR or moving-pose equivalence.</p>
<details><summary>Protected scope counts</summary><table><thead><tr><th>Subject</th><th>STEP</th><th>Interim</th></tr></thead><tbody id="counts"></tbody></table></details>
<script>const data=__DATA__,$=id=>document.getElementById(id),fmt=n=>n.toLocaleString('en-US'),index=new Map(data.views.map(r=>[[r.group,r.stage,r.view].join('|'),r]));
const views={oblique:'Oblique',reverse:'Reverse',front:'Front',back:'Back',side:'Side','other-side':'Other side',top:'Top',bottom:'Bottom'};
$('group').innerHTML=data.subjects.map(s=>'<option value="'+s.id+'">'+s.label+'</option>').join('');$('stage').innerHTML=Object.entries(data.stages).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('');$('stage').value='protected-1mm';$('view').innerHTML=Object.entries(views).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('');
function row(stage){const r=index.get([$('group').value,stage,$('view').value].join('|'));if(!r)throw Error('Missing matched image');return r}function wipe(){const p=$('position').value;$('wa').style.clipPath='inset(0 0 0 '+p+'%)';$('seam').style.left=p+'%'}function update(){const a=row($('stage').value),b=row('source'),label=data.stages[a.stage];for(const id of ['wb','pb'])$(id).src=b.image;for(const id of ['wa','pa'])$(id).src=a.image;$('before').textContent=fmt(b.triangles);$('after').textContent=fmt(a.triangles);$('badge').textContent=label;$('pairlabel').textContent=label;const subject=data.subjects.find(s=>s.id===$('group').value);$('caption').textContent=subject.label+' · '+views[$('view').value]+'. Counts are the selected subject, including hidden/internal surfaces.';const m=a.metrics;$('metrics').textContent=m?'Silhouette mask disagreement: '+fmt(m.foreground_difference_pixels)+' pixels ('+(100*m.foreground_difference_pixels/Math.max(1,m.source_foreground_pixels)).toFixed(2)+'% of source foreground). Red / green / blue pixels lost: '+[m.red,m.green,m.blue].map(x=>fmt(x.lost_pixels)).join(' / ')+'. Finite-view diagnostic only.':'';const pair=$('layout').value==='pair';$('pair').classList.toggle('hidden',!pair);$('wipe').classList.toggle('hidden',pair);$('slider').classList.toggle('hidden',pair);wipe()}
function subject(){const group=$('group').value,oldstage=$('stage').value,oldview=$('view').value,available=data.views.filter(r=>r.group===group);$('stage').innerHTML=Object.entries(data.stages).filter(([k,v])=>available.some(r=>r.stage===k)).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('');$('stage').value=available.some(r=>r.stage===oldstage)?oldstage:'protected-1mm';$('view').innerHTML=Object.entries(views).filter(([k,v])=>available.some(r=>r.view===k)).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('');$('view').value=available.some(r=>r.view===oldview)?oldview:'oblique';update()}$('group').onchange=subject;for(const id of ['stage','view','layout'])$(id).onchange=update;$('position').oninput=wipe;$('counts').innerHTML=data.subjects.map(s=>'<tr><td>'+s.label+'</td><td>'+fmt(s.triangles.source)+'</td><td>'+fmt(s.triangles['protected-1mm'])+'</td></tr>').join('');$('wa').onload=()=>console.log('Candidate image '+$('wa').naturalWidth+'×'+$('wa').naturalHeight);$('group').value='tech-core-face';subject();console.log('Matched image entries: '+index.size);</script></body></html>'''
    (OUT / 'review.html').write_text(html.replace('__DATA__', json.dumps(data)))
    for row in data['views']:
        row['image'] = str(OUT / row['image'])
    (OUT / 'review-inline.html').write_text(html.replace('__DATA__', json.dumps(data)))


if __name__ == '__main__':
    main()
