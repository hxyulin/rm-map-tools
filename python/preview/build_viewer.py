#!/usr/bin/env python3
"""build_viewer.py <config.json> <bundle>[:arena] ...

Merges mesh bundles written by mesh_parts.py (later bundles override parts by
product id; a ':arena' suffix keeps only BREP_ parts of that bundle), pads
chunks to 2-byte alignment, deflates + base64s the binary and fills
viewer_tpl.html (next to this script). Bundle names are paths without the
.bin/.json extension; the page is written next to the config as cfg['out'].
"""
import json, os, sys, zlib, base64, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(sys.argv[1])); OUT_DIR = os.path.dirname(os.path.abspath(sys.argv[1]))
bundles = []
for spec in sys.argv[2:]:
    name, _, flt = spec.partition(':')
    meta = json.load(open(f'{name}.json'))
    if flt == 'arena': meta['parts'] = [p for p in meta['parts'] if p['name'].startswith('BREP_')]
    bundles.append((meta, open(f'{name}.bin', 'rb').read()))
by_id = {}
for bi, (meta, _) in enumerate(bundles):
    for p in meta['parts']: by_id[p['id']] = (bi, p)
out = bytearray(); parts = []
for pid, (bi, p) in sorted(by_id.items(), key=lambda kv: kv[1][1]['name']):
    src = bundles[bi][1]; chunks = []
    for c in p['chunks']:
        c = dict(c); vo, io, co = c['vo'], c['io'], c['co']
        if len(out) % 2: out += b'\0'
        c['vo'] = len(out); out += src[vo:vo + c['nv'] * 6]
        c['io'] = len(out); out += src[io:io + c['nt'] * 6]
        c['co'] = len(out); out += src[co:co + c['nt']]
        chunks.append(c)
    parts.append(dict(p, chunks=chunks))
# floor top: the arena part with the largest XY footprint (world), its max z (mm)
def world_box(p):
    mn = np.full(3, 1e18); mx = -mn
    for c in p['chunks']:
        for i in p['instances']:
            M = np.array(i).reshape(4, 4).T; o = np.array(c['origin']); s = np.array(c['scale'])
            for k in range(8):
                w = M @ np.append(o + s * np.array([k & 1, (k >> 1) & 1, (k >> 2) & 1]), 1)
                mn = np.minimum(mn, w[:3]); mx = np.maximum(mx, w[:3])
    return mn, mx
arena = [p for p in parts if p['name'].startswith('BREP_')]
boxes = {p['name']: world_box(p) for p in arena}
floor_name = max(boxes, key=lambda n: (boxes[n][1][0] - boxes[n][0][0]) * (boxes[n][1][1] - boxes[n][0][1]))
floor_top = float(boxes[floor_name][1][2])
meta = dict(parts=parts, triangles=sum(p['tris'] for p in parts), bytes=len(out), seconds=sum(b[0]['seconds'] for b in bundles), floor=floor_name)
z = zlib.compress(bytes(out), 9); b64 = base64.b64encode(z).decode()
html = open(os.path.join(HERE, 'viewer_tpl.html')).read()
for k, v in cfg.items():
    if k.startswith('__'): html = html.replace(k, v)
html = html.replace('__META__', json.dumps(meta, separators=(',', ':'))).replace('__B64__', b64).replace('__FLOOR_TOP__', f'{floor_top:.1f}')
open(os.path.join(OUT_DIR, cfg['out']), 'w').write(html)
print(f"{len(parts)} parts, {meta['triangles']} tris, raw {len(out)/1e6:.1f} MB, deflate {len(z)/1e6:.1f} MB, html {len(html)/1e6:.1f} MB, floor {floor_name} top z={floor_top:.1f} mm -> {cfg['out']}")
