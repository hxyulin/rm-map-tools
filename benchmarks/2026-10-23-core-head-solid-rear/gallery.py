"""Verify and present solid rear fitting alternatives."""
import json
from pathlib import Path
from solid import b,BASE
OUT=b.OUT;r=json.loads((OUT/'solid-rear/verification.json').read_text());old=json.loads(BASE.read_text());cut=json.loads((OUT/'cutaway-renders.json').read_text());full=json.loads((OUT/'renders.json').read_text())
assert len(cut['views'])==12 and len(full['views'])==24
for row in cut['views']+full['views']:assert b.scan.digest(Path(row['path']))==row['sha256']
for path,h in r['input_pins'].items():assert b.scan.digest(Path(path))==h
assert b.scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']
paths={}
for view in ['right','back','left']:
 paths[view]={mode:{stage:str(OUT/f'{mode}-{view}-{stage}.webp')for stage in ['previous','candidate']}for mode in ['mechanisms','with-plate']}
 paths[view]['full']={'previous':str(Path(old['candidate_collision']).parent/f'head-{view}-candidate.webp'),'candidate':str(OUT/f'solid-rear/head-{view}-candidate.webp')}
html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font-family:var(--font-sans);font-size:14px;line-height:1.5;color:var(--foreground)}p{margin:0 0 12px}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}select{font:inherit;color:inherit;background:var(--background);padding:7px;border:1px solid var(--border);border-radius:var(--radius);max-width:100%}.images{display:grid;grid-template-columns:1fr 1fr;gap:10px}figure{margin:0}figcaption{margin-bottom:6px}img{width:100%;display:block;border-radius:var(--radius)}.muted{color:var(--muted-foreground);font-size:13px}table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}th,td{text-align:left;padding:8px 4px;border-bottom:1px solid var(--border)}.note{padding:16px;background:var(--card);border-radius:var(--radius);margin:14px 0}</style></head><body>
<p><strong>One lower hull, one rod cylinder, one rectangular plate.</strong><br>The large side recesses and upper rail support stay as before; the rear parts become solid collision shapes. All visuals stay byte-identical.</p>
<div class="controls"><select id="mode" aria-label="View type"><option value="mechanisms">Block and rod</option><option value="with-plate">Include backing plate</option><option value="full">Complete head</option></select><select id="camera" aria-label="Camera"><option value="right">Right side</option><option value="back">Back</option><option value="left">Left side</option></select></div>
<div class="images"><figure><figcaption>Previous proposal</figcaption><img id="before" alt="Previous rear collision"></figure><figure><figcaption>Solid rear proposal</figcaption><img id="after" alt="Simplified solid rear collision"></figure></div><p id="caption" class="muted" style="margin-top:8px"></p>
<table><tr><th>Head per Core</th><th>Previous</th><th>Revised</th></tr><tr><td>Mesh triangles</td><td>6,858</td><td>5,240</td></tr><tr><td>Native head shapes¹</td><td>24</td><td>14</td></tr><tr><td>Lower motor block</td><td>10 boxes</td><td>1 hull</td></tr><tr><td>Rod and tip</td><td>1,618 triangles</td><td>1 cylinder</td></tr><tr><td>Backing plate</td><td>3 hulls</td><td>1 box</td></tr></table>
<p class="muted">¹ Existing 39 arm/base cylinders per Core are additional and unchanged. Across both Cores: another 3,236 mesh triangles and 20 primitive leaves removed.</p>
<div class="note"><strong>These openings now become solid:</strong> the lower motor block’s channels, the rod’s bore and slots, and the plate’s notch. The rod cylinder is approximately Ø38.5 × 106.2 mm. The plate keeps its tilted plane and 8 mm thickness, but fills the sloped roof corners; sampled plate deviation reaches about 30 mm.</div>
<p>The side recesses pass all 10,700 sampled opening checks. Retained geometry, visual hashes, upper support boxes and original arm cylinders verify exact. Housing approach checks explicitly exclude the new solid rod and lower block; their former entries are intentionally closed.</p>
<p class="muted">The central-interface grid now has 303 changed hit/miss states out of 9,396 rays against the prior vector fit; 103 common hits shift over 25 mm. Internal reachability remains a design assumption. Native grouped loading and runtime profiling are outstanding; nothing installed or committed.</p>
<script>const paths=PATHS;function update(){const p=paths[camera.value][mode.value];before.src=p.previous;after.src=p.candidate;caption.textContent=mode.value==='full'?'Complete collision head. Orange: new shapes; grey: retained mesh.':'Inspection cutaway: outer casing and side panels hidden'+(mode.value==='mechanisms'?', backing plate also hidden.':'.')+' Blue: preceding shapes; orange: revised shapes. Grey: retained collision.';}for(const id of ['mode','camera'])document.getElementById(id).addEventListener('change',update);update();console.log('Solid rear fit comparison ready');</script></body></html>'''.replace('PATHS',json.dumps(paths))
(OUT/'gallery.html').write_text(html)
hashes={str(p.relative_to(OUT)):b.scan.digest(p)for p in OUT.rglob('*')if p.is_file()and p.name not in ['gallery.html','final-verification.json']}
(OUT/'final-verification.json').write_text(json.dumps(dict(geometry=json.loads((OUT/'geometry-verification.json').read_text()),delta=json.loads((OUT/'solid-rear/delta-verification.json').read_text()),matched_images=36,artifact_sha256=hashes,installed=False),indent=2)+'\n')
print('Verified source pins, geometry and 36 matched images.')
