#!/usr/bin/env python3
"""Export the field elements of a split package as STEP assemblies.

Companion to `export_elements.py`: for every element in its manifest this
writes `<name>.step`, one AP214 assembly holding the reference instance's
solid and sheet bodies in the same local frame as `<name>.glb` (arena axes, origin at the
footprint centre and lowest vertex), so the manifest's placements apply
unchanged. The geometry is not re-exported: every geometry-bearing product of
the instance is copied byte for byte from the source STEP (the splitter's
body-selected closure, including sheet bodies), and a synthetic root product is
appended that places each of them with a NEXT_ASSEMBLY_USAGE_OCCURRENCE and
an ITEM_DEFINED_TRANSFORMATION, the way the source file places its own
sub-assemblies. The sub-assembly hierarchy between the element and its
parts is flattened (the IGES round trip left those levels without names).

The grafted road comes from the donor package the same way, rebased onto
the floor top by a rigid translation (the glb used the donor slab's plane;
the difference over the road's footprint is recorded as a residual).

Every file is read back with OCCT: its face count must match the source
imported by the same reader, and its mesh box must match the glb's
`bbox_local_m`. Source healing deltas are recorded. Results go
into `manifest.json` (`assets.<name>.step`) and `step_validation.json`.
There is no `full-map.step`: the full map as STEP is the source file.

Usage:
  export_step_elements.py <pkg_dir> <index.npz> --rules rules/elements-v1.2.0.json
      --assets <dir written by export_elements.py> [--graft <donor_pkg_dir>:<donor_index.npz>]
      [--lin 2] [--ang 0.35]

Run in the OCP venv.
"""
import argparse
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_elements import Package, clusters_of, corners_of, translation  # noqa: E402
from export_field_package import bbox_corners, sha256  # noqa: E402
from mesh_parts import occurrence_transforms, placement, tessellate  # noqa: E402
from p21index import Index  # noqa: E402
from p21model import Model  # noqa: E402
from p21split import Splitter  # noqa: E402
from validate_parts import read_part  # noqa: E402

import provenance  # noqa: E402
from validate_parts import (  # noqa: E402
    BRep_Builder,
    TDF_LabelSequence,
    TopAbs_FACE,
    TopAbs_SOLID,
    TopExp,
    TopoDS_Compound,
    TopTools_IndexedMapOfShape,
    XCAFDoc_DocumentTool,
    XCAFDoc_ShapeTool,
)

GENERATOR = provenance.generator("export_step_elements.py")
BBOX_TOL_M = 0.005


def real(v):
    """A Part 21 REAL: always with a decimal point."""
    s = f"{float(v):.15g}"
    if "E" in s or "e" in s:
        m, e = re.split("[eE]", s)
        return (m if "." in m else m + ".") + "E" + e
    return s if "." in s else s + "."


def p21_string(text):
    """A Part 21 string; non-ASCII goes through the \\X2\\ control directive."""
    out, run = [], []

    def flush():
        if run:
            out.append("\\X2\\" + "".join(f"{ord(c):04X}" for c in run) + "\\X0\\")
            run.clear()

    for c in text:
        if ord(c) < 128:
            flush()
            out.append("''" if c == "'" else ("\\\\" if c == "\\" else c))
        else:
            run.append(c)
    flush()
    return "'" + "".join(out) + "'"


