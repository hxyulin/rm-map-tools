#!/usr/bin/env python3
"""Export the field elements of a split package as placed simulator assets.

Builds on a field package written by `export_field_package.py` (its
`floor.glb`, `arena-static.glb` and collision proxies are copied over with
their manifest entries) and adds one asset per field element named in a
rules file (`rules/elements-v1.2.0.json`): the base, outpost, rune, dart
station, resource zone, fortress and tech core from this package, and the
起伏路段 undulating road grafted from a donor package. A `full-map.glb`
composes everything in the arena frame.

Each element is exported once, in a local frame whose axes are the arena's
and whose origin is the footprint centre and lowest vertex of its reference
instance (the one the STEP places closest to a quarter turn of the arena
axes); the manifest lists every instance as a rigid placement of that
geometry in the arena frame (translation in metres, rotation as an xyzw
quaternion). Placements are exact when the element is an instanced
sub-assembly (the STEP occurrence transforms are used, and any product of
another instance that the STEP places differently is reported); when the
instances are distinct products (the tech cores, the road) the placement is
the quarter turn about Z whose per-product boxes, or for a single product
whose mesh, matches best, and the residual is recorded. Every meshed part's
box is checked against the STEP vertex box in the part frame.

Sheet bodies are retained: they contain lettering and equipment detail.
Explicit body groups split mixed-owner products without changing geometry.
Origins use the meshed footprint centre and lowest point, not STEP vertex boxes.

Usage:
  export_elements.py <pkg_dir> <index.npz> --rules rules/elements-v1.2.0.json
      --field <field package dir> --out <dir>
      [--graft <donor_pkg_dir>:<donor_index.npz>] [--lin 2] [--ang 0.35]

Run in the OCP venv (see docs/previews.md). The output directory must not
exist yet.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_field_package import (  # noqa: E402
    ARENA_FRAME,
    GRAFT_COLOURS,
    MATERIALS,
    SOURCE_TO_Y_UP_XYZW,
    Donor,
    GlbWriter,
    bbox_check,
    bbox_corners,
    graft_colour_keys,
    place,
    sha256,
    source_checksum,
)
from mesh_parts import nauo_transforms, occurrence_transforms, tessellate, tessellate_pair  # noqa: E402
from p21index import Index  # noqa: E402
from audit_step import geometry_length_units  # noqa: E402
from p21model import Model  # noqa: E402
from p21split import Splitter  # noqa: E402
from validate_parts import read_part  # noqa: E402
import provenance  # noqa: E402
from export_policy import add_arguments, from_arguments

GENERATOR = provenance.generator("export_elements.py")
LOCAL_FRAME = (
    "arena axes; origin at the footprint centre (x, y) and lowest vertex (z) of the reference instance; "
    "apply the placement to get the arena frame"
)
BBOX_TOL_M = 0.005


def rot_z(deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def translation(t):
    M = np.eye(4)
    M[:3, 3] = t
    return M


def in_metres(M):
    """STEP occurrence matrix (millimetre translation) -> metres."""
    out = M.copy()
    out[:3, 3] /= 1000.0
    return out


def quaternion_xyzw(R):
    """Rotation matrix -> unit quaternion (x, y, z, w)."""
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        return [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, 0.25 * s]
    i = int(np.argmax(np.diag(R)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k]) * 2
    q = [0.0, 0.0, 0.0, 0.0]
    q[i] = 0.25 * s
    q[j] = (R[j, i] + R[i, j]) / s
    q[k] = (R[k, i] + R[i, k]) / s
    q[3] = (R[k, j] - R[j, k]) / s
    return q


def is_rotation(R):
    return np.allclose(R.T @ R, np.eye(3), atol=1e-6) and np.linalg.det(R) > 0


def placement_entry(k, P, method, residual_m):
    R = P[:3, :3]
    if not is_rotation(R):
        sys.exit(f"instance {k}: placement is not a proper rotation (det {np.linalg.det(R):.3f})")
    return {
        "instance": k,
        "translation_m": [round(float(v), 6) for v in P[:3, 3]],
        "rotation_xyzw": [round(float(v), 9) for v in quaternion_xyzw(R)],
        "matrix_local_to_arena": [[round(float(v), 9) for v in row] for row in P],
        "method": method,
        "bbox_residual_m": round(float(residual_m), 6),
    }


def corners_of(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return np.array([[lo[j] if (c >> j) & 1 == 0 else hi[j] for j in range(3)] for c in range(8)])


# Shared traversal also handles articulated assets and repeated mesh instances.
from gltf_scene import read_glb_nodes, read_glb_local_nodes


class Package:
    """A split package with its model, placements and per-product solids."""

    def __init__(self, pkg, index):
        self.pkg = pkg
        self.ix = Index(index)
        units = geometry_length_units(self.ix)
        if not units or set(units) != {".MILLI.,.METRE."}:
            raise ValueError(f"expected millimetre geometry contexts, got {units}")
        self.m = Model(self.ix)
        self.nauo_T = nauo_transforms(self.ix, self.m)
        self.transforms = occurrence_transforms(self.ix, self.m, self.nauo_T)
        parts = json.load(open(os.path.join(pkg, "parts.json")))
        self.source = parts["source"]
        self.by_id = {p["product_id"]: p for p in parts["parts"]}
        self.row_of_name = {}
        for r in self.m.product_name:
            self.row_of_name.setdefault(self.m.pname(r), r)
        self.splitter = None
        self.groups = {}
        self.meshing_report = {}

    def row(self, name):
        if name not in self.row_of_name:
            sys.exit(f"product {name!r} is not in {self.source}")
        return self.row_of_name[name]

    def source_row(self, row):
        return self.groups[row][0] if row in self.groups else row

    def name(self, row):
        return self.part(row)["name"] if row in self.groups else self.m.pname(row)

    def register_groups(self, groups):
        for name, spec in groups.items():
            if name in self.row_of_name:
                continue
            source = self.row(spec["product"])
            ids = {i for lo, hi in spec["body_id_ranges"] for i in range(lo, hi + 1)}
            part = dict(self.part(source))
            part["bodies"] = [b for b in part["bodies"] if b["id"] in ids]
            if ids != {b["id"] for b in part["bodies"]}:
                raise ValueError(f"{name}: selected bodies absent from source product")
            part["name"] = name
            row = -len(self.groups) - 1
            self.groups[row] = (source, part)
            self.row_of_name[name] = row
            self.transforms[row] = self.transforms[source]

    def part(self, row):
        return self.groups[row][1] if row in self.groups else self.by_id.get(int(self.ix.ids[row]))

    def bodies(self, row):
        p = self.part(row)
        return p["bodies"] if p else []

    def geometry_file(self, row):
        """Preserve solids and sheets. Body groups use a source-checked subset."""
        p = self.part(row)
        if row not in self.groups:
            return os.path.join(self.pkg, p["file"]), False
        ids = {b["id"] for b in p["bodies"]}
        key = hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()[:16]
        path = os.path.join(self.pkg, "selected", f"{p['name']}-{key}.stp")
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if self.splitter is None:
                self.splitter = Splitter(self.ix, self.m)
            mask, rewritten = self.splitter.closure_products([self.source_row(row)], body_ids=ids)
            self.splitter.write_closure(mask, rewritten, path)
        return path, True

    def subtree_placed(self, root, M, exclude=()):
        """(product row, arena matrix) for a placed product and its descendants."""
        out = []

        def walk(q, W):
            if self.name(q) in exclude:
                return
            out.append((q, W))
            for nauo, c in self.m.children.get(q, []):
                if c is not None:
                    walk(c, W @ self.nauo_T.get(nauo, np.eye(4)))

        walk(root, M)
        return out

    def placed_box(self, items):
        """Union of the placed STEP vertex boxes of the items' solids, metres."""
        pts = [bbox_corners(b, M) for row, M in items for b in self.bodies(row)]
        if not pts:
            return None
        P = np.vstack(pts)
        return P.min(0), P.max(0)


