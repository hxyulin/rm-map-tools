"""Build the self-contained collision investigation handoff page."""
import json
from pathlib import Path
from scan import ROOT, OUT


def main():
    rounded=ROOT/'out/rmuc2027-rounded-primitive-candidates'
    planar=ROOT/'out/rmuc2027-large-side-deviations'
    base=json.loads((planar/'panel-trial.json').read_text())
    base_error=max(base[k] for k in ['source_all_vertex_to_trial_max_mm',
                    'trial_all_vertex_to_source_max_mm','source_area_sample_max_mm',
                    'trial_area_sample_max_mm'])
    subjects=[
        dict(label='Base broad side — preserve the seams',cost=f"{base['source_triangles']:,} → {base['trial_triangles']:,} panel triangles",
             detail=f"Two Base placements: {base['hypothetical_placed_savings']:,} triangles saved by this local panel trial.",
             metric=f"~{base_error:.2f} mm maximum sampled surface difference; all {base['boundary_vertices_kept']} boundary positions retained exactly.",
             note='This removes shallow detail while retaining 12 boundary vertices and three interior attachment vertices exactly. Nine Base panel trials together offer 460 placed triangles of savings. Local trials only; no complete collision asset installed.',
             views={v:{s:str(planar/f'base-housing-local-{v}-{t}.png') for s,t in [('source','source'),('proxy','trial')]} for v in ['oblique','normal']}),
        dict(label='Dart thin plate — measured outline',cost='1,616 → 76 mesh triangles per plate',
             detail='Two plates: 3,080 mesh triangles saved; alternatively two native hulls with 40 vertices each replace all 3,232 source triangles.',
             metric='0.200 mm maximum inward outline loss. Filled holes/cap surfaces separately reach 6.611 mm sampled distance.',
             note='The broad shape remains close. Small holes are deliberately closed in this proposal. The 0.20 mm outline figure does not describe those fills. Hull field import still needs implementation.',
             views={v:{s:str(OUT/f'arena-static-260-profile-{v}-{s}.webp') for s in ['source','proxy']} for v in ['oblique','reverse']}),
        dict(label='Power Rune support — flat cylinder',cost='412 triangles → 1 native cylinder',
             detail='Strongest new rounded candidate. Three moderate Rune candidates bring the potential total to 2,528 triangles replaced by four cylinders.',
             metric='0.789 mm maximum sampled surface difference on the selected support.',
             note='Collision-only. The protected Power Rune visual assembly remains unchanged. Native cylinder import exists; moving ownership and contact review still apply.',
             views={v:{s:str(rounded/f'rune-node-22-{v}-{t}.webp') for s,t in [('source','before'),('proxy','diagnostic-after')]} for v in ['oblique','reverse']}),
        dict(label='Tech Core pedestal plate — box',cost='140 triangles → 1 native box per placement',
             detail='Two placements: 280 mesh triangles replaced by two boxes; a tessellated box preview would save 256 triangles.',
             metric='2.241 mm maximum sampled surface difference on a 288 × 282 × 2 mm plate.',
             note='The box fills small edge/opening details. The crucial Core head face stays unchanged. A field-sidecar box importer is still needed.',
             views={v:{s:str(OUT/f'tech-core-68-box-{v}-{s}.webp') for s in ['source','proxy']} for v in ['oblique','reverse']}),
        dict(label='Rejected: whole Outpost column hull',cost='11,302 triangles → 54 preview triangles',
             detail='Attractive count reduction, unacceptable shape loss.',
             metric='118.521 mm maximum sampled reverse difference; the hull fills the hollow frame.',
             note='Keep the opening. Use a few separate rails/walls or retain mesh. Do not use this whole-member hull.',
             views={v:{s:str(OUT/f'outpost-10-hull-{v}-{s}.webp') for s in ['source','proxy']} for v in ['oblique','reverse']}),
    ]
    for subject in subjects:
        for pair in subject['views'].values():
            for path in pair.values():assert Path(path).is_file(),path
    template='''<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:var(--font-sans,system-ui);color:var(--foreground);line-height:1.45}p{margin:0 0 12px}.muted{color:var(--muted-foreground)}strong{font-weight:650}select,button{font:inherit;color:var(--foreground);background:var(--background);border:1px solid var(--border);border-radius:7px;padding:8px;max-width:100%}.controls{display:flex;flex-wrap:wrap;gap:8px;margin:15px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.pair img{width:100%;display:block;border-radius:7px}.caption{font-size:13px;margin:0 0 5px}.metric{padding:16px;background:var(--secondary);border-radius:var(--radius,10px);margin:14px 0}.metric p:last-child{margin-bottom:0}table{border-collapse:collapse;width:100%;font-size:13px;margin:14px 0}td,th{text-align:left;padding:8px 5px;border-bottom:1px solid var(--border)}h3{font-size:16px;margin:20px 0 8px}small{font-size:12px}#cost{font-size:17px}.status{font-size:12px;color:var(--muted-foreground);margin-bottom:8px}
</style></head><body>
<p><strong>Yes: simplify shallow details while keeping the main profile and seams.</strong> These trials use the installed collision assets. Visual geometry remains unchanged.</p>
<p class="muted">Broad screening covered 574 dense rigid owners for boxes and 214 for rounded primitives; the searches overlap. Selected Base/Outpost/Dart sides received local panel review.</p>
<div class="controls"><select id="subject" aria-label="Candidate"></select><select id="view" aria-label="View"></select></div>
<p id="cost"></p><p class="muted" id="detail"></p><div class="pair"><div><p class="caption">Installed collision geometry</p><img id="before" alt="Original collision surface"></div><div><p class="caption">Diagnostic approximation</p><img id="after" alt="Proposed collision surface"></div></div>
<div class="metric"><p><strong id="metric"></strong></p><p id="note"></p></div>
<h3>Where the primitives fit</h3>
<table><thead><tr><th>Shape</th><th>Use</th><th>Current field import</th></tr></thead><tbody>
<tr><td>Box</td><td>Plates, rectangular beams and walls</td><td>Needs extension</td></tr>
<tr><td>Cylinder</td><td>Flat-ended round rods and discs</td><td>Implemented</td></tr>
<tr><td>Convex hull / profile</td><td>Tapers and clipped/rounded plate outlines</td><td>Needs extension</td></tr>
<tr><td>Sphere / capsule</td><td>True spherical or rounded-end parts</td><td>No strong fit found; capsule also needs engine work</td></tr>
<tr><td>Compound</td><td>A few rails/walls around an opening</td><td>Multiple cylinders supported; general leaves need extension</td></tr>
</tbody></table>
<p><strong>Use local error budgets.</strong> Measure normal depth, perimeter loss and filled openings separately. A 1 mm deviation may be small on a 500 mm panel but large on a 5 mm fitting. Keep real openings and contact edges.</p>
<p class="muted"><small>All trials remain uninstalled. Sampled distances are not continuous or contact bounds; ray/contact/pose checks and speed measurements remain. Floor/arena ground queries currently require meshes. No runtime or protected visual changes.</small></p>
<script>const rows=__ROWS__;const pick=document.getElementById('subject'),view=document.getElementById('view');rows.forEach((r,i)=>pick.add(new Option(r.label,i)));function show(){const r=rows[+pick.value],p=r.views[view.value];for(const k of ['cost','detail','metric','note'])document.getElementById(k).textContent=r[k];document.getElementById('before').src=p.source;document.getElementById('after').src=p.proxy;}function choose(){view.replaceChildren();Object.keys(rows[+pick.value].views).forEach(v=>view.add(new Option(v,v)));show();}pick.onchange=choose;view.onchange=show;choose();console.log('Candidate rows',rows.length,'source/proxy pairs',rows.reduce((s,r)=>s+Object.keys(r.views).length,0));</script>
</body></html>'''
    (OUT/'gallery.html').write_text(template.replace('__ROWS__',json.dumps(subjects)))


if __name__=='__main__':main()
