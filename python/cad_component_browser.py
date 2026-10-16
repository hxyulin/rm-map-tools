#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render a standalone, offline source-component catalog browser; no CAD geometry is embedded."""
import argparse
import json
from pathlib import Path


def render(catalog, initial=None):
    """Render source selectors and occurrence counts without mutating the catalog."""
    data = {k: catalog[k] for k in ('summary', 'assemblies', 'groups', 'components')}
    data['occurrences'] = [{k: value for k, value in occurrence.items() if k != 'source_world_matrix'}
                           for occurrence in catalog['occurrences']]
    html = r'''<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font-family:var(--font-sans,system-ui);color:var(--foreground,#222)}h3{font-size:18px;margin:0 0 8px}p{font-size:13px;line-height:1.5;color:var(--muted-foreground,#777)}.controls{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 10px}select,input{font:inherit;max-width:100%;box-sizing:border-box;padding:9px;border:1px solid var(--border,#aaa);border-radius:6px;color:var(--foreground,#222);background:var(--background,transparent)}input{flex:1;min-width:180px}select{width:290px}.scroll{max-height:330px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:9px 8px 9px 0;text-align:left;border-bottom:1px solid var(--border,#ccc);vertical-align:top}th{position:sticky;top:0;background:var(--background,#fff);font-weight:500;color:var(--muted-foreground,#777)}td:nth-child(2){overflow-wrap:anywhere}tbody tr{cursor:pointer}tbody tr:hover{background:var(--accent-surface,#eee)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.5;max-height:140px;overflow:auto;padding:16px;background:var(--code-background,#eee);color:var(--code-foreground,inherit);border-radius:8px}#count{font-size:13px;margin:8px 0;color:var(--muted-foreground,#777)}.stats{display:flex;gap:25px;flex-wrap:wrap}.stats b{font-size:24px;display:block}.stats span{font-size:13px;color:var(--muted-foreground,#777)}
</style></head><body><h3>Source CAD component work catalog</h3><div class="stats"><div><b id="definitions">—</b><span>body definitions</span></div><div><b id="placed">—</b><span>placed bodies</span></div><div><b id="manual">—</b><span>manual groups</span></div></div><p>Browse an assembly or work group; select a row to get its stable source selector. This is a source-component inventory, not a geometry preview.</p><div class="controls"><select id="selection" aria-label="Assembly or work group"></select><input id="search" placeholder="Filter by body ID, group or motion…" aria-label="Filter components"></div><div id="count"></div><div class="scroll"><table><thead><tr><th>Source body</th><th>Work group</th><th>CAD faces</th><th>Motion</th><th>Placed</th></tr></thead><tbody id="rows"></tbody></table></div><pre id="detail">Select a component to inspect its identity and export selector.</pre><p>Work groups preserve original geometry and per-face styles. Unknown motion remains unknown; no runtime package changes. Export a leaf or single-product group as an isolated STEP work item, retaining placements in its sidecar.</p><script>
const catalog=CATALOG;
document.getElementById('definitions').textContent=catalog.summary.component_definitions;
document.getElementById('placed').textContent=catalog.summary.placed_component_occurrences;
document.getElementById('manual').textContent=catalog.summary.manual_groups;
const select=document.getElementById('selection'), search=document.getElementById('search');
const groupNames=new Set(catalog.groups.map(g=>g.id));for(const g of catalog.groups){const parts=g.id.split('/');for(let i=2;i<parts.length;i++)groupNames.add(parts.slice(0,i).join('/'));}
for(const a of [...catalog.assemblies].sort((a,b)=>a.name.localeCompare(b.name))) select.add(new Option(a.name,a.name));
for(const g of [...groupNames].sort()) select.add(new Option('  '+g,g));select.value=INITIAL_SELECTOR||(catalog.assemblies.some(a=>a.name==='base')?'base':catalog.assemblies[0].name);if(select.selectedIndex<0)select.selectedIndex=0;
function selection(){const a=catalog.assemblies.find(a=>a.name===select.value);let os;if(a)os=catalog.occurrences.filter(o=>o.ancestor_product_ids.includes(a.product_id));else{const ids=new Set(catalog.components.filter(c=>c.group===select.value||c.group.startsWith(select.value+'/')).map(c=>c.id));os=catalog.occurrences.filter(o=>ids.has(o.component_id));}return os;}
function render(){const os=selection(),counts=new Map();for(const o of os)counts.set(o.component_id,(counts.get(o.component_id)||0)+1);const q=search.value.toLowerCase();const cs=catalog.components.filter(c=>counts.has(c.id)&&[c.body_id,c.group,c.motion,c.motion_owner,c.id].join(' ').toLowerCase().includes(q));document.getElementById('count').textContent=cs.length+' component definitions shown · '+cs.reduce((n,c)=>n+counts.get(c.id),0)+' placed bodies';const rows=document.getElementById('rows');rows.replaceChildren();for(const c of cs){const tr=document.createElement('tr');for(const text of ['#'+c.body_id,c.group+(c.group_review_status==='spatial-candidate'?' [candidate]':''),c.source_faces,c.motion,counts.get(c.id)]){const td=document.createElement('td');td.textContent=text;tr.append(td);}tr.onclick=()=>{document.getElementById('detail').textContent='Selector: '+c.id+'\nGroup: '+c.group+'\nGroup review: '+(c.group_review_status||'unreviewed')+'\nProduct: #'+c.product_id+' · motion owner: '+c.motion_owner+'\nOriginal source paths: '+os.filter(o=>o.component_id===c.id).map(o=>o.occurrence_path.join('/')).join(', ')+'\n\nExport with: --select '+c.id+' --export-step --out <new-work-directory>';};rows.append(tr);}document.getElementById('detail').textContent='Select a component to inspect its identity and export selector.';}
select.onchange=render;search.oninput=render;render();console.log('Catalog: '+catalog.components.length+' definitions, '+catalog.occurrences.length+' placed bodies');
</script></body></html>'''
    html = html.replace('INITIAL_SELECTOR', json.dumps(initial).replace('<', '\\u003c'))
    return html.replace('CATALOG', json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--initial', help='initial assembly or group selector')
    args = parser.parse_args()
    html = render(json.loads(args.catalog.read_text()), args.initial)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        stream.write(html)


if __name__ == '__main__':
    main()