class Assembly:
    """Synthetic root product placing copied leaf products (entity texts)."""

    def __init__(self, ix, m, first_id):
        self.ix, self.m = ix, m
        self.next_id = first_id
        self.entities = []
        self.pd_of = {p: pd for pd, p in m.pd_product.items()}
        self.sr_of = {m.rep_product[rep]: rep for rep in m.sdr_rows}

    def add(self, text):
        i = self.next_id
        self.next_id += 1
        self.entities.append(f"#{i}={text};".encode("utf-8"))
        return i

    def last_ref(self, row):
        """The context a PRODUCT / PRODUCT_DEFINITION / representation ends with."""
        return int(self.ix.refs_of(row)[-1])

    def child_axis(self, sr):
        """The placement item of a leaf's shape representation (its own frame)."""
        for r in self.ix.refs_of(sr):
            rr = self.ix.r(int(r))
            if self.ix.tname(rr) == "AXIS2_PLACEMENT_3D":
                return int(self.ix.ids[rr]), placement(self.ix, rr)
        return None, np.eye(4)

    def axis(self, M):
        cp = self.add(f"CARTESIAN_POINT('',({real(M[0, 3])},{real(M[1, 3])},{real(M[2, 3])}))")
        dz = self.add(f"DIRECTION('axis',({real(M[0, 2])},{real(M[1, 2])},{real(M[2, 2])}))")
        dx = self.add(f"DIRECTION('refdir',({real(M[0, 0])},{real(M[1, 0])},{real(M[2, 0])}))")
        return self.add(f"AXIS2_PLACEMENT_3D('',#{cp},#{dz},#{dx})")

    def build(self, name, label, items):
        """items: (leaf product row, 4x4 leaf-to-local matrix in mm)."""
        ix, m = self.ix, self.m
        first_leaf = items[0][0]
        product_context = self.last_ref(first_leaf)
        pd_context = self.last_ref(self.pd_of[first_leaf])
        rep_context = self.last_ref(self.sr_of[first_leaf])
        root_axis = self.axis(np.eye(4))
        axes, leaf_axes = [], []
        for row, M in items:
            R = M[:3, :3]
            if not (np.allclose(R.T @ R, np.eye(3), atol=1e-6) and np.linalg.det(R) > 0):
                sys.exit(f"{name}: {m.pname(row)} is placed by a mirror or a scale, which AXIS2_PLACEMENT_3D cannot carry")
            # The source links a leaf's own placement item to its placement in
            # the parent: child-to-parent = placement(parent item) @ inv(placement(leaf item)).
            leaf_axis, A0 = self.child_axis(self.sr_of[row])
            if leaf_axis is None:
                leaf_axis = self.axis(np.eye(4))
            leaf_axes.append(leaf_axis)
            axes.append(self.axis(M @ A0))
        items_list = ",".join(f"#{i}" for i in [root_axis] + axes)
        sr = self.add(f"SHAPE_REPRESENTATION('',({items_list}),#{rep_context})")
        product = self.add(f"PRODUCT({p21_string(name)},{p21_string(label or name)},$,(#{product_context}))")
        pdf = self.add(f"PRODUCT_DEFINITION_FORMATION('',$,#{product})")
        pd = self.add(f"PRODUCT_DEFINITION({p21_string(name)},{p21_string(label or name)},#{pdf},#{pd_context})")
        pds = self.add(f"PRODUCT_DEFINITION_SHAPE('',$,#{pd})")
        self.add(f"SHAPE_DEFINITION_REPRESENTATION(#{pds},#{sr})")
        self.add(f"PRODUCT_RELATED_PRODUCT_CATEGORY('assembly','',(#{product}))")
        for k, ((row, M), ax, leaf_axis) in enumerate(zip(items, axes, leaf_axes)):
            occ = p21_string(f"{m.pname(row)}:{k}")
            child_pd = int(ix.ids[self.pd_of[row]])
            child_sr = int(ix.ids[self.sr_of[row]])
            nauo = self.add(f"NEXT_ASSEMBLY_USAGE_OCCURRENCE({occ},{occ},{occ},#{pd},#{child_pd},{occ})")
            npds = self.add(f"PRODUCT_DEFINITION_SHAPE('',$,#{nauo})")
            idt = self.add(f"ITEM_DEFINED_TRANSFORMATION($,$,#{leaf_axis},#{ax})")
            rr = self.add(
                f"(\nREPRESENTATION_RELATIONSHIP($,$,#{child_sr},#{sr})\n"
                f"REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(#{idt})\nSHAPE_REPRESENTATION_RELATIONSHIP()\n)"
            )
            self.add(f"CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(#{rr},#{npds})")
        return self.entities


def level_plane(a, b):
    """4x4 rotation taking the plane z = a x + b y + c to a level plane."""
    n = np.array([-a, -b, 1.0])
    n /= np.linalg.norm(n)
    axis = np.cross(n, [0.0, 0.0, 1.0])
    s = np.linalg.norm(axis)
    if s < 1e-12:
        return np.eye(4)
    axis /= s
    ang = np.arccos(np.clip(n[2], -1.0, 1.0))
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(4)
    R[:3, :3] = np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K
    return R


