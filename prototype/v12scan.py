import re, sys, collections, json
path = "/Users/hxyulin/Downloads/UTF-8__RMUC2026_V1.2.0.step"
head = re.compile(rb'^#(\d+)=([A-Z_0-9]*)\(')
SKIP = {b'CARTESIAN_POINT', b'DIRECTION', b'VECTOR', b'AXIS2_PLACEMENT_3D', b'PLANE', b'CIRCLE', b'LINE', b'ELLIPSE',
        b'CYLINDRICAL_SURFACE', b'CONICAL_SURFACE', b'SPHERICAL_SURFACE', b'TOROIDAL_SURFACE',
        b'B_SPLINE_CURVE_WITH_KNOTS', b'B_SPLINE_SURFACE_WITH_KNOTS', b'SURFACE_CURVE', b'PCURVE', b'SEAM_CURVE',
        b'DEFINITIONAL_REPRESENTATION', b'TRIMMED_CURVE', b'DERIVED_UNIT', b'DERIVED_UNIT_ELEMENT',
        b'MEASURE_REPRESENTATION_ITEM', b'DESCRIPTIVE_REPRESENTATION_ITEM', b'PROPERTY_DEFINITION',
        b'PROPERTY_DEFINITION_REPRESENTATION', b'REPRESENTATION', b'UNCERTAINTY_MEASURE_WITH_UNIT'}
ents = {}
buf = b''
def feed(line):
    m = head.match(line)
    if not m: return
    if m.group(2) in SKIP: return
    ents[int(m.group(1))] = (m.group(2).decode() or 'CPLX', line[m.end()-1:-1])
with open(path, 'rb') as f:
    for line in f:
        line = line.rstrip(b'\r\n')
        if buf:
            buf += line
            if not buf.endswith(b';'): continue
            line, buf = buf, b''
        elif line.startswith(b'#') and not line.endswith(b';'):
            buf = line; continue
        feed(line)
print('kept entities', len(ents), flush=True)
refs = lambda a: [int(x) for x in re.findall(rb'#(\d+)', a)]
name_of = lambda a: (re.match(rb"\('([^']*)'", a) or re.match(rb"\((\S*?),", a)).group(1).decode(errors='replace')
def colour_of(eid, depth=0):
    if eid not in ents or depth > 10: return None
    t, a = ents[eid]
    if t == 'COLOUR_RGB': return name_of(a)
    if t == 'DRAUGHTING_PRE_DEFINED_COLOUR': return a.decode()
    for r in refs(a):
        c = colour_of(r, depth+1)
        if c is not None: return c
# vertex points wanted
want_pts = set()
for eid, (t, a) in ents.items():
    if t == 'VERTEX_POINT': want_pts.update(refs(a))
print('vertex points', len(want_pts), flush=True)
pts = {}
with open(path, 'rb') as f:
    for line in f:
        if line.startswith(b'#') and b'=CARTESIAN_POINT(' in line:
            m = head.match(line)
            eid = int(m.group(1))
            if eid in want_pts:
                pts[eid] = tuple(float(x) for x in re.findall(rb'[-\d.E+]+', line[m.end():].split(b',', 1)[1]))
print('points loaded', len(pts), flush=True)
# styles
target_colour = {}
by_kind = collections.Counter()
for eid, (t, a) in ents.items():
    if t in ('STYLED_ITEM', 'OVER_RIDING_STYLED_ITEM'):
        rs = refs(a)
        tgt = rs[-2] if t == 'OVER_RIDING_STYLED_ITEM' else rs[-1]
        styles = rs[:-2] if t == 'OVER_RIDING_STYLED_ITEM' else rs[:-1]
        c = next((colour_of(r) for r in styles if colour_of(r) is not None), None)
        target_colour[tgt] = c
        by_kind[(t, ents.get(tgt, ('?',))[0], c)] += 1
print('styled by kind/colour:')
for k, v in by_kind.most_common(): print('  ', k, v)
# products and ownership
prods = {eid: name_of(a) for eid, (t, a) in ents.items() if t == 'PRODUCT'}
pdef_prod = {}
for eid, (t, a) in ents.items():
    if t == 'PRODUCT_DEFINITION_FORMATION': pdef_prod[eid] = refs(a)[0]
