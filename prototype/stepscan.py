import re, sys, collections
path = sys.argv[1]
head = re.compile(rb'^#(\d+)=([A-Z_0-9]*)\(')
ents = {}   # id -> (type, args bytes)
buf = b''
with open(path, 'rb') as f:
    for line in f:
        line = line.rstrip(b'\r\n')
        if buf:
            buf += line
            if not buf.endswith(b';'):
                continue
            line, buf = buf, b''
        elif line.startswith(b'#') and not line.endswith(b';'):
            buf = line; continue
        m = head.match(line)
        if not m: continue
        eid = int(m.group(1)); typ = m.group(2).decode() or 'CPLX'
        ents[eid] = (typ, line[m.end()-1:-1])
types = collections.Counter(t for t, _ in ents.values())
print('entities', len(ents))
print('types', [(k, v) for k, v in types.most_common() if k not in ('CARTESIAN_POINT','DIRECTION','VECTOR','LINE','VERTEX_POINT','EDGE_CURVE','ORIENTED_EDGE','EDGE_LOOP','FACE_BOUND','FACE_OUTER_BOUND','PLANE','CIRCLE','CYLINDRICAL_SURFACE','B_SPLINE_CURVE_WITH_KNOTS','B_SPLINE_SURFACE_WITH_KNOTS','AXIS2_PLACEMENT_3D','SURFACE_CURVE','PCURVE','DEFINITIONAL_REPRESENTATION','TRIMMED_CURVE','ELLIPSE','SPHERICAL_SURFACE','TOROIDAL_SURFACE','CONICAL_SURFACE','SEAM_CURVE','VERTEX_LOOP','BOUNDED_CURVE')])
refs = lambda a: [int(x) for x in re.findall(rb'#(\d+)', a)]
def colour_of(eid, depth=0):
    if eid not in ents or depth > 12: return None
    t, a = ents[eid]
    if t == 'COLOUR_RGB':
        return tuple(round(float(x), 3) for x in re.findall(rb'[-\d.E+]+', a.split(b',',1)[1]))
    if t == 'DRAUGHTING_PRE_DEFINED_COLOUR':
        return a.decode()
    for r in refs(a):
        c = colour_of(r, depth+1)
        if c is not None: return c
    return None
# products
prods = {eid: re.match(rb"\('([^']*)'", a).group(1).decode() for eid, (t, a) in ents.items() if t == 'PRODUCT'}
print('products', len(prods), sorted(set(prods.values()))[:80])
# styled items -> target colours
by_target = collections.Counter()
for eid, (t, a) in ents.items():
    if t in ('STYLED_ITEM', 'OVER_RIDING_STYLED_ITEM'):
        rs = refs(a)
        tgt = rs[-2] if t == 'OVER_RIDING_STYLED_ITEM' else rs[-1]
        ttype = ents.get(tgt, ('?',))[0]
        # colour: from style refs (exclude target)
        c = None
        for r in rs[:-1] if t == 'STYLED_ITEM' else rs[:-2]:
            c = colour_of(r)
            if c is not None: break
        by_target[(t, ttype, c)] += 1
print('styled by target/colour:')
for k, v in by_target.most_common(): print('  ', k, v)
# solids: colour of solid + set of face colours
face_colour = {}
solid_colour = {}
for eid, (t, a) in ents.items():
    if t == 'STYLED_ITEM':
        rs = refs(a); tgt = rs[-1]
        c = next((colour_of(r) for r in rs[:-1] if colour_of(r) is not None), None)
        if ents.get(tgt, ('?',))[0] == 'ADVANCED_FACE': face_colour[tgt] = c
        elif ents.get(tgt, ('?',))[0] == 'MANIFOLD_SOLID_BREP': solid_colour[tgt] = c
# ownership: solid -> representation -> product
rep_of = {}
for eid, (t, a) in ents.items():
    if t.endswith('SHAPE_REPRESENTATION') or t == 'SHAPE_REPRESENTATION':
        for r in refs(a): rep_of[r] = eid
prod_of_rep = {}
for eid, (t, a) in ents.items():
    if t == 'SHAPE_DEFINITION_REPRESENTATION':
        pds, rep = refs(a)
        pd = refs(ents[pds][1])[0] if ents[pds][0] == 'PRODUCT_DEFINITION_SHAPE' else None
        pdef = ents.get(pd)
        pf = refs(pdef[1])[0] if pdef else None
        prod = refs(ents[pf][1])[0] if pf in ents else None
        prod_of_rep[rep] = prods.get(prod, '?')
def faces_of_solid(sid):
    out = []
    stack = refs(ents[sid][1])
    seen = set()
    while stack:
        r = stack.pop()
        if r in seen or r not in ents: continue
        seen.add(r)
        t, a = ents[r]
        if t == 'ADVANCED_FACE': out.append(r)
        elif t in ('CLOSED_SHELL','OPEN_SHELL','ORIENTED_CLOSED_SHELL','SHELL_BASED_SURFACE_MODEL','BREP_WITH_VOIDS','MANIFOLD_SOLID_BREP'): stack.extend(refs(a))
    return out
print('solids by product with colours:')
rows = []
for sid, (t, a) in ents.items():
    if t in ('MANIFOLD_SOLID_BREP','BREP_WITH_VOIDS','SHELL_BASED_SURFACE_MODEL'):
        fs = faces_of_solid(sid)
        fc = collections.Counter(face_colour.get(f) for f in fs)
        prod = prod_of_rep.get(rep_of.get(sid), '?')
        name = re.match(rb"\('([^']*)'", a).group(1).decode()
        rows.append((prod, name, sid, solid_colour.get(sid), len(fs), dict(fc)))
for r in sorted(rows): print('  ', r)
