#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Generate a local matched-view gallery for the game-oriented LOD experiments."""
import argparse
import json
from pathlib import Path
from run import ROOT


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); out = args.out.resolve(); report = json.loads((out / 'review.json').read_bytes()); data = []
    for row in report['entries']:
        data.append({'id': row['id'], 'kind': row['kind'], 'stages': row['stages'], 'triangles': row['triangles'],
                     'images': {view: str(out / row['images'] / (view + '.webp')) for view in ['oblique', 'reverse', 'top', 'front', 'back', 'bottom']}})
    template = '''<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:var(--font-sans,system-ui);color:var(--foreground,#222);margin:0}p{line-height:1.5;margin:0 0 14px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}.stats>div{border-top:2px solid var(--border,#ccc);padding-top:10px}.stats b{font-size:22px;display:block}.muted,small{color:var(--muted-foreground,#666)}label{display:block;font-size:13px}select{font:inherit;color:inherit;background:var(--background,white);border:1px solid var(--border,#ccc);padding:8px;max-width:100%;border-radius:5px}.controls{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,1fr);gap:12px;margin:20px 0 12px}#labels{display:grid;text-align:center;font-size:13px;gap:6px;margin-bottom:6px}img{display:block;width:100%;height:auto;border-radius:6px}.note{font-size:13px;margin-top:12px}table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}td,th{text-align:right;border-bottom:1px solid var(--border,#ddd);padding:8px 4px}td:first-child,th:first-child{text-align:left}@media(max-width:480px){.stats b{font-size:18px}.controls{grid-template-columns:1fr}}
</style></head><body>
<p><b>Game-oriented LOD candidates</b><br><span class="muted">Complete 3D road strips and independent equipment collision meshes.</span></p>
<div class="stats"><div><b>1.33M</b>placed visual triangles<br><small>was 1.50M · −11.2%</small></div><div><b>−97.1%</b>road geometry<br><small>172,732 → 5,004</small></div><div><b>−115,500</b>equipment collider triangles<br><small>6 mm trial · −17.6% in scope</small></div></div>
<table><thead><tr><th>Roads, both sides</th><th>Reference</th><th>Candidate</th></tr></thead><tbody><tr><td>Visual: 16 sections / wave</td><td>172,732</td><td>5,004</td></tr><tr><td>Collision: 12 sections / wave</td><td>121,128</td><td>1,892</td></tr></tbody></table>
<p class="note">Visual road deviation ≤0.657 mm measured; collision road deviation ≤1.122 mm. Colored borders remain visual-only. Whole-field GLB: 66.4 → 53.8 MB; mesh/primitive counts and source placements stay unchanged.</p>
<div class="controls"><label>Part<select id="part"></select></label><label>View<select id="view"><option>oblique</option><option>reverse</option><option>top</option><option>front</option><option>back</option><option>bottom</option></select></label></div><div id="labels"></div><img id="image" alt="Matched source and LOD candidate views"><p id="scope" class="note muted"></p>
<p class="note muted">Collision examples share one neutral color for comparison. A 6 mm surface allowance changes small details deliberately. Energy retained its input geometry. Existing equipment visuals, Base collider and scoring targets are unchanged. These are finite geometry checks and source-pose views; runtime performance has not been measured.</p>
<script>const data=__DATA__; const part=document.getElementById('part'),view=document.getElementById('view'); data.forEach((r,i)=>part.add(new Option(r.id,i)));part.value=data.findIndex(r=>r.id==='road-wave-closeup');function show(){const r=data[+part.value];document.getElementById('image').src=r.images[view.value];const labels=document.getElementById('labels');labels.style.gridTemplateColumns=`repeat(${r.stages.length},1fr)`;labels.replaceChildren(...r.stages.map(s=>{const el=document.createElement('span');el.textContent=({'reference':'Approved reference','sections-16':'16 sections / wave','contact-3mm':'3 mm collider','contact-6mm':'6 mm collider'}[s]||s)+' · '+r.triangles[s].toLocaleString()+' tris';return el}));document.getElementById('scope').textContent=r.kind==='visual'?'Source colors and shared cap boundaries. Equipment elsewhere is byte-for-byte retained.':'Collision-only candidate, generated separately for each rigid source member. Rendering geometry is unchanged.'}part.onchange=view.onchange=show;show();</script></body></html>'''
    (out / 'review.html').write_text(template.replace('__DATA__', json.dumps(data)))
    print(out / 'review.html')


if __name__ == '__main__': main()
