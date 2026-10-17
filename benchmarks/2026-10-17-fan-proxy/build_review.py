#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Show actual fan placements and the hollow rectangle/duct replacement."""
import argparse,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());views=['oblique','front','rear','reverse','side','top','bottom'];paths={stage:{view:str(out/(stage+'-'+view+'.png')) for view in views} for stage in ['source','proxy']}
    page='''<!doctype html><html><head><meta charset="utf-8"><style>body{font:14px var(--font-sans,system-ui);color:var(--foreground);line-height:1.5}h2{font-size:20px;margin:0 0 8px}p{color:var(--muted-foreground)}img{width:100%;border-radius:9px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}.stats div{padding:16px;background:var(--secondary);border-radius:10px}.stats b{display:block;font-size:24px}.stats span,.note,figcaption{font-size:12px;color:var(--muted-foreground)}.images{display:grid;grid-template-columns:1fr 1fr;gap:8px}figure{margin:0}select{padding:7px;background:var(--secondary);color:var(--foreground);border:1px solid var(--border);border-radius:7px;margin:5px 0 10px}@media(max-width:450px){.stats div{padding:10px}.stats b{font-size:19px}}</style></head><body><h2>Fan locations & hollow-box replacement</h2>
<p>Ten rectangular ventilation housings: <b>four in the high-point assemblies</b> (orange), plus <b>six standalone source fixtures</b> (blue). The numbered dots below use their actual transformed mesh centres.</p>
<img src="MAP"><div class="stats"><div><b>56</b><span>Triangles per replacement</span></div><div><b>560</b><span>Across all ten placements</span></div><div><b>99.86%</b><span>Triangle reduction</span></div></div>
<p>One thick hollow rectangular mounting frame and one open rectangular duct. Flange: 219 × 353.3 × 14 mm. Duct: 332 mm long, 165 × 299.3 mm outside, 3 mm walls. Both ends are open; the grille, perforations, crossbars and end panels are omitted.</p>
<select id="view">VIEWS</select><div class="images"><figure><img id="source"><figcaption>Original fan · 40,666 triangles</figcaption></figure><figure><img id="proxy"><figcaption>Hollow frame + duct · 56 triangles</figcaption></figure></div>
<p class="note">Fitted to source planes and the flange outline bounds; original placement and neutral fallback material retained. The proxy intentionally changes openings and corner detail; it is not a small-error simplification. The map background is schematic projected component bounds. Original source, approved assets and collision are unchanged.</p><script>const paths=PATHS;function update(){let view=document.querySelector('#view').value;for(let stage of ['source','proxy'])document.querySelector('#'+stage).src=paths[stage][view];}document.querySelector('#view').onchange=update;update();</script></body></html>'''
    page=page.replace('MAP',str(out/'locations.png')).replace('VIEWS',''.join(f'<option value="{v}">{v.title()} view</option>' for v in views)).replace('PATHS',json.dumps(paths));(out/'review.html').write_text(page)

if __name__=='__main__':main()