def clusters_of(pkg, spec):
    """The element's instances as lists of placed products, plus the anchor's
    occurrence matrices when the instances are true STEP occurrences."""
    pkg.register_groups(spec.get("body_groups", {}))
    if "instances" in spec:
        clusters = []
        for names in spec["instances"]:
            items = []
            for n in names:
                Ms = pkg.transforms.get(pkg.row(n), [])
                if len(Ms) != 1:
                    sys.exit(f"{spec['name']}: {n} has {len(Ms)} occurrences, expected 1")
                items.append((pkg.row(n), Ms[0]))
            clusters.append(items)
        return clusters, None
    anchor = pkg.row(spec["products"][0])
    anchors = pkg.transforms.get(anchor, [])
    if not anchors:
        sys.exit(f"{spec['name']}: {spec['products'][0]} is never placed")
    exclude = set(spec.get("exclude", []))
    clusters = [pkg.subtree_placed(anchor, M, exclude) for M in anchors]
    centres = [np.mean(pkg.placed_box(c), axis=0) for c in clusters]
    for name in spec["products"][1:]:
        for M in pkg.transforms.get(pkg.row(name), []):
            items = pkg.subtree_placed(pkg.row(name), M, exclude)
            box = pkg.placed_box(items)
            if box is None:
                continue
            centre = np.mean(box, axis=0)
            k = int(np.argmin([np.linalg.norm(centre - c) for c in centres]))
            clusters[k] += items
    return clusters, anchors


