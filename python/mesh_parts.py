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
from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideAngle
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder
from OCP.Poly import Poly_Triangulation, Poly_Triangle


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


def nauo_transforms(ix, m):
    """NEXT_ASSEMBLY_USAGE_OCCURRENCE row -> 4x4 child-to-parent matrix (identity when absent)."""
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
    return nauo_T


def occurrence_transforms(ix, m, nauo_T=None):
    """product row -> list of 4x4 world matrices (one per occurrence path)."""
    if nauo_T is None:
        nauo_T = nauo_transforms(ix, m)
    out = collections.defaultdict(list)
    def walk(p, M):
        out[p].append(M)
        for nauo, c in m.children.get(p, []):
            if c is not None:
                walk(c, M @ nauo_T.get(nauo, np.eye(4)))
    for r in m.roots:
        walk(r, np.eye(4))
    return out


def analytic_band(face, lin, ang):
    """Mesh a complete conical/cylindrical band from its exact STEP surface.

    Used only if OCCT's wire mesher fails. The UV span and exact surface area
    must describe a complete band; trimmed faces with holes are refused.
    """
    surface = BRepAdaptor_Surface(face)
    kind = surface.GetType()
    if kind not in (GeomAbs_Cone, GeomAbs_Cylinder):
        return None
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    if abs(u1 - u0 - 2 * np.pi) > 1e-7 or v1 <= v0:
        return None
    levels = [v0, v1]
    if kind == GeomAbs_Cone:
        cone = surface.Cone()
        slope = np.sin(cone.SemiAngle())
        radius = lambda v: cone.RefRadius() + v * slope
        apex = -cone.RefRadius() / slope
        if v0 < apex < v1:
            levels.insert(1, apex)
    else:
        radius = lambda v: surface.Cylinder().Radius()
    area = sum(np.pi * (abs(radius(a)) + abs(radius(b))) * (b - a)
               for a, b in zip(levels, levels[1:]))
    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, properties)
    if abs(abs(properties.Mass()) - area) > max(1e-7, area * 1e-5):
        return None
    rmax = max(abs(radius(v)) for v in levels)
    chord_angle = 2 * np.arccos(max(-1.0, 1 - min(lin, 0.01) / max(rmax, 1e-9)))
    segments = max(12, int(np.ceil(2 * np.pi / max(1e-4, min(ang, 0.2, chord_angle)))))
    if segments > 4096:
        return None
    triangles = []
    for row in range(len(levels) - 1):
        for col in range(segments):
            a = row * segments + col + 1
            b = row * segments + (col + 1) % segments + 1
            c, d = b + segments, a + segments
            if abs(radius(levels[row])) > 1e-9:
                triangles.append((a, b, c))
            if abs(radius(levels[row + 1])) > 1e-9:
                triangles.append((a, c, d))
    result = Poly_Triangulation(len(levels) * segments, len(triangles), False, False)
    for row, v in enumerate(levels):
        for col in range(segments):
            result.SetNode(row * segments + col + 1, surface.Value(u0 + (u1 - u0) * col / segments, v))
    for i, triangle in enumerate(triangles, 1):
        result.SetTriangle(i, Poly_Triangle(*triangle))
    return result


def face_meshes(face, lin, ang, stats):
    """Retry narrow faces, then split closed analytic surfaces without moving them."""
    def mesh_of(f):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        return f, tri, loc

    item = mesh_of(face)
    if item[1] is not None:
        return [item]
    BRepMesh_IncrementalMesh(face, min(lin, 0.01), False, min(ang, 0.2), False)
    item = mesh_of(face)
    if item[1] is not None:
        stats["fine_retries"] = stats.get("fine_retries", 0) + 1
        return [item]
    split = ShapeUpgrade_ShapeDivideAngle(1.5, face)
    split.Perform()
    shape = split.Result()
    BRepMesh_IncrementalMesh(shape, min(lin, 0.01), False, min(ang, 0.2), False)
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    items = [mesh_of(TopoDS.Face(faces.FindKey(i))) for i in range(1, faces.Extent() + 1)]
    if items and all(item[1] is not None for item in items):
        stats["split_retries"] = stats.get("split_retries", 0) + 1
        return items
    band = analytic_band(face, lin, ang)
    if band is not None:
        stats["analytic_bands"] = stats.get("analytic_bands", 0) + 1
        return [(face, band, TopLoc_Location())]
    BRepMesh_IncrementalMesh(face, 0.0001, False, min(ang, 0.1), False)
    item = mesh_of(face)
    if item[1] is not None:
        stats["narrow_face_retries"] = stats.get("narrow_face_retries", 0) + 1
        return [item]
    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, properties)
    if abs(properties.Mass()) < 1e-8:
        stats["degenerate_faces"] = stats.get("degenerate_faces", 0) + 1
        return []
    stats.setdefault("unmeshed_details", []).append({
        "surface": str(BRepAdaptor_Surface(face).GetType()), "area_mm2": properties.Mass()})
    stats["unmeshed_faces"] = stats.get("unmeshed_faces", 0) + 1
    return []


