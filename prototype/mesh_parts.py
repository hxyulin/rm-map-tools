#!/usr/bin/env python3
"""Tessellate split part files with OCCT into one compact binary mesh bundle
for the web preview: per part, quantised uint16 positions, uint16 indices in
chunks of <= 65535 vertices, one colour index per triangle (effective face
colour from XCAF, fallback shell > solid > root), plus instance matrices from
the STEP assembly (identity for the arena, root-level transforms for the
equipment).

Usage: mesh_parts.py <pkg_dir> <index.npz> <out.bin> <out.json> [--lin 4] [--ang 0.5] [--only a,b] [--arena-only]
"""
import sys, os, json, time, argparse, struct, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p21index import Index
from p21model import Model, NUM_RE
from validate_parts import read_part, colour_key
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL, TopAbs_REVERSED
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.Quantity import Quantity_Color
from OCP.TopLoc import TopLoc_Location


def placement(ix, row):
    """AXIS2_PLACEMENT_3D row -> (origin, z axis, x axis)."""
    vals = []
    for r in ix.refs_of(row):
        rr = ix.r(int(r)); a = ix.args(rr)
        nums = NUM_RE.findall(a[a.index(b'('):]); vals.append(np.array([float(x) for x in nums[:3]]))
    while len(vals) < 3:
        vals.append(None)
    o, z, x = vals[0], vals[1], vals[2]
    if z is None: z = np.array([0., 0., 1.])
    if x is None: x = np.array([1., 0., 0.]) if abs(z[0]) < 0.9 else np.array([0., 1., 0.])
    z = z / np.linalg.norm(z); x = x - z * (x @ z); x = x / np.linalg.norm(x); y = np.cross(z, x)
    M = np.eye(4); M[:3, 0] = x; M[:3, 1] = y; M[:3, 2] = z; M[:3, 3] = o
    return M


def occurrence_transforms(ix, m):
    """product row -> list of 4x4 world matrices (one per occurrence path)."""
    t_idt = ix.tid.get('ITEM_DEFINED_TRANSFORMATION', -1); t_ax = ix.tid['AXIS2_PLACEMENT_3D']
    pds_nauo = {}
    for row in ix.rows_of('PRODUCT_DEFINITION_SHAPE'):
        rf = ix.refs_of(row)
        if len(rf) and ix.r(int(rf[0])) in m.nauo:
            pds_nauo[row] = ix.r(int(rf[0]))
    nauo_T = {}
    for row in ix.rows_of('CONTEXT_DEPENDENT_SHAPE_REPRESENTATION'):
        rf = ix.refs_of(row); rel = ix.r(int(rf[0])); pds = ix.r(int(rf[1]))
        nauo = pds_nauo.get(pds)
        if nauo is None: continue
        idt = next((ix.r(int(x)) for x in ix.refs_of(rel) if ix.types[ix.r(int(x))] == t_idt), None)
        if idt is None: continue
        axes = [ix.r(int(x)) for x in ix.refs_of(idt) if ix.types[ix.r(int(x))] == t_ax]
        if len(axes) == 2:
            nauo_T[nauo] = placement(ix, axes[1]) @ np.linalg.inv(placement(ix, axes[0]))
    out = collections.defaultdict(list)
    def walk(p, M):
        out[p].append(M)
        for nauo, c in m.children.get(p, []):
            if c is not None:
                walk(c, M @ nauo_T.get(nauo, np.eye(4)))
    for r in m.roots:
        walk(r, np.eye(4))
    return out


def tessellate(doc, lin, ang, min_face=0.0):
    """min_face: skip faces whose triangulation bbox diagonal is below this (mm) -- drops screws, chamfers, holes."""
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()); ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    roots = TDF_LabelSequence(); st.GetFreeShapes(roots)
    comp = TopoDS_Compound(); bb = BRep_Builder(); bb.MakeCompound(comp)
    root_shapes = [XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)) for i in range(1, roots.Length() + 1)]
    for s in root_shapes: bb.Add(comp, s)
    BRepMesh_IncrementalMesh(comp, lin, False, ang, True)
    faces = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(comp, TopAbs_FACE, faces)
    shells = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(comp, TopAbs_SHELL, shells)
    solids = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(comp, TopAbs_SOLID, solids)
    col = Quantity_Color(); body_of = {}
    for bodies in ([shells.FindKey(i) for i in range(1, shells.Extent() + 1)], [solids.FindKey(i) for i in range(1, solids.Extent() + 1)], root_shapes):
        for body in bodies:
            bc = colour_key(col) if (ct.GetColor(body, XCAFDoc_ColorSurf, col) or ct.GetColor(body, XCAFDoc_ColorGen, col)) else None
            ex = TopExp_Explorer(body, TopAbs_FACE)
            while ex.More():
                fi = faces.FindIndex(ex.Current())
                if body_of.get(fi) is None: body_of[fi] = bc
                ex.Next()
    pos = []; tris = []; tcol = []; colours = {}; nv = 0
    for i in range(1, faces.Extent() + 1):
        f = TopoDS.Face(faces.FindKey(i)); loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None: continue
        ck = colour_key(col) if (ct.GetColor(f, XCAFDoc_ColorSurf, col) or ct.GetColor(f, XCAFDoc_ColorGen, col)) else body_of.get(i)
        ci = colours.setdefault(ck, len(colours))
        trsf = loc.Transformation(); n = tri.NbNodes()
        P = np.empty((n, 3))
        for k in range(1, n + 1):
            p = tri.Node(k).Transformed(trsf); P[k - 1] = (p.X(), p.Y(), p.Z())
        if min_face and np.linalg.norm(P.max(0) - P.min(0)) < min_face: continue
        T = np.empty((tri.NbTriangles(), 3), np.int64)
        for k in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(k).Get(); T[k - 1] = (a, b, c)
        if f.Orientation() == TopAbs_REVERSED: T = T[:, [0, 2, 1]]
        pos.append(P); tris.append(T - 1 + nv); tcol.append(np.full(len(T), ci, np.uint8)); nv += n
    if not pos: return None
    return np.vstack(pos), np.vstack(tris), np.concatenate(tcol), [k for k, _ in sorted(colours.items(), key=lambda kv: kv[1])]