def selection_coverage(pkg, rules, field):
    """Every source body has one full-map owner; reusable subassets are aliases."""
    owners = {}
    for name in ("floor", "arena-static"):
        for pid in field["assets"][name]["source_products"]:
            for body in pkg.by_id[pid]["bodies"]:
                owners.setdefault(body["id"], set()).add(name)
    for spec in rules["elements"]:
        if "graft" in spec or spec.get("in_arena") or spec.get("included_in"):
            continue
        clusters, _ = clusters_of(pkg, spec)
        for cluster in clusters:
            for row, _ in cluster:
                for body in pkg.bodies(row):
                    owners.setdefault(body["id"], set()).add(spec["name"])
    missing = {p["name"]: [b["id"] for b in p["bodies"] if b["id"] not in owners]
               for p in pkg.by_id.values()}
    missing = {name: ids for name, ids in missing.items() if ids}
    duplicate = {str(i): sorted(names) for i, names in owners.items() if len(names) > 1}
    return {"source_bodies": sum(len(p["bodies"]) for p in pkg.by_id.values()),
            "covered_bodies": len(owners), "unassigned": missing, "multiple_owners": duplicate}


def footprint_origin(points):
    """Centre the actual visual footprint; put its lowest point at local z=0."""
    lo, hi = points.min(0), points.max(0)
    return np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])


def nn_residual(A, B, samples=2000, seed=0):
    """Symmetric nearest-vertex distance between two point sets (metres):
    the 95th percentile and the maximum over a random sample of each side."""
    rng = np.random.default_rng(seed)

    def one_way(P, Q):
        idx = rng.choice(len(P), min(samples, len(P)), replace=False)
        best = np.empty(len(idx))
        for i in range(0, len(idx), 100):
            chunk = P[idx[i : i + 100]]
            d = np.sqrt(((chunk[:, None, :] - Q[None, :, :]) ** 2).sum(-1))
            best[i : i + 100] = d.min(1)
        return best

    d = np.concatenate([one_way(A, B), one_way(B, A)])
    return float(np.percentile(d, 95)), float(d.max())


def box_residual(boxes0_local, R, t, boxes_k):
    """Largest per-product box mismatch (metres) after carrying instance 0's
    product boxes by (R, t): each is compared with the nearest box of instance k."""
    worst = 0.0
    for lo, hi in boxes0_local:
        C = corners_of(lo, hi) @ R.T + t
        blo, bhi = C.min(0), C.max(0)
        res = min(max(np.abs(klo - blo).max(), np.abs(khi - bhi).max()) for klo, khi in boxes_k)
        worst = max(worst, float(res))
    return worst


def match_cluster(V0_local, boxes0_local, W_k, boxes_k):
    """Quarter turn about Z carrying instance 0's local geometry onto instance k:
    among the turns whose overall extents match, the one whose per-product
    boxes match best (or, for a single product, whose meshes are nearest).
    Returns (placement, residual, mesh p95, mesh max, yaw)."""
    box0 = (np.min([lo for lo, _ in boxes0_local], axis=0), np.max([hi for _, hi in boxes0_local], axis=0))
    box_k = (np.min([lo for lo, _ in boxes_k], axis=0), np.max([hi for _, hi in boxes_k], axis=0))
    best = None
    for yaw in (0, 90, 180, 270):
        R = rot_z(yaw)
        C = corners_of(*box0) @ R.T
        shift_lo = box_k[0] - C.min(0)
        shift_hi = box_k[1] - C.max(0)
        if np.abs(shift_lo - shift_hi).max() > 0.05:
            continue  # extents do not even match
        t = (shift_lo + shift_hi) / 2
        p95, worst = nn_residual(V0_local @ R.T + t, W_k)
        residual = box_residual(boxes0_local, R, t, boxes_k) if len(boxes0_local) > 1 else p95
        if best is None or residual < best[1]:
            P = np.eye(4)
            P[:3, :3] = R
            P[:3, 3] = t
            best = (P, residual, p95, worst, yaw)
    if best is None:
        sys.exit("no quarter turn matches the instance's extents")
    return best


