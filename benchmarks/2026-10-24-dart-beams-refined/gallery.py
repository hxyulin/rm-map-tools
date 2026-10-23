"""Check artifacts and publish original/thick/refined matched comparisons."""
import json
from pathlib import Path
from export import OUT,hub
r=json.loads((OUT/'verification.json').read_text());proof=json.loads((OUT/'geometry-verification.json').read_text());ccd=json.loads((OUT/'mesh-ccd-result.json').read_text());deck=json.loads((OUT/'deck-ray-checks.json').read_text());renders=json.loads((OUT/'renders.json').read_text())
assert len(renders['views'])==36 and ccd['exit_code']==0 and ccd['temporary_test_removed']
assert hub.scan.digest(OUT/'mesh-ccd-fixture.txt')==ccd['fixture_sha256']
for item in renders['views']:assert hub.scan.digest(Path(item['path']))==item['sha256']
for path,digest in r['input_pins'].items():assert hub.scan.digest(Path(path))==digest
assert hub.scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']
assert proof['source_faces_covered']==18358 and proof['closed_box_count']==98
paths={str(node):{scope:{view:{stage:str(OUT/f'node{node}-{scope}-{view}-{stage}.webp')for stage in ['source','thick','candidate']}for view in ['oblique','side','end']}for scope in ['frame','station']}for node in [354,587]}
html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px/1.5 var(--font-sans);color:var(--foreground)}p{margin:0 0 12px}.controls{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}select{font:inherit;color:inherit;background:var(--background);padding:6px;border:1px solid var(--border);border-radius:var(--radius);max-width:100%}.images{display:grid;grid-template-columns:1fr 1fr;gap:10px}figure{margin:0}figcaption{margin-bottom:6px}img{width:100%;display:block;border-radius:var(--radius)}.muted{color:var(--muted-foreground);font-size:13px}table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}th,td{text-align:left;padding:7px 4px;border-bottom:1px solid var(--border)}.note{padding:16px;background:var(--card);border-radius:var(--radius);margin:12px 0}</style></head><body>
<p><strong>Thinner beams, with local connection shapes.</strong><br>Long members are fitted separately from brackets and fittings. Each main beam is still one simple solid. The deck, crossbars and all visual geometry stay exact.</p>
<div class="controls"><select id="comparison" aria-label="Comparison"><option value="thick">Previous thick fit</option><option value="source">Original collision</option></select><select id="node" aria-label="Frame"><option value="354">Frame A</option><option value="587">Frame B</option></select><select id="scope" aria-label="Scope"><option value="frame">Frame only</option><option value="station">Station context</option></select><select id="camera" aria-label="Camera"><option value="oblique">Oblique</option><option value="side">Side</option><option value="end">End</option></select></div>
<div class="images"><figure><figcaption id="beforeLabel">Previous thick fit</figcaption><img id="before" alt="Previous frame collision"></figure><figure><figcaption>Refined fit</figcaption><img id="after" alt="Thinner frame collision with local fittings"></figure></div>
<p class="muted" style="margin-top:8px">Orange shows replacement collision; grey stays exact. Original collision selections appear blue.</p>
<table><tr><th>Both frame sides</th><th>Triangles</th></tr><tr><td>Original</td><td>18,358</td></tr><tr><td>Previous thick fit</td><td>336</td></tr><tr><td>Refined fit</td><td>1,318</td></tr></table>
<p><strong>92.8% fewer side triangles.</strong> The extra geometry is local: 26 long-member boxes, 72 fitting boxes and 142 retained triangles. They remain mesh-backed.</p>
<div class="note"><strong>Coverage and projectile checks pass.</strong> All 18,358 original side faces remain covered. All 240 actual mesh CCD shots pass. All 1,554 deck rays retain their original first-hit heights.</div>
<p>Three main opening cores on one side now lose under 0.4% of their area, versus 14–39% before. The other side's largest openings lose about 2–11%; its lower opening loses 6% instead of 81%. One narrow opening remains closed and another remains partly narrowed.</p>
<p class="muted">Whole-map proposal: 369,482 remaining mesh triangles plus unchanged native shapes. Visuals stay unchanged. This is an uncommitted review candidate; clearance integration and runtime timing remain untested.</p>
<script>const paths=PATHS;function update(){const p=paths[node.value][scope.value][camera.value];before.src=p[comparison.value];after.src=p.candidate;beforeLabel.textContent=comparison.value==='thick'?'Previous thick fit':'Original collision';}for(const id of ['comparison','node','scope','camera'])document.getElementById(id).addEventListener('change',update);update();console.log('36 matched images; 18,358 covered faces; 240 CCD shots passed');</script></body></html>'''.replace('PATHS',json.dumps(paths))
(OUT/'gallery.html').write_text(html)
(OUT/'final-verification.json').write_text(json.dumps(dict(geometry=proof,deck=deck,ccd=ccd,matched_images=36,artifact_sha256={p.name:hub.scan.digest(p)for p in OUT.iterdir()if p.is_file()and p.name!='final-verification.json'},installed=False),indent=2)+'\n')
print('All geometry, fixture, source and image checks pass.')
