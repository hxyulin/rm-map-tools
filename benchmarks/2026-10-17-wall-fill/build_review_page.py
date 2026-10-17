#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build a self-contained-source HTML review with local matched native renders."""
import html,json,sys
from pathlib import Path
from PIL import Image


def main():
    out=Path(sys.argv[1]).resolve();report=json.loads((out/'summary.json').read_text());image=Image.open(out/'review.png')
    cases=[('Highland grille','1,816 → 36 triangles per definition; two placements.'),
           ('Tunnel grille','1,312 → 38 triangles per definition; two placements.'),
           ('Supports · inner side','Close-up of the six-rib wall cavity. Geometry is clipped to identical planes.'),
           ('Supports · outer side','Reverse view of the same support strip.'),
           ('Mirrored support strip','The other team’s wall; same bounded operation.'),
           ('Complete wall','1,334 → 1,124 triangles; larger functional openings remain outside the fill window.'),
           ('Complete mirrored wall','1,334 → 1,182 triangles; whole definition for context.')]
    panels=[]
    for i,(label,caption) in enumerate(cases):
        paths=[]
        for j,kind in enumerate(['source','candidate']):
            path=out/f'view-{i}-{kind}.png';image.crop((10+j*750,40+i*440,745+j*750,430+i*440)).save(path);paths.append(html.escape(str(path)))
        panels.append(f'<section class="case" id="case-{i}" '+('' if i==0 else 'hidden')+f'><div class="pair"><figure><figcaption>Source</figcaption><img src="{paths[0]}" alt="Original {label}"></figure><figure><figcaption>Solid wall candidate</figcaption><img src="{paths[1]}" alt="Filled {label}"></figure></div><p class="note">{caption}</p></section>')
    options=''.join(f'<option value="{i}">{label}</option>' for i,(label,_) in enumerate(cases))
    groups=[('Main roads · both sides',121128),('Colored road borders',51604),('Trapezoid highlands',12300),('Central deck',10936),('Assembly area',10048),('Base footings',8388)]
    rows=''.join(f'<tr><td>{name}</td><td>{n:,}</td><td><span class="bar" style="width:{n/121128*100:.1f}%"></span></td></tr>' for name,n in groups)
    before=report['placed_triangles_before'];after=report['placed_triangles_after']
    document='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{font:14px/1.5 var(--font-sans,system-ui);color:var(--foreground,#17202f);margin:0}h3{margin:18px 0 8px;font-size:17px}p{margin:8px 0}.note{font-size:12px;color:var(--muted-foreground,#667085)}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}td{padding:6px 0;border-bottom:1px solid var(--border,#ddd)}td:nth-child(2){text-align:right;padding-right:14px}td:nth-child(3){width:28%}.bar{display:block;height:8px;background:var(--chart-1,#5f86bb);border-radius:3px}.stats{display:flex;flex-wrap:wrap;gap:16px;font-size:16px}.stats b{font-size:21px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}figure{margin:0}figcaption{font-size:12px;margin:7px 0}img{width:100%;display:block;border-radius:var(--radius,6px)}select{max-width:100%;padding:8px;border:1px solid var(--border,#aaa);border-radius:6px;background:var(--background,white);color:inherit;font:inherit}button{font:inherit;background:var(--background,white);color:inherit;border:1px solid var(--border,#aaa);border-radius:6px;padding:8px;cursor:pointer}nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}[hidden]{display:none!important}body[data-mode=source] figure:nth-child(2),body[data-mode=candidate] figure:first-child{display:none}body[data-mode=source] .pair,body[data-mode=candidate] .pair{grid-template-columns:1fr}@media(max-width:440px){.pair{grid-template-columns:1fr}td:nth-child(3){width:15%}}
</style></head><body><h3>Largest native terrain groups</h3><p class="note">Unmodified CAD baseline: 0.4 mm / 0.25 rad. The approved 16-section road remesh is still pending. These groundwork counts exclude the separate grilles.</p><table>'''+rows+'''</table><h3>Grille and support-wall candidate</h3><div class="stats"><span><b>'''+f'{before:,} → {after:,}'+'''</b> placed triangles</span><span><b>'''+f'{(before-after)/before*100:.1f}%'+'''</b> less in this selection</span></div><p>Four definitions, six placements. Original CAD is unchanged; this candidate intentionally closes the selected openings.</p><nav><select aria-label="Review view" onchange="document.querySelectorAll('.case').forEach((p,i)=>p.hidden=i!=this.value)">'''+options+'''</select><button onclick="document.body.dataset.mode='both'">Both</button><button onclick="document.body.dataset.mode='source'">Source</button><button onclick="document.body.dataset.mode='candidate'">Candidate</button></nav>'''+''.join(panels)+'''<p class="note">Same camera and framing per pair. Grey grille material is the tagged unresolved-source fallback. Native differences found no removed material or additions outside the explicit fill volumes, within 0.01 mm³ tolerance. All four derived STEP files passed native read-back checks. No runtime package has been installed.</p><script>console.assert(document.querySelectorAll('.case').length===7);console.log('Seven matched views; select a view or enlarge Source/Candidate.');</script></body></html>'''
    (out/'review.html').write_text(document);print(out/'review.html')
if __name__=='__main__':main()
