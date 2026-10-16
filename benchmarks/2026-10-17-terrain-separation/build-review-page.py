# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build a disposable, self-contained T3 review page with inline-able local images."""
from pathlib import Path
import json

REPO=Path(__file__).resolve().parents[2]
out=REPO/'out/appearance-review-v2'
review=json.loads((out/'review.json').read_text())
images=out/'renders'
choices=[('terrain-all','All terrain fixtures','662,976 placed triangles · previous terrain subset'),
         ('terrain-no-secondary','Without fixtures','249,532 placed triangles · same camera and framing'),
         ('secondary-only','Hidden parts only','413,444 placed triangles · same camera and framing'),
         ('full-field','Full-field context','Complete source field · separate framing; 8,311,552 inspection triangles')]
buttons=''.join(f'<button data-choice="{key}" aria-pressed="{str(key=="terrain-no-secondary").lower()}">{label}</button>' for key,label,_ in choices)
figures=''.join(f'<figure data-overview="{key}" {"" if key=="terrain-no-secondary" else "hidden"}><img src="{images/(key+".png")}" alt="{label}"><figcaption>{caption}</figcaption></figure>' for key,label,caption in choices)
small=''.join(f'<figure><img src="{images/(key+".png")}" alt="{title}"><figcaption><b>{title}</b><br>{caption}</figcaption></figure>' for key,title,caption in [
 ('fan-frame-one','Fan frame 1 · #2650147','High-point child; black/cyan CAD colors'),
 ('fan-frame-two','Fan frame 2 · #4070010','Arena-root fixture; black/cyan CAD colors'),
 ('drone-landing-pad','Drone pad · #1754789','The small H-marked platforms'),
 ('outpost-footing','Outpost footing · #1800898','Remains visible when fixtures are hidden')])
models=''.join(f'<option value="{r["name"]}">{r["name"].replace("-"," ").title()}</option>' for r in review['compositions'])
model_images=''.join(f'<figure data-model="{r["name"]}" {"" if i==0 else "hidden"}><img src="{images/(r["name"]+".png")}" alt="{r["name"]}"><figcaption>{r["native_faces"]:,} native faces · {len(r["occurrences"])} product occurrences · STEP + instanced GLB</figcaption></figure>' for i,r in enumerate(review['compositions']))
html='''<!doctype html><html><head><meta charset="utf-8"><style>
body{font:14px/1.5 var(--font-sans);color:var(--foreground)}h3{font-size:19px;margin:18px 0 8px}p{margin:8px 0;color:var(--muted-foreground)}figure{margin:0}img{width:100%;display:block;border-radius:8px}figcaption{font-size:12px;color:var(--muted-foreground);margin:6px 0 10px}button,select{font:inherit;background:var(--secondary);color:var(--foreground);border:1px solid var(--border);border-radius:6px;padding:7px 10px;cursor:pointer}button[aria-pressed=true]{background:var(--primary);color:var(--primary-foreground)}nav{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}.small{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.evidence{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:center}.evidence img{max-height:340px;object-fit:contain;background:#c0d0e0}select{max-width:100%;margin:6px 0 12px}[hidden]{display:none!important}.note{padding:14px 16px;border-radius:var(--radius);background:var(--secondary);margin:12px 0}.label{font-size:12px;color:var(--muted-foreground)}@media(max-width:500px){.small{grid-template-columns:repeat(2,minmax(0,1fr))}.evidence{grid-template-columns:1fr}.evidence img{max-height:260px}}footer{font-size:11px;color:var(--muted-foreground);margin-top:16px}
</style></head><body>
<h3>What disappears without secondary fixtures?</h3>
<p>Toggle the same terrain subset with drone pads, fans, fan frames and grilles hidden. Walls, roofs, footings, terrain and markings remain. This is an inspection selection, not an official CAD layer.</p>
<nav>BUTTONS</nav>FIGURES
<div class="small">SMALL</div>
<h3>The unusual colors are mostly in the CAD</h3>
<div class="evidence"><img src="TECH" alt="Technology Core with original source colors"><div><b>Technology Core: all 4,892 faces explicitly colored</b><p>The copper, green, teal and purple details are original face colors. There is no parent assembly color missing from this export.</p><b>Some other surfaces really are unstyled</b><p>All 1,607 fan faces and 183 of 243 Base-footing faces have no surface fill color. Those receive neutral gray. New GLB metadata distinguishes this fallback from source paint.</p><span class="label">Source diffuse colors with illustrative lighting; no LED emission or reconstructed finish.</span></div></div>
<h3>More complete equipment exports</h3>
<p>Ten compositions preserve source geometry and placements: Dart stations with walls/roof; Bases and Outposts with matching footings; high points with their fans/frames; resource zones with six energy units each.</p>
<label for="equipment">Inspect an export:</label><br><select id="equipment">MODELS</select>MODELIMAGES
<footer>DJI / RoboMaster RMUC2027 V1.0.0 CAD. Preview tessellation: 0.4 mm / 0.25 rad. No simplification, recoloring or runtime package installation. Generated exports are disposable; recipes and tooling remain.</footer>
<script>document.querySelectorAll('[data-choice]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-overview]').forEach(f=>f.hidden=f.dataset.overview!==button.dataset.choice);document.querySelectorAll('[data-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}));document.querySelector('#equipment').addEventListener('change',e=>document.querySelectorAll('[data-model]').forEach(f=>f.hidden=f.dataset.model!==e.target.value));console.log('Review views',document.querySelectorAll('[data-overview]').length,'equipment exports',document.querySelectorAll('[data-model]').length);</script>
</body></html>'''
for key,value in {'BUTTONS':buttons,'FIGURES':figures,'SMALL':small,'TECH':str(images/'technology-core.png'),'MODELS':models,'MODELIMAGES':model_images}.items():html=html.replace(key,value)
(out/'page.html').write_text(html)