def chunk_and_pack(P, T, C, out):
    """write chunks of <=65535 verts: returns list of chunk dicts (offsets in bytes)."""
    chunks = []; start = 0
    while start < len(T):
        # greedily take triangles until unique verts would exceed 65535
        used = {}; end = start; order = []
        while end < len(T):
            tri = T[end]; new = [v for v in tri if v not in used]
            if len(used) + len(new) > 65535: break
            for v in new: used[v] = len(used); order.append(v)
            end += 1
        sub = T[start:end]; V = P[order]
        mn = V.min(0); ext = np.maximum(V.max(0) - mn, 1e-6)
        Q = np.round((V - mn) / ext * 65535).astype(np.uint16)
        I = np.vectorize(used.get)(sub).astype(np.uint16)
        rec = dict(vo=out.tell(), nv=len(V), origin=mn.round(3).tolist(), scale=ext.round(4).tolist())
        out.write(Q.tobytes()); rec['io'] = out.tell(); rec['nt'] = len(sub); out.write(I.tobytes())
        rec['co'] = out.tell(); out.write(C[start:end].tobytes())
        chunks.append(rec); start = end
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pkg'); ap.add_argument('index'); ap.add_argument('bin'); ap.add_argument('json')
    ap.add_argument('--lin', type=float, default=4.0); ap.add_argument('--ang', type=float, default=0.5)
    ap.add_argument('--only', default=None); ap.add_argument('--min-face', type=float, default=0.0); ap.add_argument('--arena-only', action='store_true')
    a = ap.parse_args()
    ix = Index(a.index); m = Model(ix); T = occurrence_transforms(ix, m)
    man = json.load(open(os.path.join(a.pkg, 'parts.json')))
    parts = man['parts']
    if a.only: want = set(a.only.split(',')); parts = [p for p in parts if p['name'] in want]
    if a.arena_only: parts = [p for p in parts if p['name'].startswith('BREP_')]
    prow = {int(ix.ids[r]): r for r in m.product_name}
    out = open(a.bin, 'wb'); recs = []; t0 = time.time(); ntri = 0
    for i, p in enumerate(parts):
        ts = time.time()
        doc, rd, err = read_part(os.path.join(a.pkg, p['file']))
        if err: print('skip', p['file'], err); continue
        # coarser tolerance for the huge equipment products so the bundle stays small
        k = 1 + 2 * np.log10(max(p['bytes'] / 20e6, 1))
        res = tessellate(doc, a.lin * k, min(a.ang * (1 + (k - 1) / 2), 1.0), a.min_face)
        del doc, rd
        if res is None: continue
        P, Tr, C, cols = res
        chunks = chunk_and_pack(P, Tr, C, out)
        inst = [M.round(6).T.flatten().tolist() for M in T.get(prow.get(p['product_id']), [np.eye(4)])]
        recs.append(dict(name=p['name'], id=p['product_id'], colours=cols, chunks=chunks, instances=inst, tris=int(len(Tr))))
        ntri += len(Tr)
        print(f"[{i + 1}/{len(parts)}] {p['name']}: {len(Tr)} tris, {len(cols)} colours, {len(inst)} inst, {time.time() - ts:.1f}s, total {ntri} tris {out.tell() / 1e6:.1f} MB", flush=True)
    out.close()
    json.dump(dict(lin=a.lin, ang=a.ang, parts=recs, triangles=ntri, bytes=os.path.getsize(a.bin), seconds=round(time.time() - t0, 1)), open(a.json, 'w'))
    print(f'{len(recs)} parts, {ntri} triangles, {os.path.getsize(a.bin) / 1e6:.1f} MB, {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
