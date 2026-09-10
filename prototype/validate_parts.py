#!/usr/bin/env python3
"""Validate split part files with OCCT (via cadquery-ocp).

For every part in <pkg>/parts.json: read with STEPCAFControl_Reader, then
compare against the text-scan manifest:
  * number of faces (unique TopoDS_Face)
  * bounding box of vertices (exact points, not Bnd_Box)
  * face colour histogram (face colour, else body colour)
Also records read time, optional tessellation time/triangle count, and RSS.

Usage: validate_parts.py <pkg_dir> [--mesh] [--limit N] [--only name,...]
Writes <pkg_dir>/validation.json and prints a summary.
"""
import sys, os, json, time, argparse, resource, collections
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX, TopAbs_SOLID, TopAbs_SHELL, TopAbs_COMPOUND
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB, Quantity_TOC_RGB
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopLoc import TopLoc_Location
from OCP.Poly import Poly_Triangulation


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def colour_key(col):
    r, g, b = col.Values(Quantity_TOC_sRGB)
    return f'{r:.4f},{g:.4f},{b:.4f}'


def read_part(path):
    doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    rd = STEPCAFControl_Reader()
    rd.SetColorMode(True); rd.SetNameMode(True); rd.SetLayerMode(True)
    st = rd.ReadFile(path)
    if st != IFSelect_RetDone:
        return None, None, f'read status {st}'
    ok = rd.Transfer(doc)
    if not ok:
        return None, None, 'transfer failed'
    return doc, rd, None


def analyse(doc, mesh=False):
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    roots = TDF_LabelSequence(); st.GetFreeShapes(roots)
    comp = TopoDS_Compound(); bb = BRep_Builder(); bb.MakeCompound(comp)
    for i in range(1, roots.Length() + 1):
        bb.Add(comp, XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)))
    faces = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(comp, TopAbs_FACE, faces)
    verts = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(comp, TopAbs_VERTEX, verts)
    solids = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(comp, TopAbs_SOLID, solids)
    shells = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(comp, TopAbs_SHELL, shells)
    mn = [float('inf')] * 3; mx = [-float('inf')] * 3
    for i in range(1, verts.Extent() + 1):
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(verts.FindKey(i)))
        for k, v in enumerate((p.X(), p.Y(), p.Z())):
            mn[k] = min(mn[k], v); mx[k] = max(mx[k], v)
    # colours: face colour, else colour of the owning solid/shell
    col = Quantity_Color(); hist = collections.Counter()
    body_of = {}
    root_shapes = [XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)) for i in range(1, roots.Length() + 1)]
    # nearest coloured ancestor wins: shell, then solid, then the free root shape
    # (a BREP_WITH_VOIDS or multi-shell sheet body becomes a coloured compound)
    for bodies in (
        [shells.FindKey(i) for i in range(1, shells.Extent() + 1)],
        [solids.FindKey(i) for i in range(1, solids.Extent() + 1)],
        root_shapes,
    ):
        for body in bodies:
            bc = None
            if ct.GetColor(body, XCAFDoc_ColorSurf, col) or ct.GetColor(body, XCAFDoc_ColorGen, col):
                bc = colour_key(col)
            ex = TopExp_Explorer(body, TopAbs_FACE)
            while ex.More():
                fi = faces.FindIndex(ex.Current())   # stable key: index in the face map
                if body_of.get(fi) is None:
                    body_of[fi] = bc
                ex.Next()
    for i in range(1, faces.Extent() + 1):
        f = faces.FindKey(i)
        if ct.GetColor(f, XCAFDoc_ColorSurf, col) or ct.GetColor(f, XCAFDoc_ColorGen, col):
            hist[colour_key(col)] += 1
        else:
            hist[str(body_of.get(i))] += 1
    out = dict(faces=faces.Extent(), vertices=verts.Extent(), solids=solids.Extent(), shells=shells.Extent(),
               roots=roots.Length(), bbox_min=[round(v, 4) for v in mn] if verts.Extent() else None,
               bbox_max=[round(v, 4) for v in mx] if verts.Extent() else None,
               face_colours=dict(hist))
    if mesh:
        t = time.time()
        BRepMesh_IncrementalMesh(comp, 1.0, False, 0.35, True)
        tris = 0; mverts = 0
        for i in range(1, faces.Extent() + 1):
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(TopoDS.Face(faces.FindKey(i)), loc)
            if tri is not None:
                tris += tri.NbTriangles(); mverts += tri.NbNodes()
        out.update(mesh_seconds=round(time.time() - t, 3), triangles=tris, mesh_vertices=mverts)
    return out


