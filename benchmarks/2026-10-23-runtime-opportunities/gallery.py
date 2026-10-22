# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build an offline comparison gallery for the rendered runtime probes."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--absolute', action='store_true', help='absolute local image paths for inline publication')
    parser.add_argument('--refined', action='store_true', help='include cleaned 1 mm panel reconstructions')
    args = parser.parse_args()
    out = args.out.resolve()
    report = json.loads((out / ('refined-renders.json' if args.refined else 'renders.json')).read_text())
    for row in report['views']:
        if not (out / row['image']).is_file():
            raise ValueError('missing render: ' + row['image'])
        if args.absolute:
            row['image'] = str(out / row['image'])
    data = {'stages': {k: v['triangles'] for k, v in report['stages'].items()}, 'views': report['views']}
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px var(--font-sans,system-ui);color:var(--foreground,#ddd);line-height:1.45;margin:0}h2{font-size:20px;margin:0 0 6px}p{margin:6px 0 14px}.muted{color:var(--muted-foreground,#999)}.controls{display:flex;flex-wrap:wrap;gap:10px 16px;margin:14px 0}label{display:flex;align-items:center;gap:7px}select,button{background:var(--secondary,#333);color:inherit;border:1px solid var(--border,#666);padding:7px;border-radius:5px;font:inherit;max-width:100%}button{cursor:pointer}.stats{font-size:13px;margin:10px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pair img{width:100%;display:block}.caption{font-size:12px;padding:6px 0}.wipe{position:relative;aspect-ratio:1;overflow:hidden;background:#fff}.wipe img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}.badge{position:absolute;top:9px;padding:5px 8px;background:#111d;color:white;font-size:12px;border-radius:4px;pointer-events:none}.badge.left{left:9px}.badge.right{right:9px}.seam{position:absolute;top:0;bottom:0;width:2px;background:#ed9d2b;pointer-events:none}.slider{display:flex;gap:12px;align-items:center;margin:10px 0}.slider input{flex:1;accent-color:#ed9d2b}.note{font-size:12px;color:var(--muted-foreground,#999);margin-top:16px}.hidden{display:none}details{font-size:12px;margin-top:10px}summary{cursor:pointer}.fullscreen{background:var(--background,#161616);padding:16px}.fullscreen:fullscreen .wipe{height:calc(100% - 85px);aspect-ratio:auto}.fullscreen:fullscreen{overflow:auto}.fullscreen:fullscreen .wipe img{object-fit:contain}@media(max-width:480px){.controls{gap:8px}label{font-size:12px}select,button{font-size:12px;padding:6px}.badge{font-size:10px}.pair{gap:5px}}
</style></head><body>
<h2>Map reduction · inspect the actual meshes</h2><p class="muted">Eight subjects · seven matched views · visual and collision-derived candidates</p>
<div class="controls"><label>Subject <select id="group"></select></label><label>View <select id="view"></select></label><label>Candidate <select id="stage"></select></label><label>Reference <select id="reference"><option value="visual-current">Current visual</option><option value="visual-1mm">Previous visual · 1 mm</option><option value="collision-current">Current collision</option><option value="collision-1mm">Previous collision · 1 mm</option></select></label><label>Layout <select id="layout"><option value="wipe">Wipe</option><option value="pair">Side by side</option></select></label></div>
<p id="stats" class="stats"></p><div id="canvas" class="fullscreen"><div class="wipe" id="wipe"><img id="wb" alt="Current reference"><img id="wa" alt="Reduced candidate"><div class="seam" id="seam"></div><span class="badge left" id="lb"></span><span class="badge right" id="la"></span></div><div class="pair hidden" id="pair"><div><img id="pb" alt="Current reference"><div class="caption" id="cb"></div></div><div><img id="pa" alt="Reduced candidate"><div class="caption" id="ca"></div></div></div><div class="slider" id="slider"><span>Reference</span><input type="range" id="position" min="0" max="100" value="50" aria-label="Comparison divider"><span>Candidate</span></div><button id="fullscreen">Enlarge</button></div>
<p class="note">1200 × 1200, matched cameras and crop bounds. Source colors and available embedded artwork; flat, two-sided diagnostic shading. Collision-derived meshes retain their existing proxy colors/materials and may omit visual-only artwork or detail. Reductions are unguarded inspection candidates; geometry, openings and animation are not approved. Runtime assets are unchanged.</p>
<details><summary>Triangle totals across the whole arena</summary><div id="totals"></div></details>
<script>const data=__DATA__;const groups={field:'Full arena','tech-core':'Tech Core',rune:'Rune','dart-station':'Dart station',outpost:'Outpost',base:'Base','resource-area':'Resource area','energy-unit':'Energy unit'};const views={oblique:'Oblique',reverse:'Reverse',top:'Top',front:'Front',back:'Back',side:'Side',bottom:'Bottom'};const stages={'visual-0.1mm':'Visual · 0.1 mm','visual-1mm':'Visual · 1 mm','visual-4mm':'Visual · 4 mm','collision-current':'Current collision as visual','collision-0.1mm':'Collision as visual · 0.1 mm','collision-1mm':'Collision as visual · 1 mm','collision-4mm':'Collision as visual · 4 mm',...(data.stages['visual-refined-1mm']?{'visual-refined-1mm':'Refined visual · 1 mm','collision-refined-1mm':'Refined collision · 1 mm'}:{})};const $=s=>document.getElementById(s),fmt=n=>n.toLocaleString('en-US');for(const [id,options] of [['group',groups],['view',views],['stage',stages]])$(id).innerHTML=Object.entries(options).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('');$('group').value='tech-core';$('stage').value='collision-1mm';const index=new Map(data.views.map(r=>[[r.group,r.view,r.stage].join('|'),r]));if(index.size!==8*7*Object.keys(data.stages).length)throw Error('Incomplete render combinations');function row(s){const r=index.get([$('group').value,$('view').value,s].join('|'));if(!r)throw Error('Missing render');return r}function name(s){return stages[s]||(s==='visual-current'?'Current visual':'Current collision')}function wipe(){const v=$('position').value;$('wa').style.clipPath='inset(0 0 0 '+v+'%)';$('seam').style.left=v+'%'}function update(){const b=row($('reference').value),a=row($('stage').value);for(const id of ['wb','pb'])$(id).src=b.image;for(const id of ['wa','pa'])$(id).src=a.image;const bc=name(b.stage)+' · '+fmt(b.triangles)+' triangles',ac=name(a.stage)+' · '+fmt(a.triangles)+' triangles';$('lb').textContent='Reference';$('la').textContent=name(a.stage);$('cb').textContent=bc;$('ca').textContent=ac;const input=a.stage.startsWith('visual')?'visual-current':'collision-current';const saving=100*(1-data.stages[a.stage]/data.stages[input]);$('stats').textContent=bc+' → '+ac+' | Whole arena: '+fmt(data.stages[a.stage])+' triangles ('+saving.toFixed(1)+'% below its '+(input.startsWith('visual')?'visual':'collision')+' input)';const pair=$('layout').value==='pair';$('wipe').classList.toggle('hidden',pair);$('slider').classList.toggle('hidden',pair);$('pair').classList.toggle('hidden',!pair);wipe()}for(const id of ['group','view','stage','reference','layout'])$(id).onchange=update;$('position').oninput=wipe;$('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else $('canvas').requestFullscreen().catch(()=>{window.open(row($('stage').value).image,'_blank')})};$('totals').innerHTML=Object.entries(data.stages).map(([k,v])=>'<p>'+name(k)+': '+fmt(v)+'</p>').join('');$('wa').onload=()=>console.log('Candidate image ready: '+$('wa').naturalWidth+' × '+$('wa').naturalHeight);update();console.log('Validated '+index.size+' unique subject/view/stage combinations.');</script></body></html>'''.replace('__DATA__', json.dumps(data))
    if args.refined:
        html = html.replace("$('stage').value='collision-1mm'", "$('stage').value='collision-refined-1mm';$('reference').value='collision-1mm'")
        totals = json.loads((out / 'refined-totals.json').read_text())
        v, c = totals['visual'], totals['collision']
        info = (f"<p class='stats'><b>Cleaned 1 mm:</b> visual {v['after_triangles']:,} triangles "
                f"(+{v['after_triangles'] - v['before_triangles']:,} for repairs), "
                f"{v['before_placed_primitives']:,} → {v['after_placed_primitives']:,} primitive occurrences. "
                f"Collision-derived: {c['after_triangles']:,} triangles; "
                f"{c['before_placed_primitives']:,} → {c['after_placed_primitives']:,} primitive occurrences. "
                "Primitive counts are not measured GPU draw calls or speedups.</p>")
        html = html.replace('Map reduction · inspect the actual meshes', '1 mm · reconstructed panel boundaries')
        html = html.replace('<div class="controls">', info + '<div class="controls">', 1)
        html = html.replace('Reductions are unguarded inspection candidates; geometry, openings and animation are not approved.',
                            'Refined structural panels use source outlines and holes; the curved remainder keeps the previous 1 mm geometry. These remain inspection candidates; animation, optics and collision are not approved.')
    name = ('refined-review' if args.refined else 'review') + ('-inline' if args.absolute else '') + '.html'
    (out / name).write_text(html)


if __name__ == '__main__':
    main()
