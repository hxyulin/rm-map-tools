#!/usr/bin/env python3
"""Compare per-part OCCT tessellation (validation.json from validate_parts.py --mesh)
with the node meshes of a whole-file glb (RMUC2026_full.glb from the 9 h XDE run).

Matching is by node name == product name. Reports triangle-count ratio and
bounding-box delta (glb POSITION accessor min/max vs part vertex bbox).

Usage: compare_glb.py <pkg_dir> <file.glb>
"""
import sys, os, json, struct, collections


def load_glb(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, ver, length = struct.unpack_from('<III', data, 0)
    off = 12; chunks = []
    while off < length:
        clen, ctype = struct.unpack_from('<II', data, off); off += 8
        chunks.append((ctype, data[off:off + clen])); off += clen
    return json.loads(chunks[0][1])


def main():
    pkg, glb = sys.argv[1], sys.argv[2]
    js = load_glb(glb)
    val = json.load(open(os.path.join(pkg, 'validation.json')))
    # glb: name -> list of (triangles, vertices, bbox_min, bbox_max)
    by_name = collections.defaultdict(list)
    for n in js['nodes']:
        if 'mesh' not in n:
            continue
        tri = 0; vert = 0; mn = [float('inf')] * 3; mx = [-float('inf')] * 3
        for p in js['meshes'][n['mesh']]['primitives']:
            acc = js['accessors'][p['attributes']['POSITION']]
            vert += acc['count']
            if 'min' in acc:
                mn = [min(a, b) for a, b in zip(mn, acc['min'])]; mx = [max(a, b) for a, b in zip(mx, acc['max'])]
            if 'indices' in p:
                tri += js['accessors'][p['indices']]['count'] // 3
        by_name[n.get('name', '?')].append(dict(triangles=tri, vertices=vert, bbox_min=mn, bbox_max=mx))
    rows = []; unmatched = []
    for r in val['results']:
        if 'triangles' not in r:
            continue
        cands = by_name.get(r['name'])
        if not cands:
            unmatched.append(r['name']); continue
        g = cands[0]
        ratio = r['triangles'] / g['triangles'] if g['triangles'] else float('nan')
        if r['bbox_min'] and g['bbox_min'][0] != float('inf'):
            # glb from the XDE writer is metres; axes were kept Z-up (checked on BREP_1)
            gmn = [v / 1e3 for v in r['bbox_min']]; gmx = [v / 1e3 for v in r['bbox_max']]
            d = 1e3 * max(abs(a - b) for a, b in zip(gmn + gmx, g['bbox_min'] + g['bbox_max']))
        else:
            d = None
        rows.append((r['name'], r['triangles'], g['triangles'], ratio, d, len(cands)))
    ratios = [x[3] for x in rows if x[3] == x[3]]
    print(f'matched {len(rows)} parts, unmatched {len(unmatched)}: {unmatched[:10]}')
    print(f'triangle ratio part/glb: min {min(ratios):.3f} median {sorted(ratios)[len(ratios) // 2]:.3f} max {max(ratios):.3f}')
    within = sum(1 for x in ratios if 0.9 <= x <= 1.1)
    print(f'ratio within 10%: {within}/{len(ratios)}')
    ds = [x[4] for x in rows if x[4] is not None]
    print(f'bbox delta mm: max {max(ds):.3f}, >1mm: {sum(1 for d in ds if d > 1)}/{len(ds)}')
    print('worst triangle ratios:')
    for x in sorted(rows, key=lambda x: abs((x[3] if x[3] == x[3] else 1) - 1), reverse=True)[:12]:
        print(f'  {x[0]:40s} part {x[1]:8d} glb {x[2]:8d} ratio {x[3]:.3f} bbox_d {x[4]} instances {x[5]}')
    print('worst bbox deltas:')
    for x in sorted(rows, key=lambda x: -(x[4] or 0))[:8]:
        print(f'  {x[0]:40s} bbox_d {x[4]:.3f} mm')
    json.dump(dict(rows=rows, unmatched=unmatched), open(os.path.join(pkg, 'glb_compare.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