def mesh_item(pkg, row, lin, ang, settings=None):
    path, solids_only = pkg.geometry_file(row)
    doc, rd, err = read_part(path)
    if err:
        return None, None, err, path
    stats = {}
    if settings is None:
        fine = tessellate(doc, lin, ang, stats=stats)
        coarse = fine
    else:
        try:
            fine, coarse = tessellate_pair(doc, settings, stats=stats)
        except ValueError as error:
            return None, None, str(error), path
    pkg.meshing_report[pkg.name(row)] = stats
    if stats.get("unmeshed_faces"):
        return None, None, f"{stats['unmeshed_faces']} faces could not be tessellated", path
    if fine is None or coarse is None:
        return None, None, "no triangulation", path
    return fine, coarse, None, path


def mesh_cluster(pkg, items, a, element, failures, bbox_errors):
    """Mesh every placed product with solids: (node, part, M, fine, coarse) in
    the arena frame (metres), with the part-frame mesh box checked against
    the STEP vertex box of the product's solids."""
    out = []
    for row, M in items:
        solids = pkg.bodies(row)
        if not solids:
            continue
        p = pkg.part(row)
        fine, coarse, err, path = mesh_item(
            pkg, row, a.lin, a.ang, a.export_policy.settings(element, p["name"]))
        if err:
            failures.append({"element": element, "part": p["name"], "error": err})
            print(f"{element}: {p['name']} unreadable: {err}", flush=True)
            continue
        lo = np.min([b["bbox_min"] for b in solids], axis=0) / 1000.0
        hi = np.max([b["bbox_max"] for b in solids], axis=0) / 1000.0
        missing_m, excess_m = bbox_check(fine[0] / 1000.0, corners_of(lo, hi))
        # A sphere or torus has one or two vertices: its vertex box says
        # nothing about how far the surface reaches.
        bounded = [b for b in solids if b.get("vertices", 0) >= 4]
        if not bounded:
            excess_m = 0.0
        elif len(bounded) < len(solids):
            lo = np.min([b["bbox_min"] for b in bounded], axis=0) / 1000.0
            hi = np.max([b["bbox_max"] for b in bounded], axis=0) / 1000.0
            excess_m = bbox_check(fine[0] / 1000.0, corners_of(lo, hi))[1]
        node = f"source_{p['product_id']}_{p['name']}"
        if missing_m > 0.002 or excess_m > 0.1:
            bbox_errors.append({"element": element, "node": node, "missing_m": missing_m, "excess_m": excess_m})
        out.append((node, p, M, fine, coarse, os.path.relpath(path, pkg.pkg), (missing_m, excess_m)))
    return out


