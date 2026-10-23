"""Validate top/base trial and show matched frame and isolated detail views."""
import json
from pathlib import Path
from export import OUT,hub
r=json.loads((OUT/'verification.json').read_text());proof=json.loads((OUT/'geometry-verification.json').read_text());ccd=json.loads((OUT/'mesh-ccd-result.json').read_text());deck=json.loads((OUT/'deck-ray-checks.json').read_text());renders=json.loads((OUT/'renders.json').read_text())
assert len(renders['views'])==36 and ccd['exit_code']==0 and ccd['temporary_test_removed']
assert hub.scan.digest(OUT/'mesh-ccd-fixture.txt')==ccd['fixture_sha256']
assert '320 shots passed'in(OUT/'mesh-ccd.log').read_text()
for item in renders['views']:assert hub.scan.digest(Path(item['path']))==item['sha256']
for path,digest in r['input_pins'].items():assert hub.scan.digest(Path(path))==digest
assert hub.scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']
assert proof['source_faces_contained']==10512 and proof['closed_boxes']==172
paths={str(node):{scope:{view:{stage:str(OUT/f'node{node}-{scope}-{view}-{stage}.webp')for stage in ['source','candidate']}for view in ['oblique','side','end']}for scope in ['frame','top','base']}for node in [354,587]}
html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px/1.5 var(--font-sans);color:var(--foreground)}p{margin:0 0 12px}.controls{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}select{font:inherit;color:inherit;background:var(--background);padding:6px;border:1px solid var(--border);border-radius:var(--radius);max-width:100%}.images{display:grid;grid-template-columns:1fr 1fr;gap:10px}figure{margin:0}figcaption{margin-bottom:6px}img{width:100%;display:block;border-radius:var(--radius)}.muted{color:var(--muted-foreground);font-size:13px}table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}th,td{text-align:left;padding:7px 4px;border-bottom:1px solid var(--border)}.note{padding:16px;background:var(--card);border-radius:var(--radius);margin:12px 0}</style></head><body>
<p><strong>Dart station: simpler top and base collision.</strong><br>Four top rungs, five lower crossbars and the flat deck become simple solids, with small fittings approximated locally. The slimmer side fit stays exact.</p>
<div class="controls"><select id="scope" aria-label="Scope"><option value="top">Top details</option><option value="base">Base details</option><option value="frame">Whole frame</option></select><select id="node" aria-label="Frame"><option value="354">Frame A</option><option value="587">Frame B</option></select><select id="camera" aria-label="Camera"><option value="oblique">Oblique</option><option value="side">Side</option><option value="end">End</option></select></div>
<div class="images"><figure><figcaption>Accepted side-fit reference</figcaption><img id="before" alt="Previous Dart top and base collision"></figure><figure><figcaption>Simplified top and base</figcaption><img id="after" alt="New Dart top and base collision"></figure></div>
<p class="muted" style="margin-top:8px">Blue: replaced source faces. Orange: new collision solids. Grey: exact retained geometry. Detail views crop away the rest of the frame; use “Whole frame” to inspect the joins.</p>
<table><tr><th>Both stations</th><th>Before</th><th>After</th></tr><tr><td>Selected top/base faces</td><td>10,512</td><td>2,064</td></tr><tr><td>Whole frame owners</td><td>17,830</td><td>9,382</td></tr></table>
<p><strong>8,448 more triangles saved.</strong> Complex upper mounts and lower guide profiles stay exact. All visuals remain unchanged.</p>
<div class="note"><strong>320/320 projectile CCD shots pass.</strong> Every replaced source face remains enclosed. All 1,554 short deck probes retain the original surface height. Broader overhead queries shift by at most 2.575 mm as shallow details become solid.</div>
<p class="muted">The combined proposal has 361,034 remaining collision mesh triangles plus unchanged native shapes. New solids stay mesh-backed. This trial is uncommitted and uninstalled; dynamic door clearance, match integration and runtime timing remain untested.</p>
<script>const paths=PATHS;function update(){const p=paths[node.value][scope.value][camera.value];before.src=p.source;after.src=p.candidate;}for(const id of ['node','scope','camera'])document.getElementById(id).addEventListener('change',update);update();console.log('36 matched views; complete source coverage; 320 mesh CCD shots passed');</script></body></html>'''.replace('PATHS',json.dumps(paths))
(OUT/'gallery.html').write_text(html)
(OUT/'final-verification.json').write_text(json.dumps(dict(geometry=proof,deck=deck,ccd=ccd,matched_images=36,artifact_sha256={p.name:hub.scan.digest(p)for p in OUT.iterdir()if p.is_file()and p.name!='final-verification.json'},installed=False),indent=2)+'\n');print('Verified source pins, meshes, 36 renders and 320-shot result.')