def expected(part):
    faces = sum(b['faces'] for b in part['bodies'])
    faces += sum(b.get('extra_outer_bounds', 0) for b in part['bodies'])  # OCCT splits multi-outer-wire faces
    hist = collections.Counter()
    mn = [float('inf')] * 3; mx = [-float('inf')] * 3
    for b in part['bodies']:
        for k, n in b['face_colours'].items():
            hist[k] += n  # manifest colours are already effective (face > shell > body)
        if b['bbox_min']:
            mn = [min(a, c) for a, c in zip(mn, b['bbox_min'])]
            mx = [max(a, c) for a, c in zip(mx, b['bbox_max'])]
    return dict(faces=faces, face_colours=dict(hist),
                bbox_min=mn if mn[0] != float('inf') else None, bbox_max=mx if mx[0] != -float('inf') else None)


def compare(exp, got, tol=1e-3):
    issues = []
    if exp['faces'] != got['faces']:
        issues.append(f"faces {exp['faces']} != {got['faces']}")
    if exp['bbox_min'] and got['bbox_min']:
        d = max(abs(a - b) for a, b in zip(exp['bbox_min'] + exp['bbox_max'], got['bbox_min'] + got['bbox_max']))
        if d > tol:
            issues.append(f'bbox differs by {d:.4g} mm')
    elif bool(exp['bbox_min']) != bool(got['bbox_min']):
        issues.append('bbox presence differs')
    if exp['face_colours'] != got['face_colours']:
        issues.append(f"colours exp {exp['face_colours']} got {got['face_colours']}")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pkg'); ap.add_argument('--mesh', action='store_true')
    ap.add_argument('--limit', type=int, default=0); ap.add_argument('--only', default=None)
    a = ap.parse_args()
    man = json.load(open(os.path.join(a.pkg, 'parts.json')))
    parts = man['parts']
    if a.only:
        want = set(a.only.split(',')); parts = [p for p in parts if p['name'] in want]
    if a.limit:
        parts = parts[:a.limit]
    results = []; bad = 0; t_all = time.time(); read_total = 0.0
    for i, p in enumerate(parts):
        path = os.path.join(a.pkg, p['file'])
        t0 = time.time()
        doc, rd, err = read_part(path)
        t_read = time.time() - t0
        rec = dict(file=p['file'], name=p['name'], bytes=p['bytes'], read_seconds=round(t_read, 3))
        if err:
            rec['error'] = err; bad += 1
        else:
            got = analyse(doc, mesh=a.mesh)
            exp = expected(p)
            issues = compare(exp, got)
            rec.update(got); rec['expected'] = exp; rec['issues'] = issues
            if issues:
                bad += 1
        rec['rss_mb'] = round(rss_mb(), 1)
        read_total += t_read
        results.append(rec)
        if rec.get('issues') or rec.get('error') or i % 50 == 0 or i == len(parts) - 1:
            print(f"[{i + 1}/{len(parts)}] {p['file']}: {p['bytes'] / 1e6:.1f} MB read {t_read:.2f}s "
                  f"faces {rec.get('faces')} rss {rec['rss_mb']} MB "
                  f"{'OK' if not (rec.get('issues') or rec.get('error')) else rec.get('issues') or rec.get('error')}", flush=True)
        del doc, rd
    summary = dict(parts=len(parts), failed=bad, read_seconds_total=round(read_total, 1),
                   wall_seconds=round(time.time() - t_all, 1), peak_rss_mb=round(rss_mb(), 1),
                   mesh=a.mesh)
    out = 'validation.json' if not (a.only or a.limit) else 'validation_partial.json'
    json.dump(dict(summary=summary, results=results), open(os.path.join(a.pkg, out), 'w'), indent=1)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
