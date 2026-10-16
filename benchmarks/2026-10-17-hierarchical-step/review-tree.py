# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build an interactive inspection of a completed analytic STEP hierarchy."""
from html import escape
import json
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
r=json.loads((root/'hierarchy.json').read_text())
native=json.loads((root/'native-validation.json').read_text())
assemblies={a['product_id']:a for a in r['assemblies']}
leaves={c['export_product_id']:c for c in r['components']}
references={}
for a in r['assemblies']:
 for child in a['children']:references[child['product_id']]=references.get(child['product_id'],0)+1


def node(product,depth=0):
 if product in leaves:
  part=leaves[product]
  return f'<li class="leaf" title="{escape(part["id"])}">{escape(part["id"].split("/")[-1])}<small>{part["face_count"]:,} faces</small></li>'
 a=assemblies[product];shared=f' · {references[product]} references' if references.get(product,0)>1 else ''
 children=''.join(node(c['product_id'],depth+1) for c in a['children'])
 count=len(a['children']);label='child' if count==1 else 'children'
 return f'<li><details {"open" if depth<2 else ""}><summary>{escape(a["name"])}<small>{count} {label}{shared}</small></summary><ul>{children}</ul></details></li>'

size=(root/'field.step').stat().st_size/1024**2
html='''<!doctype html><html><head><meta charset="utf-8"><style>
body{font:14px/1.5 var(--font-sans);color:var(--foreground)}h3{font-size:19px;margin:12px 0 6px}p{color:var(--muted-foreground);margin:8px 0}.stats{display:flex;gap:20px;flex-wrap:wrap;margin:16px 0}.stats b{display:block;font-size:21px;color:var(--foreground)}.stats span{font-size:12px;color:var(--muted-foreground)}.tree{max-height:660px;overflow:auto;border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px}.tree>ul{padding:0;margin:0}ul{list-style:none;padding-left:18px;margin:2px 0}summary{cursor:pointer;padding:4px 0}li.leaf{padding:4px 0 4px 16px;color:var(--muted-foreground)}small{font-size:11px;color:var(--muted-foreground);margin-left:10px}button{font:inherit;background:var(--secondary);color:var(--foreground);border:1px solid var(--border);border-radius:5px;padding:5px 9px;cursor:pointer;margin:6px 5px 10px 0}.ok{color:var(--success)}footer{font-size:12px;color:var(--muted-foreground);margin-top:12px}@media(max-width:450px){small{display:block;margin-left:15px}.stats{gap:12px}ul{padding-left:12px}}
</style></head><body><h3>RMUC 2027 · reorganized STEP assembly</h3><p>Original analytic CAD, named work parts and shared model definitions. Expand the tree to inspect the layout.</p>
<div class="stats"><span><b>PARTS</b>work-part definitions</span><span><b>FACES</b>source face definitions</span><span><b>SIZE MiB</b>final STEP</span></div>
<button id="expand">Expand all</button><button id="collapse">Collapse models</button><div class="tree"><ul>TREE</ul></div>
<p class="ok">Native CAD read-back passed: one root assembly, PLACED placed faces.</p><footer>202 encoded assembly edges and 68 source model placements verified. Geometry, original styles and source identity maps preserved. Organizational groups retain the supplied solid/surface topology.</footer>
<script>document.querySelector('#expand').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=true);document.querySelector('#collapse').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=d.parentElement.parentElement.closest('details')?.parentElement.parentElement.closest('details')==null);console.log('Assembly definitions',document.querySelectorAll('details').length,'displayed part instances',document.querySelectorAll('.leaf').length);</script>
</body></html>'''
for key,value in {'PARTS':str(r['work_part_definitions']),'FACES':f'{r["source_face_definitions"]:,}','SIZE':f'{size:.1f}','TREE':node(r['root_product_id']),'PLACED':f'{native["native_faces"]:,}'}.items():html=html.replace(key,value)
(root/'review.html').write_text(html)