def tessellate(doc, lin, ang, stats=None, face_observer=None):
    """Tessellate every source face at the requested tolerance."""
    stats = {} if stats is None else stats
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()); ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    roots = TDF_LabelSequence(); st.GetFreeShapes(roots)
    comp = TopoDS_Compound(); bb = BRep_Builder(); bb.MakeCompound(comp)
    root_shapes = [XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)) for i in range(1, roots.Length() + 1)]
    for s in root_shapes: bb.Add(comp, s)
    # OCCT otherwise retains an earlier, finer mesh when requesting a coarser LOD.
    BRepTools.Clean_s(comp)
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
        f = TopoDS.Face(faces.FindKey(i))
        ck = colour_key(col) if (ct.GetColor(f, XCAFDoc_ColorSurf, col) or ct.GetColor(f, XCAFDoc_ColorGen, col)) else body_of.get(i)
        ci = colours.setdefault(ck, len(colours))
        pieces = face_meshes(f, lin, ang, stats)
        if face_observer is not None:
            face_observer(i, f, sum(tri.NbTriangles() for _, tri, _ in pieces))
        for piece, tri, loc in pieces:
            trsf = loc.Transformation(); n = tri.NbNodes()
            P = np.empty((n, 3))
            for k in range(1, n + 1):
                p = tri.Node(k).Transformed(trsf); P[k - 1] = (p.X(), p.Y(), p.Z())
            T = np.empty((tri.NbTriangles(), 3), np.int64)
            for k in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(k).Get(); T[k - 1] = (a, b, c)
            if piece.Orientation() == TopAbs_REVERSED: T = T[:, [0, 2, 1]]
            pos.append(P); tris.append(T - 1 + nv); tcol.append(np.full(len(T), ci, np.uint8)); nv += n
    if not pos: return None
    return np.vstack(pos), np.vstack(tris), np.concatenate(tcol), [k for k, _ in sorted(colours.items(), key=lambda kv: kv[1])]



def tessellate_pair(doc, settings, stats=None):
    """Mesh the same source faces independently; never substitute collision shapes.

    Keep source body, face-color and articulation membership unchanged. Clearing
    cached triangulations in tessellate makes each tolerance order-independent.
    """
    stats = {} if stats is None else stats
    meshes = {}
    for kind in ('visual', 'collision'):
        if kind == 'collision' and not settings.get('collision_enabled', True):
            fine = meshes['visual']
            meshes[kind] = None if fine is None else (fine[0], fine[1][:0], fine[2][:0], fine[3])
            stats[kind] = {'excluded': True, 'visual_triangles': 0 if fine is None else len(fine[1])}
            continue
        if kind == 'collision' and (settings['collision_mode'] == 'visual'
                                    or settings['collision'] == settings['visual']):
            meshes[kind] = meshes['visual']
            stats[kind] = dict(stats['visual'])
            continue
        params = settings[kind]
        detail = stats.setdefault(kind, {})
        meshes[kind] = tessellate(doc, params['linear_deflection_mm'],
                                 params['angular_deflection_rad'], stats=detail)
        if detail.get('unmeshed_faces') or meshes[kind] is None:
            # A complete finer visual mesh is a conservative collider fallback.
            # Never use a partial mesh or relax a requested collision tolerance.
            if (kind == 'collision' and meshes.get('visual') is not None
                    and all(settings['visual'][key] <= params[key] for key in
                            ('linear_deflection_mm', 'angular_deflection_rad'))):
                detail['fallback_to_visual'] = True
                detail['effective_tolerance'] = dict(settings['visual'])
                meshes[kind] = meshes['visual']
            else:
                raise ValueError(f"{kind}: {detail.get('unmeshed_faces', 0)} source faces could not be tessellated")
    return meshes['visual'], meshes['collision']


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
    ap.add_argument('--only', default=None); ap.add_argument('--arena-only', action='store_true')
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
        res = tessellate(doc, a.lin, a.ang)
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
