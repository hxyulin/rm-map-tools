"""Consolidated review page; all counts are placed, alternative budgets."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/rmuc2027-box-hull-scenery-r2'


def main():
    eq=ROOT/'out/rmuc2027-box-hull-equipment-r2';rune=ROOT/'out/rmuc2027-box-hull-rune-r2'
    def pairs(folder,prefix,before='source',after='proxy',views=('oblique','reverse'),suffix='webp'):
        return {v:{'source':str(folder/f'{prefix}-{v}-{before}.{suffix}'),'proxy':str(folder/f'{prefix}-{v}-{after}.{suffix}')}for v in views}
    outpost=pairs(OUT,'outpost-one-block')
    outpost.update({'location-'+k:v for k,v in pairs(OUT,'outpost-all-three-context').items()})
    core={'plate':{'source':str(eq/'core-53-exact-hull-before.png'),'proxy':str(eq/'core-53-exact-hull-diagnostic-after.png')},
          'whole-Core location':{'source':str(eq/'core-all-context-before.png'),'proxy':str(eq/'core-all-context-diagnostic-after.png')}}
    rv=pairs(rune,'rune-123',before='before',after='diagnostic-after')
    rv['location']={'source':str(rune/'rune-123-context-before.webp'),'proxy':str(rune/'rune-123-context-diagnostic-after.webp')}
    dart=pairs(OUT,'dart-strip-end-detail',views=('face','oblique'))
    dart['location']={'source':str(OUT/'scenery-354-context-oblique-source.webp'),'proxy':str(OUT/'scenery-354-context-oblique-proxy.webp')}
    rows=[dict(label='Outpost closed blocks — strongest new fit',cost='1,224 → 120 placed mesh triangles',
        detail='Three blocks per Outpost, two placements: 1,104 mesh triangles saved. Native alternative: six hull leaves replace all 1,224 selected mesh triangles.',
        metric='Every hull facet is covered by the existing outward-facing source skin; uncovered area = 0 mm².',
        note='The reduction removes 176 buried triangles per block while retaining the outer profile, checked at 0.001 mm geometric tolerance. An ordinary box is also plausible with about 1 mm exterior change. Inside-origin queries and contacts still need validation.',views=outpost),
        dict(label='Tech Core arm — already-convex plates',cost='1,604 placed mesh triangles → 8 native hull leaves',
        detail='Four selected plates in each Core. Matching hull surfaces differ by less than 0.00005 mm in the fine sample checks; all other owner islands stay.',
        metric='This changes the physics representation with essentially matching selected surfaces.',
        note='Exact triangle-hull previews save zero triangles. A 0.5 mm approximation only saves 128 placed triangles, so native convex representation is the useful option here. The crucial Core face and all visuals stay unchanged.',views=core),
        dict(label='Rune support plates — conditional slot filling',cost='1,592 → 156 selected mesh triangles',
        detail='Three plates: 1,436 mesh triangles saved. Native alternative: three hulls; all 352 triangles in other islands of nodes 121/122 remain.',
        metric='Outer profiles retained; narrow fastener slots up to about 25 × 5 mm close. Sampled difference ≤2.46 mm.',
        note='The fastener-slot fill is deliberate and needs review. This is collision geometry; the protected Power Rune visual appearance remains unchanged.',views=rv),
        dict(label='Dart strands — optional detail coarsening',cost='2,900 → 252 placed mesh triangles',
        detail='Six bundles independently located across both Dart frames: potential saving 2,648 mesh triangles, or six native hulls.',
        metric='A hull fills the separation between three strands. This is a real local shape change, visible in the close-up.',
        note='About 127 × 8 × 4 mm per bundle; envelope recession ≤0.5 mm, sampled surface difference ~2.18 mm. Keep this below the structural candidates in priority. It does not simplify the main frame.',views=dart),
        dict(label='Rejected: one hull for an Energy unit',cost='Large count reduction, wrong external shape',
        detail='A whole-member convex hull fills the spool waist and socket. Separate pieces would be needed.',
        metric='About 45.63 mm forward and 20.62 mm reverse sampled differences.',
        note='A tight outer bounding volume cannot represent the concave profile. This remains a rejection.',views=pairs(OUT,'scenery-710-local')),
        dict(label='Rejected: one hull for resource mechanism',cost='Major opening filled',
        detail='The central port and other large gaps disappear under a whole-member hull.',
        metric='About 64.21 mm forward and 54.44 mm reverse sampled differences.',
        note='Keep the opening and decompose real members instead of hulling the complete mechanism.',views=pairs(OUT,'scenery-660-local'))]
    for row in rows:
        for pair in row['views'].values():
            for path in pair.values():assert Path(path).is_file(),path
    html='''<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:var(--font-sans,system-ui);line-height:1.45;color:var(--foreground)}p{margin:0 0 12px}.muted{color:var(--muted-foreground)}strong{font-weight:650}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}select{font:inherit;color:var(--foreground);background:var(--background);border:1px solid var(--border);border-radius:7px;padding:8px;max-width:100%}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.caption{font-size:13px;margin:0 0 5px}.box{aspect-ratio:1;border-radius:8px;overflow:hidden;background:#c5d5e3}.box img{width:100%;height:100%;object-fit:contain;display:block}.metric{background:var(--secondary);border-radius:var(--radius,10px);padding:16px;margin:14px 0}.metric p:last-child{margin-bottom:0}#cost{font-size:18px}table{width:100%;border-collapse:collapse;font-size:13px;margin:15px 0}td,th{text-align:left;border-bottom:1px solid var(--border);padding:9px 5px}small{font-size:12px}h3{font-size:16px;margin:20px 0 8px}
</style></head><body>
<p><strong>More fits found: closed blocks and convex cover plates are the cleanest new targets.</strong> Splitting parts by their real members preserves the large openings.</p>
<p class="muted">Collision-only research from the installed reference. All visuals remain unchanged; both full-asset mesh trials are uninstalled.</p>
<div class="controls"><select id="subject" aria-label="Candidate"></select><select id="view" aria-label="Comparison view"></select></div>
<p id="cost"></p><p class="muted" id="detail"></p><div class="pair"><div><p class="caption">Source collision geometry</p><div class="box"><img id="source" alt="Original collision surface"></div></div><div><p class="caption">Hull approximation</p><div class="box"><img id="proxy" alt="Proposed hull collision surface"></div></div></div>
<div class="metric"><p><strong id="metric"></strong></p><p id="note"></p></div>
<h3>New opportunities, ranked</h3><table><thead><tr><th>Area</th><th>Mesh preview saving</th><th>Native alternative</th><th>Review status</th></tr></thead><tbody>
<tr><td>Outpost blocks</td><td>1,104</td><td>6 hulls replace 1,224 triangles</td><td>Closed outer skin verified; interior removal</td></tr>
<tr><td>Core arm plates</td><td>0 for matching hulls</td><td>8 hulls replace 1,604 triangles</td><td>Already convex</td></tr>
<tr><td>Rune supports</td><td>1,436</td><td>3 hulls replace 1,592 triangles</td><td>Closes narrow fastener slots</td></tr>
<tr><td>Dart strands</td><td>2,648</td><td>6 hulls replace 2,900 triangles</td><td>Optional gap filling; lower priority</td></tr>
</tbody></table>
<p><strong>A useful reusable test:</strong> check that existing faces cover every outward hull facet, then remove buried geometry. This recovered the Outpost fits while rejecting a Core part whose coarse samples missed a 142 mm² opening.</p>
<p class="muted"><small>Counts are placed alternatives and are not approved savings. Native box/hull field import and verified partial-owner selection still need implementation; native backend shapes already exist. Contact, inside-origin query and runtime timing checks remain. Ground and important openings stay mesh-backed.</small></p>
<script>const rows=__ROWS__;const pick=document.getElementById('subject'),view=document.getElementById('view');rows.forEach((r,i)=>pick.add(new Option(r.label,i)));function show(){const r=rows[+pick.value];for(const k of ['cost','detail','metric','note'])document.getElementById(k).textContent=r[k];for(const k of ['source','proxy'])document.getElementById(k).src=r.views[view.value][k];}function choose(){view.replaceChildren();Object.keys(rows[+pick.value].views).forEach(k=>view.add(new Option(k,k)));show();}pick.onchange=choose;view.onchange=show;choose();console.log('Verified candidate image pairs',rows.reduce((s,r)=>s+Object.keys(r.views).length,0));</script>
</body></html>'''
    (OUT/'gallery.html').write_text(html.replace('__ROWS__',json.dumps(rows)))


if __name__=='__main__':main()
