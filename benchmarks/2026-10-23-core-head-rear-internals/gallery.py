"""Validated interactive rear/internal mechanism comparison."""
import json
from pathlib import Path
from rear import b,BASE
OUT=b.OUT
r=json.loads((OUT/'rear-internals/verification.json').read_text());old=json.loads(BASE.read_text())
rows=json.loads((OUT/'renders.json').read_text())['views'];cut=json.loads((OUT/'cutaway-renders.json').read_text())
assert len(rows)==24 and len(cut['views'])==9
for row in rows+cut['views']:assert b.scan.digest(Path(row['path']))==row['sha256']
assert b.scan.digest(Path(cut['source']))==cut['source_sha256']
for path,h in r['input_pins'].items():assert b.scan.digest(Path(path))==h
assert b.scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']
paths={}
for view in ['back','right','left']:
 paths[view]={'cutaway':{stage:str(OUT/f'cutaway-{view}-{stage}.webp')for stage in ['installed','previous','candidate']},
  'full':{'previous':str(Path(old['candidate_collision']).parent/f'head-{view}-candidate.webp'),'candidate':str(OUT/f'rear-internals/head-{view}-candidate.webp')}}
html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font-family:var(--font-sans);font-size:14px;line-height:1.5;color:var(--foreground)}p{margin:0 0 12px}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}select{font:inherit;color:inherit;background:var(--background);padding:7px;border:1px solid var(--border);border-radius:var(--radius);max-width:100%}.images{display:grid;grid-template-columns:1fr 1fr;gap:10px}figure{margin:0}figcaption{margin-bottom:6px}img{width:100%;display:block;border-radius:var(--radius)}.muted{color:var(--muted-foreground);font-size:13px}table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}th,td{text-align:left;padding:8px 4px;border-bottom:1px solid var(--border)}.note{padding:16px;background:var(--card);border-radius:var(--radius);margin:14px 0}</style></head><body>
<p><strong>The rear and internals are mostly simple solids already.</strong><br>This pass combines motor volumes and simplifies the backing plate, while keeping the side recesses and rear rail gap.</p>
<div class="controls"><select id="mode" aria-label="View type"><option value="cutaway">Internal mechanism cutaway</option><option value="full">Complete head</option></select><select id="camera" aria-label="Camera"><option value="back">Back</option><option value="right" selected>Right side</option><option value="left">Left side</option></select><select id="reference" aria-label="Reference"><option value="previous">Previous proposal</option><option value="installed" selected>Installed source parts</option></select></div>
<div class="images"><figure><figcaption id="label">Previous proposal</figcaption><img id="before" alt="Reference mechanism"></figure><figure><figcaption>Revised collision</figcaption><img id="after" alt="Revised mechanism collision"></figure></div><p id="caption" class="muted" style="margin-top:8px"></p>
<table><tr><th>Head per Core</th><th>Previous</th><th>Revised</th></tr><tr><td>Mesh triangles</td><td>7,330</td><td>6,858</td></tr><tr><td>Native shape leaves¹</td><td>25</td><td>24</td></tr><tr><td>Motor boxes</td><td>14</td><td>10</td></tr><tr><td>Backing plate</td><td>472 triangles</td><td>3 hulls</td></tr></table><p class="muted">¹ Head shapes only. Existing 39 arm/base cylinders per Core remain unchanged. Across both Cores: another 944 mesh triangles and two native leaves removed.</p>
<div class="note"><strong>Keep useful openings; omit small perimeter detail.</strong> The three rear support boxes, their rail gap, and both simplified side recesses stay exactly as before. The backing plate keeps its large notch and 8 mm thickness. Motor consolidation preserves the sleeve/nozzle approach cuts.</div>
<p>The tradeoff is extra solid space up to about 15.7 mm along the motor steps, and removed backing-plate tabs extending about 20 mm. Clearance checks pass for 10,700 side-opening samples, 1,200 notch samples and 450 tool-approach samples. Visual geometry stays byte-identical.</p>
<p class="muted">The older coarse contact tradeoffs remain: 107 of 9,396 central-interface rays shift more than 25 mm against the previous vector fit, with a maximum shift of 178.5 mm. These are finite geometry checks, not complete contact qualification. Nothing installed or committed; grouped native loading and performance measurement remain outstanding.</p>
<script>const paths=PATHS;function update(){const full=mode.value==='full';reference.options[1].disabled=full;if(full&&reference.value==='installed')reference.value='previous';const p=paths[camera.value][mode.value];before.src=p[reference.value];after.src=p.candidate;label.textContent=reference.selectedOptions[0].text;caption.textContent=full?'Full head collision, visuals unchanged. Orange: new shapes; grey: retained mesh.':'Selected motor/support and socket parts only; outer skins and backing plate hidden for inspection. Orange: revised solids. Blue: previous solids. Grey: exact collision mesh.';}for(const id of ['mode','camera','reference'])document.getElementById(id).addEventListener('change',update);update();console.log('Rear/internal comparison ready');</script></body></html>'''.replace('PATHS',json.dumps(paths))
(OUT/'gallery.html').write_text(html)
hashes={str(p.relative_to(OUT)):b.scan.digest(p)for p in OUT.rglob('*')if p.is_file()and p.name not in ['gallery.html','final-verification.json']}
(OUT/'final-verification.json').write_text(json.dumps(dict(geometry=json.loads((OUT/'geometry-verification.json').read_text()),delta=json.loads((OUT/'rear-internals/delta-verification.json').read_text()),matched_images=33,artifact_sha256=hashes,installed=False),indent=2)+'\n')
print('Verified inputs and 33 matched images; wrote gallery.')
