"""Validate proposal assets and show matched Outpost/Rune collision comparisons."""
import json
from pathlib import Path
from inventory import ROOT,OUT,STAGE,hub
reports={asset:json.loads((OUT/f'{asset}-verification.json').read_text())for asset in ['outpost','rune']};proof=json.loads((OUT/'geometry-verification.json').read_text());ccd=json.loads((OUT/'mesh-ccd-result.json').read_text());renders=json.loads((OUT/'renders.json').read_text());stage=json.loads(STAGE.read_text())
assert len(renders)==24 and ccd['exit_code']==0 and ccd['temporary_test_removed']
assert hub.scan.digest(OUT/'mesh-ccd-fixture.txt')==ccd['fixture_sha256'] and '1392 shots passed'in(OUT/'mesh-ccd.log').read_text()
for row in renders:assert hub.scan.digest(Path(row['path']))==row['sha256']
for asset,r in reports.items():
 for path,h in r['input_pins'].items():assert hub.scan.digest(Path(path))==h
 assert hub.scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']
 stage['collision_assets'][asset]=dict(path=r['candidate_collision'],sha256=r['candidate_sha256'],triangles=r['candidate_triangles'],placements=r['placements'],placed_triangles=r['candidate_triangles']*r['placements'])
for role in ['visual','collision']:
 for data in stage[role+'_assets'].values():assert hub.scan.digest(Path(data['path']))==data['sha256']
stage['placed_collision_triangles']=sum(x['placed_triangles']for x in stage['collision_assets'].values());stage.update(variant='outpost-hardware-and-rune-strip-trial',installed=False,contact_validated=False)
(OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
summary=dict(placed_triangles_saved=sum(r['placed_triangles_saved']for r in reports.values()),field_native_remaining_mesh_triangles=334146,field_native_shapes=dict(cylinder=80,box=8,convex_hull=33),field_diagnostic_triangles=stage['placed_collision_triangles'],placed_visual_triangles=stage['placed_visual_triangles'],new_native_leaves=0,installed=False)
assert summary['placed_triangles_saved']==26888 and summary['field_diagnostic_triangles']==343826
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
paths={asset:{scope:{view:{s:str(OUT/f'{asset}-{scope}-{view}-{s}.webp')for s in ['source','candidate']}for view in ['front','oblique']}for scope in (['whole','lower','upper']if asset=='outpost'else['whole','arm-0','strip'])}for asset in reports}
html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px/1.5 var(--font-sans);color:var(--foreground)}p{margin:0 0 12px}.controls{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}select{font:inherit;color:inherit;background:var(--background);padding:6px;border:1px solid var(--border);border-radius:var(--radius);max-width:100%}.images{display:grid;grid-template-columns:1fr 1fr;gap:10px}figure{margin:0}figcaption{margin-bottom:6px}img{width:100%;display:block;border-radius:var(--radius)}.muted{color:var(--muted-foreground);font-size:13px}table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}th,td{text-align:left;padding:7px 4px;border-bottom:1px solid var(--border)}.note{padding:16px;background:var(--card);border-radius:var(--radius);margin:12px 0}</style></head><body>
<p><strong>Next trial: Outpost hardware and long Rune arm strips.</strong><br>Collision only. Protected visuals, armor, lights and markings remain byte-exact.</p>
<div class="controls"><select id="asset" aria-label="Asset"><option value="rune">Rune arms</option><option value="outpost">Outpost</option></select><select id="scope" aria-label="Scope"></select><select id="camera" aria-label="Camera"><option value="front">Front</option><option value="oblique">Oblique</option></select></div>
<div class="images"><figure><figcaption>Current reviewed collision</figcaption><img id="before" alt="Current collision geometry"></figure><figure><figcaption>Simplified collision</figcaption><img id="after" alt="Candidate simplified collision geometry"></figure></div>
<p class="muted" style="margin-top:8px">Blue: replaced source faces. Orange: simplified solids. Grey: exact retained geometry. Use the scope selector for a complete arm or whole assembly.</p>
<table><tr><th>Scope</th><th>Before</th><th>After</th></tr><tr><td>Outpost per unit</td><td>23,196</td><td>17,274</td></tr><tr><td>20 Rune strips</td><td>15,736</td><td>692</td></tr></table>
<p><strong>26,888 placed triangles saved.</strong> Outpost: 134 compact hardware islands per unit become local boxes; large shells and rotor/armor owners stay exact. Rune: two strips per arm become simple extruded outlines, retaining their edge scallops and original joint ownership.</p>
<div class="note"><strong>All replaced source faces remain covered.</strong> Reopened solids are closed. All 1,392 projectile CCD shots pass against the real meshes in separated static fixtures. Worst sampled surface change: 4.29 mm on compact Outpost hardware; 2.19 mm on Rune strips.</div>
<p>Small bores become solid collision. The Rune's large target openings remain exact in the unselected panels. Live spinning-body collision and scoring are not tested by these static fixtures.</p>
<p class="muted">If adopted: 334,146 remaining mesh triangles + unchanged 80 cylinders, 8 boxes and 33 hulls. New solids remain mesh-backed. This trial is uncommitted and uninstalled; runtime speedup remains unmeasured.</p>
<script>const paths=PATHS;const names={rune:{strip:'One strip', 'arm-0':'Complete arm',whole:'Whole Rune'},outpost:{whole:'Whole Outpost',lower:'Lower structure',upper:'Upper structure'}};function update(){const p=paths[asset.value][scope.value][camera.value];before.src=p.source;after.src=p.candidate;}function chooseAsset(){scope.replaceChildren();for(const [key,label]of Object.entries(names[asset.value])){const o=document.createElement('option');o.value=key;o.textContent=label;scope.appendChild(o);}update();}asset.addEventListener('change',chooseAsset);scope.addEventListener('change',update);camera.addEventListener('change',update);chooseAsset();console.log('24 matched views; original ownership retained; 1392 static CCD shots passed');</script></body></html>'''.replace('PATHS',json.dumps(paths))
(OUT/'gallery.html').write_text(html)
(OUT/'final-verification.json').write_text(json.dumps(dict(summary=summary,geometry=proof,ccd=ccd,matched_images=24,artifact_sha256={p.name:hub.scan.digest(p)for p in OUT.iterdir()if p.is_file()and p.name!='final-verification.json'}),indent=2)+'\n');print('Verified proposal; saved',summary['placed_triangles_saved'],'placed triangles.')