def write_assembly(splitter, name, label, items, path, source_sha256, pkg=None):
    """Copy the selected source bodies and append the placing root."""
    ix, m = splitter.ix, splitter.m
    body_ids = None
    if pkg is not None:
        body_ids = {b["id"] for row, _ in items for b in pkg.bodies(row)}
        items = [(pkg.source_row(row), M) for row, M in items]
    rows = sorted({row for row, _ in items})
    mask, rewritten = splitter.closure_products(rows, body_ids=body_ids)
    asm = Assembly(ix, m, ix.max_id + 1)
    extra = asm.build(name, label, items)
    header = provenance.step_header(
        ix.header, os.path.basename(path), "export_step_elements.py", ix.source, source_sha256,
        f"RMUC2026 field element {name} ({label}), reference instance in its local frame",
    )
    n, nrw, nbytes = splitter.write_closure(mask, rewritten, path, extra=extra, header=header)
    return {"entities_copied": int(n), "entities_rewritten": int(nrw), "entities_added": len(extra), "bytes": int(nbytes) + len(ix.header)}


def counts(bodies):
    """(bodies, faces) of source bodies."""
    bodies = list(bodies)
    return len(bodies), sum(b["faces"] for b in bodies)


def shape_counts(doc):
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    comp = TopoDS_Compound()
    BRep_Builder().MakeCompound(comp)
    for i in range(1, roots.Length() + 1):
        BRep_Builder().Add(comp, XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)))
    solids = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(comp, TopAbs_SOLID, solids)
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(comp, TopAbs_FACE, faces)
    return solids.Extent(), faces.Extent()