def placed_mesh(fine, M):
    """Arena-frame vertices (metres) and outward-wound triangles of a meshed part."""
    P, T, C, cols = fine
    flip = np.linalg.det(M[:3, :3]) < 0
    return place(P, M), (T[:, [0, 2, 1]] if flip else T), [cols[c] for c in C]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pkg")
    ap.add_argument("index")
    ap.add_argument("--rules", required=True)
    ap.add_argument("--field", required=True, help="field package from export_field_package.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--semantics", help="checksum-pinned semantic/joint rules applied after tessellation")
    ap.add_argument("--graft", default=None, metavar="PKG_DIR:INDEX_NPZ", help="donor package for grafted elements")
    ap.add_argument("--graft-floor", default=None)
    ap.add_argument("--graft-colours", default=GRAFT_COLOURS)
    add_arguments(ap)
    ap.add_argument("--texture-atlas", help="JSON artwork selections to bake into PNG atlases and a placement sidecar")
    a = ap.parse_args()
    a.export_policy = from_arguments(a, ap)
    default_settings = a.export_policy.settings("")
    a.lin = default_settings["visual"]["linear_deflection_mm"]
    a.ang = default_settings["visual"]["angular_deflection_rad"]
    if os.path.exists(a.out):
        sys.exit(f"{a.out} exists; the output directory must be new")
    t0 = time.time()
    rules = json.load(open(a.rules))
    field = json.load(open(os.path.join(a.field, "manifest.json")))
    floor_top = field["floor_top_source_z_m"]
    pkg = Package(a.pkg, a.index)
    if os.path.basename(pkg.source) != rules["source"]:
        sys.exit(f"rules are for {rules['source']}, package is {pkg.source}")
    coverage = selection_coverage(pkg, rules, field)
    if coverage["unassigned"] or coverage["multiple_owners"]:
        sys.exit(f"body ownership is incomplete or ambiguous: {coverage}")
    print(f"model ready in {time.time() - t0:.1f}s; {coverage['covered_bodies']} bodies assigned", flush=True)
    donor = None
    top_key, side_key = graft_colour_keys(a.graft_colours)
    source_hash, hash_origin = source_checksum(pkg.source)

    def asset_block(name, **extras):
        return provenance.glb_asset("export_elements.py", pkg.source, source_hash, asset=name, **extras)

    os.makedirs(a.out)
    assets, validation_nodes, failures, bbox_errors, warnings = {}, {}, [], [], []
    full = {"visual": GlbWriter("FULL-MAP", asset_block("full-map", frame=ARENA_FRAME)),
            "collision": GlbWriter("FULL-MAP_COLLISION", asset_block("full-map", frame=ARENA_FRAME, collision=True))}
    composed = []

    # The arena as already exported: copied, and its nodes read back for the full map.
    for name in ("floor", "arena-static"):
        entry = dict(field["assets"][name])
        source_visual = os.path.join(a.field, entry["visual"])
        if sha256(source_visual) != entry["visual_sha256"]:
            sys.exit(f"{entry['visual']} does not match the field manifest checksum")
        entry["collision"] = name + "-collision.glb"
        for kind in ("visual", "collision"):
            shutil.copyfile(source_visual, os.path.join(a.out, entry[kind]))
            entry[f"{kind}_sha256"] = entry["visual_sha256"]
            for node, P, T, K, M in read_glb_local_nodes(os.path.join(a.out, entry[kind])):
                full[kind].add_node(node, P, T, K, matrix=M)
        entry["collision_triangles"] = entry["triangles"]
        entry["carried_from"] = {"directory": a.field, "generator": field.get("generator")}
        assets[name] = entry
        composed.append(name)

    for spec in rules["elements"]:
        name, label = spec["name"], spec.get("label", "")
        t1 = time.time()
        visual = GlbWriter(name.upper(), asset_block(name, label=label, frame=LOCAL_FRAME))
        collision = GlbWriter(f"{name.upper()}_COLLISION", asset_block(name, label=label, frame=LOCAL_FRAME, collision=True))
        nodes, meshes = [], []  # meshes: (node, fine, coarse) in the local frame
        grafted = []
        if "graft" in spec:
            if a.graft is None:
                sys.exit(f"{name} needs --graft")
            if donor is None:
                pkg_dir, index = a.graft.split(":")
                donor = Donor(pkg_dir, index, a.graft_floor, a.lin, a.ang)
                donor_hash, donor_hash_origin = source_checksum(donor.source)
                print(f"graft donor {donor.source}: floor slab {donor.floor['name']}", flush=True)
            clusters, boxes, node_sets = [], [], []
            for gname in spec["graft"]["products"]:
                p = donor.by_name.get(gname)
                if p is None:
                    sys.exit(f"{name}: {gname} is not in the donor package")
                doc, rd, err = read_part(os.path.join(donor.pkg, p["file"]))
                settings = a.export_policy.settings(name, gname)
                fine, coarse = (None, None) if err else tessellate_pair(doc, settings)
                if fine is None or coarse is None:
                    sys.exit(f"{name}: {gname} unusable: {err or 'no triangulation'}")
                M = donor.placements(p)[0]
                placed = place(fine[0], M)
                plane = donor.slab_plane(placed.min(0), placed.max(0))
                for b in p["bodies"]:
                    missing_m, excess_m = bbox_check(placed, bbox_corners(b, M))
                    if missing_m > 0.002 or excess_m > 0.1:
                        bbox_errors.append({"element": name, "node": gname, "missing_m": missing_m, "excess_m": excess_m})

                def rebase(world, plane=plane):
                    out = world.copy()
                    out[:, 2] += floor_top - (plane[0] * world[:, 0] + plane[1] * world[:, 1] + plane[2])
                    return out

                flip = np.linalg.det(M[:3, :3]) < 0
                set_ = []
                for P, T, C, cols in (fine, coarse):
                    world = rebase(place(P, M))
                    tris = T[:, [0, 2, 1]] if flip else T
                    n = np.cross(world[tris[:, 1]] - world[tris[:, 0]], world[tris[:, 2]] - world[tris[:, 0]])
                    up = n[:, 2] > 0.5 * np.linalg.norm(n, axis=1)
                    set_.append((world, tris, [top_key if u else side_key for u in up]))
                clusters.append([(f"graft_{p['product_id']}_{gname}", set_, p)])
                boxes.append((set_[0][0].min(0), set_[0][0].max(0)))
                grafted.append(
                    {
                        "product": gname,
                        "product_id": p["product_id"],
                        "source_file": donor.source,
                        "source_sha256": donor_hash,
                        "source_sha256_origin": donor_hash_origin,
                        "donor_slab_plane_z_m": [round(float(c), 6) for c in plane],
                    }
                )
            origin = np.array([(boxes[0][0][0] + boxes[0][1][0]) / 2, (boxes[0][0][1] + boxes[0][1][1]) / 2, boxes[0][0][2]])
            box0_local = (boxes[0][0] - origin, boxes[0][1] - origin)
            placements = [placement_entry(0, translation(origin), "reference", 0.0)]
            V0 = np.vstack([set_[0][0] for _, set_, _ in clusters[0]]) - origin
            for k in range(1, len(clusters)):
                W = np.vstack([set_[0][0] for _, set_, _ in clusters[k]])
                P, residual, p95, worst, yaw = match_cluster(V0, [box0_local], W, [boxes[k]])
                placements.append(placement_entry(k, P, f"matched_yaw_{yaw}", residual))
                placements[-1]["mesh_residual_p95_m"] = round(p95, 6)
                placements[-1]["mesh_residual_max_m"] = round(worst, 6)
                if residual > BBOX_TOL_M:
                    bbox_errors.append({"element": name, "instance": k, "placement_residual_m": residual})
            for node, (fine_w, coarse_w), p in clusters[0]:
                for writer, (world, tris, keys) in ((visual, fine_w), (collision, coarse_w)):
                    writer.add_node(node, world - origin, tris, keys)
                meshes.append((node, (fine_w[0] - origin, fine_w[1], fine_w[2]), (coarse_w[0] - origin, coarse_w[1], coarse_w[2])))
                nodes.append(
                    {
                        "node": node,
                        "product_id": p["product_id"],
                        "part_file": p["file"],
                        "triangles": int(len(fine_w[1])),
                        "collision_triangles": int(len(coarse_w[1])),
                        "colours_srgb": {top_key: int(sum(k == top_key for k in fine_w[2])), side_key: int(sum(k == side_key for k in fine_w[2]))},
                        "bbox_local_min_m": (fine_w[0].min(0) - origin).round(6).tolist(),
                        "bbox_local_max_m": (fine_w[0].max(0) - origin).round(6).tolist(),
                        "graft": grafted[0],
                    }
                )
            source_products = []
            in_full_map = False  # arena-static already carries the grafted road
        else:
            clusters, anchors = clusters_of(pkg, spec)
            boxes = [pkg.placed_box(c) for c in clusters]
            for k, box in enumerate(boxes):
                if box is None:
                    sys.exit(f"{name}: instance {k} has no solids")
            # Reference geometry: the instance whose anchor sits closest to a
            # quarter turn of the arena axes (V1.2.0 tilts one outpost 3.6°).
            ref = 0
            if anchors is not None:
                yaws = [np.degrees(np.arctan2(M[1, 0], M[0, 0])) for M in anchors]
                ref = int(np.argmin([abs((y + 45) % 90 - 45) for y in yaws]))
            origin = np.array([(boxes[ref][0][0] + boxes[ref][1][0]) / 2, (boxes[ref][0][1] + boxes[ref][1][1]) / 2, boxes[ref][0][2]])
            meshed = mesh_cluster(pkg, clusters[ref], a, name, failures, bbox_errors)
            reference_points = np.vstack([placed_mesh(fine, M)[0] for _, _, M, fine, *_ in meshed])
            origin = footprint_origin(reference_points)
            source_products = sorted({p["product_id"] for _, p, *_ in meshed})
            for node, p, M, fine, coarse, part_file, (missing_m, excess_m) in meshed:
                local = []
                for writer, mesh in ((visual, fine), (collision, coarse)):
                    world, tris, keys = placed_mesh(mesh, M)
                    writer.add_node(node, world - origin, tris, keys)
                    local.append((world - origin, tris, keys))
                meshes.append((node, local[0], local[1]))
                nodes.append(
                    {
                        "node": node,
                        "product_id": p["product_id"],
                        "part_file": part_file,
                        "triangles": int(len(fine[1])),
                        "collision_triangles": int(len(coarse[1])),
                        "colours_srgb": {c: int((fine[2] == j).sum()) for j, c in enumerate(fine[3])},
                        "bbox_local_min_m": local[0][0].min(0).round(6).tolist(),
                        "bbox_local_max_m": local[0][0].max(0).round(6).tolist(),
                        "bbox_missing_m": round(missing_m, 6),
                        "bbox_excess_m": round(excess_m, 6),
                    }
                )
            placements = []
            V0 = np.vstack([fine[0] for _, fine, _ in meshes]) if meshes else np.zeros((0, 3))
            boxes_ref = [tuple(np.asarray(b) - origin for b in pkg.placed_box([item])) for item in clusters[ref] if pkg.bodies(item[0])]
            for k in range(len(clusters)):
                if k == ref:
                    placements.append(placement_entry(k, translation(origin), "reference", 0.0))
                    continue
                if anchors is not None:
                    # Exact: the STEP occurrence transforms. Every product of
                    # instance k should sit where the reference's copy lands;
                    # a product placed differently is reported, not moved.
                    A = in_metres(anchors[k]) @ np.linalg.inv(in_metres(anchors[ref]))
                    P = A @ translation(origin)
                    at_ref = {row: in_metres(M) for row, M in clusters[ref]}
                    residual, unmatched, off = 0.0, [], []
                    for row, M in clusters[k]:
                        if row not in at_ref:
                            unmatched.append(pkg.name(row))
                            continue
                        D = A @ at_ref[row] - in_metres(M)
                        d_rot, d_t = float(np.abs(D[:3, :3]).max()), float(np.abs(D[:3, 3]).max())
                        if d_rot > 1e-6 or d_t > 1e-6:
                            off.append({"product": pkg.name(row), "rotation_deg": round(float(np.degrees(np.arcsin(min(1.0, d_rot)))), 3), "translation_m": round(d_t, 6)})
                        else:
                            residual = max(residual, d_t)
                    if unmatched or len(clusters[k]) != len(clusters[ref]):
                        bbox_errors.append({"element": name, "instance": k, "products_differ": unmatched})
                    placements.append(placement_entry(k, P, "instance", residual))
                    if off:
                        placements[-1]["products_placed_differently"] = off
                        warnings.append({"element": name, "instance": k, "products_placed_differently": off})
                else:
                    meshed_k = mesh_cluster(pkg, clusters[k], a, name, failures, bbox_errors)
                    W = np.vstack([placed_mesh(fine, M)[0] for _, _, M, fine, *_ in meshed_k])
                    boxes_k = [pkg.placed_box([item]) for item in clusters[k] if pkg.bodies(item[0])]
                    P, residual, p95, worst, yaw = match_cluster(V0, boxes_ref, W, boxes_k)
                    placements.append(placement_entry(k, P, f"matched_yaw_{yaw}", residual))
                    placements[-1]["mesh_residual_p95_m"] = round(p95, 6)
                    placements[-1]["mesh_residual_max_m"] = round(worst, 6)
                if residual > BBOX_TOL_M:
                    bbox_errors.append({"element": name, "instance": k, "placement_residual_m": residual})
            # Arena bodies are already in arena-static; do not place them twice.
            in_full_map = not (spec.get("in_arena", False) or spec.get("included_in"))

        files = {}
        for kind, writer in (("visual", visual), ("collision", collision)):
            fn = f"{name}.glb" if kind == "visual" else f"{name}-collision.glb"
            writer.write(os.path.join(a.out, fn))
            files[kind] = fn
        if in_full_map:
            for k, pl in enumerate(placements):
                P = np.array(pl["matrix_local_to_arena"])
                for node, fine, coarse in meshes:
                    for kind, (Pm, T, K) in (("visual", fine), ("collision", coarse)):
                        full[kind].add_node(f"{name}_{k}_{node}", Pm, T, K, matrix=P)
            composed.append(name)
        assets[name] = {
            "label": label,
            "visual": files["visual"],
            "visual_sha256": sha256(os.path.join(a.out, files["visual"])),
            "collision": files["collision"],
            "collision_sha256": sha256(os.path.join(a.out, files["collision"])),
            "source_products": source_products,
            "local_frame": LOCAL_FRAME,
            "placements_in_source_arena_frame": placements,
            "nodes": len(nodes),
            "collision_method": "source-tessellation-v1",
            "tessellation": a.export_policy.resolved.get(name, {}),
            "triangles": sum(e["triangles"] for e in nodes),
            "collision_triangles": sum(e["collision_triangles"] for e in nodes),
            "colours_srgb": sorted({c for e in nodes for c in e["colours_srgb"]}, key=lambda c: c or ""),
            "bbox_local_m": [
                np.min([e["bbox_local_min_m"] for e in nodes], axis=0).round(6).tolist(),
                np.max([e["bbox_local_max_m"] for e in nodes], axis=0).round(6).tolist(),
            ] if nodes else None,
            "in_full_map": in_full_map,
        }
        if grafted:
            assets[name]["grafted"] = grafted
        validation_nodes[name] = nodes
        print(
            f"{name} ({label}): {len(nodes)} nodes, {assets[name]['triangles']} / {assets[name]['collision_triangles']} triangles, "
            f"{len(placements)} placements "
            + ", ".join(f"{p['method']} at {p['translation_m'][:2]} r={p['bbox_residual_m']:.4f}" for p in placements)
            + f"; {time.time() - t1:.0f}s",
            flush=True,
        )

    files = {}
    for kind, writer in full.items():
        fn = "full-map.glb" if kind == "visual" else "full-map-collision.glb"
        writer.write(os.path.join(a.out, fn))
        files[kind] = fn
    assets["full-map"] = {
        "label": "全图",
        "visual": files["visual"],
        "visual_sha256": sha256(os.path.join(a.out, files["visual"])),
        "collision": files["collision"],
        "collision_sha256": sha256(os.path.join(a.out, files["collision"])),
        "composed_of": composed,
        "frame": "arena frame; every element instance placed, node names <element>_<instance>_<node>",
        "nodes": len(full["visual"].nodes),
        "triangles": full["visual"].triangles,
        "collision_triangles": full["collision"].triangles,
    }
    manifest = {
        "schema_version": 1,
        "generator": GENERATOR,
        "units": "metres",
        "source_file": pkg.source,
        "source_sha256": source_hash,
        "source_sha256_origin": hash_origin,
        "split_package": {"parts_json_source": pkg.source, "parts": len(pkg.by_id)},
        "element_rules": {"file": os.path.relpath(a.rules), "sha256": sha256(a.rules), "notes": rules.get("notes", [])},
        "arena_frame": ARENA_FRAME,
        "source_to_y_up_rotation_xyzw": SOURCE_TO_Y_UP_XYZW,
        "floor_top_source_z_m": floor_top,
        "floor_slab": field["floor_slab"],
        "tessellation": default_settings,
        "export_policy": a.export_policy.metadata(),
        "collision_contract": "Independent tessellations of source solids and sheets, except explicit collision exclusions in export_policy; two-sided contacts required. Copied arena assets retain their input policy.",
        "collision_solids": False,
        "materials": MATERIALS,
        "assets": assets,
    }
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"), indent=2, ensure_ascii=False)
    if a.semantics:
        from export_semantics import annotate_package
        annotate_package(a.out, json.load(open(a.semantics)), sha256(a.semantics))
    validation = {
        "ok": not failures and not bbox_errors,
        "read_failures": failures,
        "bbox_mismatches": bbox_errors,
        "warnings": warnings,
        "body_coverage": coverage,
        "meshing": pkg.meshing_report,
        "placements": {n: assets[n]["placements_in_source_arena_frame"] for n in validation_nodes},
        "seconds": round(time.time() - t0, 1),
        "nodes": validation_nodes,
    }
    json.dump(validation, open(os.path.join(a.out, "validation.json"), "w"), indent=1, ensure_ascii=False)
    print(f"full map: {assets['full-map']['nodes']} nodes, {assets['full-map']['triangles']} / {assets['full-map']['collision_triangles']} triangles")
    for w in warnings:
        print(f"warning: {w}")
    print(f"failures {len(failures)}; bbox mismatches {len(bbox_errors)}; warnings {len(warnings)}; {time.time() - t0:.0f}s")
    if failures or bbox_errors:
        sys.exit(1)

    if a.texture_atlas:
        from texture_atlas import export_atlas
        export_atlas(a.out, a.texture_atlas)


if __name__ == "__main__":
    main()