pd_prod = {eid: prods.get(pdef_prod.get(refs(a)[0])) for eid, (t, a) in ents.items() if t == 'PRODUCT_DEFINITION'}
rep_prod = {}
for eid, (t, a) in ents.items():
    if t == 'SHAPE_DEFINITION_REPRESENTATION':
        pds, rep = refs(a)
        pd = refs(ents[pds][1])[0]
        rep_prod[rep] = pd_prod.get(pd)
for eid, (t, a) in ents.items():
    if t == 'SHAPE_REPRESENTATION_RELATIONSHIP':
        r1, r2 = refs(a)[:2]
        if r2 not in rep_prod and r1 in rep_prod: rep_prod[r2] = rep_prod[r1]
        if r1 not in rep_prod and r2 in rep_prod: rep_prod[r1] = rep_prod[r2]
body_rep = {}
for eid, (t, a) in ents.items():
    if t in ('ADVANCED_BREP_SHAPE_REPRESENTATION', 'SHAPE_REPRESENTATION', 'MANIFOLD_SURFACE_SHAPE_REPRESENTATION', 'CPLX'):
        for r in refs(a):
            if ents.get(r, ('?',))[0] in ('MANIFOLD_SOLID_BREP', 'BREP_WITH_VOIDS', 'SHELL_BASED_SURFACE_MODEL'): body_rep[r] = eid
# assembly tree
children = collections.defaultdict(list)
for eid, (t, a) in ents.items():
    if t == 'NEXT_ASSEMBLY_USAGE_OCCURRENCE':
        rs = refs(a); children[pd_prod.get(rs[0])].append(pd_prod.get(rs[1]))
all_children = {c for v in children.values() for c in v}
roots = [p for p in children if p not in all_children]
print('roots', roots)
def tree(p, d=0):
    cnt = collections.Counter(children.get(p, []))
    for c, n in cnt.items():
        print('  '*d + f'{c} x{n} ({len(children.get(c,[]))} children)')
        if d < 2: tree(c, d+1)
for r in roots: print(r); tree(r)
# bodies
TOPO = ('CLOSED_SHELL','OPEN_SHELL','ORIENTED_CLOSED_SHELL','SHELL_BASED_SURFACE_MODEL','BREP_WITH_VOIDS','MANIFOLD_SOLID_BREP',
        'FACE_OUTER_BOUND','FACE_BOUND','EDGE_LOOP','ORIENTED_EDGE','EDGE_CURVE','VERTEX_POINT','VERTEX_LOOP')
rows = []
for sid, (t, a) in ents.items():
    if t not in ('MANIFOLD_SOLID_BREP','BREP_WITH_VOIDS','SHELL_BASED_SURFACE_MODEL'): continue
    faces = []; P = []
    stack = [sid]; seen = set()
    while stack:
        r = stack.pop()
        if r in seen or r not in ents: continue
        seen.add(r); tt, aa = ents[r]
        if tt == 'ADVANCED_FACE': faces.append(r); stack.extend(refs(aa)[:-1])
        elif tt == 'VERTEX_POINT':
            for q in refs(aa):
                if q in pts: P.append(pts[q])
        elif tt in TOPO: stack.extend(refs(aa))
    fc = collections.Counter(target_colour.get(f) for f in faces)
    bc = target_colour.get(sid)
    if P:
        mn = [min(p[i] for p in P) for i in range(3)]; mx = [max(p[i] for p in P) for i in range(3)]
    else: mn = mx = [0,0,0]
    rows.append(dict(id=sid, type=t, product=rep_prod.get(body_rep.get(sid)), body_colour=bc, faces=len(faces),
                     face_colours={str(k): v for k, v in fc.items()}, min=[round(x) for x in mn], max=[round(x) for x in mx]))
json.dump(rows, open('v12_bodies.json', 'w'), indent=0)
print('bodies', len(rows))
rows.sort(key=lambda r: -max(r['max'][i]-r['min'][i] for i in range(3)))
print('largest 60 bodies:')
for r in rows[:60]:
    ext = [r['max'][i]-r['min'][i] for i in range(3)]
    print('  ', r['type'][:12], r['product'], 'body', r['body_colour'], 'faces', r['faces'], 'ext', ext, 'zrange', r['min'][2], r['max'][2], r['face_colours'])