def read_back(path, lin, ang):
    """((solids, faces), mesh bbox in metres) of a STEP file read through OCCT.
    Compare face counts with the same source imported through OCCT; its
    healing can split faces and BREP_WITH_VOIDS solids."""
    doc, rd, err = read_part(path)
    if err:
        return None, None, err
    got = shape_counts(doc)
    mesh = tessellate(doc, lin, ang)
    if mesh is None:
        return got, None, "no triangulation"
    P = mesh[0] / 1000.0
    return got, (P.min(0), P.max(0)), None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pkg")
    ap.add_argument("index")
    ap.add_argument("--rules", required=True)
    ap.add_argument("--assets", required=True, help="directory written by export_elements.py")
    ap.add_argument("--graft", default=None, metavar="PKG_DIR:INDEX_NPZ")
    ap.add_argument("--lin", type=float, default=2.0)
    ap.add_argument("--ang", type=float, default=0.35)
    ap.add_argument("--only", default=None, help="comma-separated element names")
    a = ap.parse_args()
    t0 = time.time()
    rules = json.load(open(a.rules))
    manifest_path = os.path.join(a.assets, "manifest.json")
    manifest = json.load(open(manifest_path))
    if manifest["element_rules"]["sha256"] != sha256(a.rules):
        sys.exit("the rules file differs from the one the assets were exported with")
    pkg = Package(a.pkg, a.index)
    splitter = Splitter(pkg.ix, pkg.m)
    print(f"model ready in {time.time() - t0:.1f}s", flush=True)
    donor = None
    imported_counts = {}
    problems = []

    for spec in rules["elements"]:
        name, label = spec["name"], spec.get("label", "")
        if a.only and name not in a.only.split(","):
            continue
        t1 = time.time()
        asset = manifest["assets"][name]
        placements = asset["placements_in_source_arena_frame"]
        ref = next(p["instance"] for p in placements if p["method"] == "reference")
        origin_mm = np.array(placements[ref]["translation_m"]) * 1000.0
        expected = (0, 0)
        extra = {}
        if "graft" in spec:
            if a.graft is None:
                sys.exit(f"{name} needs --graft")
            if donor is None:
                pkg_dir, index = a.graft.split(":")
                dix = Index(index)
                dm = Model(dix)
                donor = (Splitter(dix, dm), dm, occurrence_transforms(dix, dm), json.load(open(os.path.join(pkg_dir, "parts.json"))))
            dsp, dm, dtr, dparts = donor
            gname = spec["graft"]["products"][0]
            grow = next(r for r in dm.product_name if dm.pname(r) == gname)
            part = next(p for p in dparts["parts"] if p["name"] == gname)
            M = dtr[grow][0]
            # The glb rebased the road by shearing it onto the donor slab's
            # plane (z += floor_top - plane(x, y)); the rigid equivalent is the
            # rotation that levels that plane about the footprint centre, then
            # the lift onto the floor top. They differ by the road height times
            # the slab slope, which is recorded.
            plane = asset["grafted"][0]["donor_slab_plane_z_m"]
            C = np.vstack([bbox_corners(b, M) for b in part["bodies"]])
            lo, hi = C.min(0), C.max(0)
            centre = (lo + hi) / 2
            dz = manifest["floor_top_source_z_m"] - (plane[0] * centre[0] + plane[1] * centre[1] + plane[2])
            R = level_plane(plane[0], plane[1])
            slope = float(np.hypot(plane[0], plane[1]))
            local = translation(-origin_mm) @ translation((centre + [0, 0, dz]) * 1000.0) @ R @ translation(-centre * 1000.0) @ M
            items = [(grow, local)]
            expected = counts(part["bodies"])
            extra = {"graft": {"product": gname, "source_file": dparts["source"], "rigid_rebase_z_m": round(float(dz), 6),
                               "slab_slope": round(slope, 6), "levelled_by_rotation_deg": round(float(np.degrees(np.arctan(slope))), 4),
                               "shear_vs_rotation_bound_m": round(float((hi[2] - lo[2]) * slope), 6)}}
            tol = max(BBOX_TOL_M, 2 * (hi[2] - lo[2]) * slope)
            info = write_assembly(dsp, name, label, items, os.path.join(a.assets, f"{name}.step"), asset["grafted"][0]["source_sha256"])
        else:
            clusters, _ = clusters_of(pkg, spec)
            items = [(row, translation(-origin_mm) @ M) for row, M in clusters[ref] if pkg.bodies(row)]
            expected = counts(b for row, _ in items for b in pkg.bodies(row))
            imported_faces = 0
            for row, _ in items:
                source_path, _ = pkg.geometry_file(row)
                if source_path not in imported_counts:
                    source_doc, _, error = read_part(source_path)
                    if error:
                        sys.exit(f"{source_path}: {error}")
                    imported_counts[source_path] = shape_counts(source_doc)[1]
                imported_faces += imported_counts[source_path]
            extra["source_faces_after_occt_import"] = imported_faces
            extra["occt_face_count_delta"] = imported_faces - expected[1]
            tol = BBOX_TOL_M
            info = write_assembly(splitter, name, label, items, os.path.join(a.assets, f"{name}.step"), manifest["source_sha256"], pkg=pkg)
        path = os.path.join(a.assets, f"{name}.step")
        got, box, err = read_back(path, a.lin, a.ang)
        entry = {
            "file": f"{name}.step",
            "sha256": sha256(path),
            "frame": "same local frame as the glb; the manifest placements apply",
            "leaf_products": len(items),
            "source_bodies": expected[0],
            "source_faces": expected[1],
            "solids_read": got[0] if got else None,
            "faces_read": got[1] if got else None,
            **info,
            **extra,
        }
        status = []
        if err:
            status.append(f"read: {err}")
        else:
            entry["bbox_local_m"] = [box[0].round(6).tolist(), box[1].round(6).tolist()]
            glb = np.array(asset["bbox_local_m"])
            dev = float(max(np.abs(box[0] - glb[0]).max(), np.abs(box[1] - glb[1]).max()))
            entry["bbox_deviation_from_glb_m"] = round(dev, 6)
            entry["bbox_tolerance_m"] = round(float(tol), 6)
            if dev > tol:
                status.append(f"bbox deviates {dev:.4f} m from the glb")
        expected_import = extra.get("source_faces_after_occt_import", expected[1])
        if got is not None and got[1] != expected_import:
            status.append(f"{got[1]} faces read, {expected_import} after source import")
        entry["ok"] = not status
        if status:
            problems.append({"element": name, "problems": status})
        asset["step"] = entry
        print(f"{name} ({label}): {len(items)} products, {expected[0]} bodies as {got[0]} solids, {got[1]}/{expected[1]} faces, {info['bytes'] / 1e6:.1f} MB, "
              f"{'ok' if not status else '; '.join(status)}; {time.time() - t1:.0f}s", flush=True)

    manifest["step"] = {
        "generator": GENERATOR,
        "full_map": "not exported: the full map as STEP is the source file (source_file, source_sha256)",
        "hierarchy": "one synthetic root product per element placing every geometry-bearing product directly; solid and sheet bodies retained",
        "check": "faces read by OCCT equal source faces imported by the same reader; source healing deltas are recorded",
    }
    json.dump(manifest, open(manifest_path, "w"), indent=2, ensure_ascii=False)
    json.dump({"ok": not problems, "problems": problems, "seconds": round(time.time() - t0, 1)},
              open(os.path.join(a.assets, "step_validation.json"), "w"), indent=1, ensure_ascii=False)
    print(f"problems {len(problems)}; {time.time() - t0:.0f}s")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
