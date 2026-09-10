#!/usr/bin/env python3
"""Export the arena of a split field package as the simulator asset package.

Writes the manifest schema the simulators (`rm-simulator`, `rm-vision-sim`)
already load: `floor.glb`, `arena-static.glb`, their `*-collision.glb`
proxies, `manifest.json` with SHA-256 checksums, and `validation.json`.
The articulated equipment (rune, outpost) and the rigid equipment directory
(base, tech core) are carried over from an existing extraction, since
their placements are in the same arena frame.

Every arena body (`BREP_*` product, plus `--arena-products` such as the
V1.2.0 base pedestals `0010_1`) is read from its split part file with
OCCT, tessellated, placed by the STEP assembly transforms and written as one
glTF node named `source_<product id>_<product name>[_<instance>]`, with one
primitive per effective face colour (face > shell > body). Coordinates stay
in the CAD arena frame (Z up) converted to metres, exactly like the earlier
extraction, so consumers keep their arena transform.

Solids the source STEP leaves out can be grafted from another split package
of the same arena (`--graft`): the V1.2.0 STEP has a flat deck where V2.0.0
models the 起伏路段 undulating road (`BREP_220`, `BREP_192`), so those two
solids are read from the V2.0.0 package, the tilt of V2.0.0's crowned slab
under each is removed and they are set on this package's floor top, coloured
with this package's plate colours (`--graft-colours`). Grafted nodes are
named `graft_<product id>_<product name>[_<instance>]` and listed in the
manifest under the asset's `grafted` entry with the donor file's checksum.

Usage:
  export_field_package.py <pkg_dir> <index.npz> --equipment <extracted_dir>
      --out <dir> [--lin 2] [--ang 0.35] [--collision-lin 10]
      [--collision-ang 0.7] [--floor NAME]
      [--graft <donor_pkg_dir>:<donor_index.npz>:<NAME,...>]

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
from mesh_parts import occurrence_transforms, tessellate  # noqa: E402
from p21index import Index  # noqa: E402
from p21model import Model  # noqa: E402
from validate_parts import read_part  # noqa: E402

# glTF Y-up from the Z-up arena frame: -90 degrees about X.
SOURCE_TO_Y_UP_XYZW = [-0.7071067811865475, 0.0, 0.0, 0.7071067811865476]
ARENA_FRAME = "original CAD numeric axes and origin, Z up; do not assume glTF Y-up"
COLLISION_CONTRACT = (
    "Separate triangle-mesh proxies, not scoring masks: the same CAD solids "
    "tessellated coarser, one closed node per solid within the collision "
    "tolerance of the visual, untouched markings and undersides included; "
    "consumers may use the nodes as they are (collision_solids) and need "
    "only drop the flat marking sheets."
)
MATERIALS = (
    "STEP face colours (face > shell > body) as glTF base colour factors, "
    "one primitive per colour, flat normals. No textures or emission."
)
# V1.2.0 plate colours for grafted solids: tops Opaque(65,65,65), sides Opaque(200,200,180).
GRAFT_COLOURS = "top=0.2549,0.2549,0.2549;side=0.7843,0.7843,0.7059"


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def colour_rgb(key):
    if key is None:
        return (0.6275, 0.6275, 0.6275)
    return tuple(float(x) for x in key.split(","))


class GlbWriter:
    """Minimal glTF 2.0 binary writer: one buffer, flat triangle meshes."""

    def __init__(self, root_name, generator):
        self.root_name = root_name
        self.generator = generator
        self.bin = bytearray()
        self.buffer_views = []
        self.accessors = []
        self.materials = []
        self.material_index = {}
        self.meshes = []
        self.nodes = []
        self.triangles = 0

    def material(self, key):
        if key not in self.material_index:
            r, g, b = colour_rgb(key)
            self.material_index[key] = len(self.materials)
            self.materials.append(
                {
                    "name": f"colour_{key or 'default'}",
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0],
                        "metallicFactor": 0.0,
                        "roughnessFactor": 0.8,
                    },
                    "doubleSided": True,
                    "extras": {"step_colour_srgb": [r, g, b]},
                }
            )
        return self.material_index[key]

    def _view(self, data, target):
        while len(self.bin) % 4:
            self.bin.append(0)
        offset = len(self.bin)
        self.bin += data
        self.buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        return len(self.buffer_views) - 1

    def _accessor(self, view, component, count, kind, extremes=None):
        acc = {"bufferView": view, "componentType": component, "count": count, "type": kind}
        if extremes is not None:
            acc["min"] = [float(v) for v in extremes[0]]
            acc["max"] = [float(v) for v in extremes[1]]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def add_node(self, name, positions_m, triangles, colour_keys):
        """positions_m: (n,3) float64 metres; triangles: (t,3) int; colour_keys: list per triangle."""
        primitives = []
        for key in sorted(set(colour_keys), key=lambda k: (k is None, k)):
            select = np.array([k == key for k in colour_keys])
            tris = triangles[select]
            # Flat shading: three vertices per triangle.
            p = positions_m[tris.reshape(-1)].astype(np.float32)
            a, b, c = p[0::3], p[1::3], p[2::3]
            n = np.cross(b - a, c - a)
            length = np.linalg.norm(n, axis=1, keepdims=True)
            n = np.where(length > 0, n / np.maximum(length, 1e-30), [0.0, 0.0, 1.0]).astype(np.float32)
            normals = np.repeat(n, 3, axis=0)
            indices = np.arange(len(p), dtype=np.uint32)
            pv = self._view(p.tobytes(), 34962)
            nv = self._view(normals.tobytes(), 34962)
            iv = self._view(indices.tobytes(), 34963)
            primitives.append(
                {
                    "attributes": {
                        "POSITION": self._accessor(pv, 5126, len(p), "VEC3", (p.min(0), p.max(0))),
                        "NORMAL": self._accessor(nv, 5126, len(p), "VEC3"),
                    },
                    "indices": self._accessor(iv, 5125, len(indices), "SCALAR"),
                    "material": self.material(key),
                    "mode": 4,
                }
            )
            self.triangles += len(tris)
        self.meshes.append({"name": name, "primitives": primitives})
        self.nodes.append({"name": name, "mesh": len(self.meshes) - 1})

    def write(self, path):
        children = list(range(1, len(self.nodes) + 1))
        gltf = {
            "asset": {"version": "2.0", "generator": self.generator},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"name": self.root_name, "children": children}] + self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.bin)}],
        }
        js = json.dumps(gltf, separators=(",", ":")).encode()
        while len(js) % 4:
            js += b" "
        bin_ = bytes(self.bin)
        while len(bin_) % 4:
            bin_ += b"\0"
        total = 12 + 8 + len(js) + 8 + len(bin_)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A))
            f.write(js)
            f.write(struct.pack("<II", len(bin_), 0x004E4942))
            f.write(bin_)


def source_checksum(source_path):
    """Look the source file up in the archive's download-verification.json."""
    directory = os.path.dirname(source_path)
    name = os.path.basename(source_path)
    verification = os.path.join(directory, "download-verification.json")
    if os.path.exists(verification):
        for entry in json.load(open(verification)).get("files", []):
            if entry["path"] == name:
                return entry["sha256"], "download-verification.json"
    return sha256(source_path), "computed"


def footprint(p, transforms, prow):
    """Largest placed XY footprint of a part's bodies, mm²."""
    best = 0.0
    for M in transforms.get(prow.get(p["product_id"]), [np.eye(4)]):
        for b in p["bodies"]:
            ext = np.abs(M[:3, :3]) @ (np.array(b["bbox_max"]) - np.array(b["bbox_min"]))
            best = max(best, ext[0] * ext[1])
    return best


def place(P_mm, M):
    """Part-frame millimetre positions to placed arena-frame metres."""
    return (P_mm @ M[:3, :3].T + M[:3, 3]) / 1000.0


def bbox_corners(body, M):
    """The eight corners of a body's STEP vertex box, placed, in metres."""
    corners = np.array(
        [[body["bbox_min"][j] if (c >> j) & 1 == 0 else body["bbox_max"][j] for j in range(3)] for c in range(8)]
    )
    return place(corners, M)


def bbox_check(world, corners):
    """How far the mesh box falls short of the vertex box and how far it
    exceeds it (metres): the mesh must cover the vertices; on curved faces it
    may legitimately reach a little beyond them."""
    missing_m = max(float((world.min(0) - corners.min(0)).max()), float((corners.max(0) - world.max(0)).max()))
    excess_m = max(float((corners.min(0) - world.min(0)).max()), float((world.max(0) - corners.max(0)).max()))
    return missing_m, excess_m


def height_at(P, T, x, y):
    """Highest z of a triangle mesh under (x, y), or None when nothing is there."""
    A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]

    def side(U, V):
        return (V[:, 0] - U[:, 0]) * (y - U[:, 1]) - (V[:, 1] - U[:, 1]) * (x - U[:, 0])

    d1, d2, d3 = side(A, B), side(B, C), side(C, A)
    inside = ((d1 >= 0) & (d2 >= 0) & (d3 >= 0)) | ((d1 <= 0) & (d2 <= 0) & (d3 <= 0))
    n = np.cross(B - A, C - A)
    inside &= np.abs(n[:, 2]) > 1e-12
    if not inside.any():
        return None
    a, n = A[inside], n[inside]
    z = a[:, 2] - (n[:, 0] * (x - a[:, 0]) + n[:, 1] * (y - a[:, 1])) / n[:, 2]
    return float(z.max())


class Donor:
    """Another split package of the same arena whose solids can be grafted
    in: its model and placements, and the top of its floor slab as a coarse
    mesh, so a graft can be re-based from that slab onto the recipient's."""

    def __init__(self, pkg, index, floor_name, lin, ang):
        self.pkg = pkg
        self.ix = Index(index)
        self.m = Model(self.ix)
        self.transforms = occurrence_transforms(self.ix, self.m)
        self.prow = {int(self.ix.ids[r]): r for r in self.m.product_name}
        parts_json = json.load(open(os.path.join(pkg, "parts.json")))
        self.source = parts_json["source"]
        self.by_name = {p["name"]: p for p in parts_json["parts"]}
        arena = [p for p in parts_json["parts"] if p["name"].startswith("BREP_")]
        self.floor = self.by_name[floor_name] if floor_name else max(arena, key=lambda p: footprint(p, self.transforms, self.prow))
        doc, rd, err = read_part(os.path.join(pkg, self.floor["file"]))
        mesh = None if err else tessellate(doc, lin, ang)
        if mesh is None:
            sys.exit(f"donor floor slab {self.floor['name']} unusable: {err or 'no triangulation'}")
        M = self.transforms.get(self.prow.get(self.floor["product_id"]), [np.eye(4)])[0]
        self.floor_P = place(mesh[0], M)
        self.floor_T = mesh[1]

    def placements(self, p):
        return self.transforms.get(self.prow.get(p["product_id"]), [np.eye(4)])

    def slab_plane(self, lo, hi):
        """Least-squares plane z = a x + b y + c (metres) through the slab top
        sampled on a 3 × 3 grid over the footprint lo..hi."""
        rows, zs = [], []
        for fx in (0.1, 0.5, 0.9):
            for fy in (0.1, 0.5, 0.9):
                x = lo[0] + fx * (hi[0] - lo[0])
                y = lo[1] + fy * (hi[1] - lo[1])
                z = height_at(self.floor_P, self.floor_T, x, y)
                if z is not None:
                    rows.append([x, y, 1.0])
                    zs.append(z)
        if len(rows) < 3:
            sys.exit(f"graft footprint {lo[:2]}..{hi[:2]} is off the donor floor slab")
        coeffs, *_ = np.linalg.lstsq(np.array(rows), np.array(zs), rcond=None)
        return coeffs


def graft_colour_keys(spec):
    keys = dict(item.split("=", 1) for item in spec.split(";") if item)
    if set(keys) != {"top", "side"}:
        sys.exit("--graft-colours must be top=R,G,B;side=R,G,B")
    return keys["top"], keys["side"]


def skipped_assemblies(m, ix, transforms, parts, exported):
    """The topmost products with solid bodies that export nothing: the rune,
    outpost, base and tech-core assemblies the equipment copy covers, and
    anything else the package leaves out. Listed so an omission is visible."""
    by_id = {p["product_id"]: p for p in parts}
    solids = ("MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS")

    def subtree(r):
        out = [r]
        for _, c in m.children.get(r, []):
            if c is not None:
                out += subtree(c)
        return out

    def exports(r):
        return any(m.product_name[q] in exported for q in subtree(r))

    def placed(r):
        pts, count = [], 0
        for q in subtree(r):
            bodies = by_id.get(int(ix.ids[q]), {}).get("bodies", [])
            count += sum(1 for b in bodies if b.get("type") in solids)
            for M in transforms.get(q, []):
                for b in bodies:
                    lo, hi = b["bbox_min"], b["bbox_max"]
                    corners = np.array([[lo[0] if c & 1 == 0 else hi[0], lo[1] if c & 2 == 0 else hi[1], lo[2] if c & 4 == 0 else hi[2], 1.0] for c in range(8)])
                    pts.append((M @ corners.T).T[:, :3] / 1000.0)
        return count, pts

    out = []
    seen = set()

    def walk(r):
        if r in seen or m.product_name[r] in exported:
            return
        seen.add(r)
        if exports(r):
            for _, c in m.children.get(r, []):
                if c is not None:
                    walk(c)
            return
        count, pts = placed(r)
        if count == 0:
            return
        P = np.vstack(pts)
        out.append(
            {
                "product": m.product_name[r],
                "product_id": int(ix.ids[r]),
                "occurrences": len(transforms.get(r, [])),
                "solids": count,
                "bbox_min_m": P.min(0).round(3).tolist(),
                "bbox_max_m": P.max(0).round(3).tolist(),
            }
        )

    for r in m.roots:
        walk(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pkg")
    ap.add_argument("index")
    ap.add_argument("--equipment", required=True, help="existing extraction with rune, outpost and equipment/")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lin", type=float, default=2.0, help="visual linear deflection, mm")
    ap.add_argument("--ang", type=float, default=0.35, help="visual angular deflection, rad")
    ap.add_argument("--collision-lin", type=float, default=10.0)
    ap.add_argument("--collision-ang", type=float, default=0.7)
    ap.add_argument("--floor", default=None, help="floor slab product name (default: largest footprint)")
    ap.add_argument(
        "--arena-products",
        default="0010_1,00_1",
        help="comma-separated names of products outside the BREP_* arena to export as arena solids "
        "(default: V1.2.0's base pedestals and the steps behind them, top-level products of their own)",
    )
    ap.add_argument(
        "--graft",
        action="append",
        default=[],
        metavar="PKG_DIR:INDEX_NPZ:NAME[,NAME...]",
        help="solids from another split package of the same arena to add as arena nodes, re-based from "
        "that package's floor slab onto this one's (V2.0.0's 起伏路段 undulating road is BREP_220,BREP_192; "
        "the V1.2.0 STEP has a flat deck there)",
    )
    ap.add_argument("--graft-floor", default=None, help="donor floor slab product name (default: largest footprint)")
    ap.add_argument(
        "--graft-colours",
        default=GRAFT_COLOURS,
        help="colour keys for grafted faces, upward faces and the rest (default: V1.2.0's plate top and side)",
    )
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"{a.out} exists; the output directory must be new")
    t0 = time.time()
    ix = Index(a.index)
    m = Model(ix)
    transforms = occurrence_transforms(ix, m)
    prow = {int(ix.ids[r]): r for r in m.product_name}
    manifest_in = json.load(open(os.path.join(a.pkg, "parts.json")))
    extra = {n for n in a.arena_products.split(",") if n}
    arena = [p for p in manifest_in["parts"] if p["name"].startswith("BREP_") or p["name"] in extra]
    missing = extra - {p["name"] for p in arena}
    if missing:
        sys.exit(f"--arena-products not in the package: {sorted(missing)}")
    print(f"model ready in {time.time() - t0:.1f}s; {len(arena)} arena parts", flush=True)
    skipped = skipped_assemblies(m, ix, transforms, manifest_in["parts"], {p["name"] for p in arena})
    for e in skipped:
        print(
            f"skipped {e['product']} (id {e['product_id']}, {e['occurrences']} occurrences, {e['solids']} solids)"
            f" bbox {e['bbox_min_m']}..{e['bbox_max_m']}: not arena; expected from the equipment copy",
            flush=True,
        )

    # Floor: the arena part with the largest XY footprint after placement.
    floor_name = a.floor or max(arena, key=lambda p: footprint(p, transforms, prow))["name"]
    print("floor slab:", floor_name)

    generator = "rm-map-tools export_field_package.py"
    visual = {"floor": GlbWriter("FLOOR", generator), "arena-static": GlbWriter("ARENA-STATIC", generator)}
    collision = {
        "floor": GlbWriter("FLOOR_COLLISION", generator),
        "arena-static": GlbWriter("ARENA-STATIC_COLLISION", generator),
    }
    report = {"floor": [], "arena-static": []}
    failures = []
    bbox_errors = []
    for i, p in enumerate(arena):
        asset = "floor" if p["name"] == floor_name else "arena-static"
        doc, rd, err = read_part(os.path.join(a.pkg, p["file"]))
        if err:
            failures.append({"part": p["name"], "error": err})
            continue
        # Coarse first: the incremental mesher only refines an existing triangulation.
        coarse = tessellate(doc, a.collision_lin, a.collision_ang)
        fine = tessellate(doc, a.lin, a.ang)
        del doc, rd
        if fine is None or coarse is None:
            failures.append({"part": p["name"], "error": "no triangulation"})
            continue
        for k, M in enumerate(transforms.get(prow.get(p["product_id"]), [np.eye(4)])):
            name = f"source_{p['product_id']}_{p['name']}" + (f"_{k}" if k else "")
            flip = np.linalg.det(M[:3, :3]) < 0
            for writer, (P, T, C, cols) in ((visual[asset], fine), (collision[asset], coarse)):
                world = place(P, M)
                tris = T[:, [0, 2, 1]] if flip else T
                writer.add_node(name, world, tris, [cols[c] for c in C])
            P, T, C, cols = fine
            world = place(P, M)
            entry = {
                "node": name,
                "product_id": p["product_id"],
                "part_file": p["file"],
                "instance": k,
                "triangles": int(len(T)),
                "collision_triangles": int(len(coarse[1])),
                "colours_srgb": {c: int((C == j).sum()) for j, c in enumerate(cols)},
                "bbox_min_m": world.min(0).round(6).tolist(),
                "bbox_max_m": world.max(0).round(6).tolist(),
            }
            # The mesh box must agree with the exact vertex box of the STEP text scan.
            for b in p["bodies"]:
                missing_m, excess_m = bbox_check(world, bbox_corners(b, M))
                entry["bbox_missing_m"] = round(missing_m, 6)
                entry["bbox_excess_m"] = round(excess_m, 6)
                if missing_m > 0.002 or excess_m > 0.1:
                    bbox_errors.append({"node": name, "missing_m": missing_m, "excess_m": excess_m})
            report[asset].append(entry)
        if (i + 1) % 50 == 0:
            print(f"[{i + 1}/{len(arena)}] {visual['arena-static'].triangles} arena triangles", flush=True)

    floor_top = max(e["bbox_max_m"][2] for e in report["floor"])
    grafted = []
    top_key, side_key = graft_colour_keys(a.graft_colours)
    for spec in a.graft:
        pkg_dir, index, names = spec.split(":")
        donor = Donor(pkg_dir, index, a.graft_floor, a.collision_lin, a.collision_ang)
        donor_hash, donor_hash_origin = source_checksum(donor.source)
        print(f"graft donor {donor.source}: floor slab {donor.floor['name']}", flush=True)
        for gname in names.split(","):
            p = donor.by_name.get(gname)
            if p is None:
                sys.exit(f"--graft: {gname} is not in {pkg_dir}")
            doc, rd, err = read_part(os.path.join(pkg_dir, p["file"]))
            coarse = None if err else tessellate(doc, a.collision_lin, a.collision_ang)
            fine = None if err else tessellate(doc, a.lin, a.ang)
            if fine is None or coarse is None:
                sys.exit(f"--graft: {gname} unusable: {err or 'no triangulation'}")
            for k, M in enumerate(donor.placements(p)):
                node = f"graft_{p['product_id']}_{gname}" + (f"_{k}" if k else "")
                flip = np.linalg.det(M[:3, :3]) < 0
                placed = place(fine[0], M)
                plane = donor.slab_plane(placed.min(0), placed.max(0))

                def rebase(world):
                    # Take the donor slab's local tilt out and set the solid on this floor.
                    out = world.copy()
                    out[:, 2] += floor_top - (plane[0] * world[:, 0] + plane[1] * world[:, 1] + plane[2])
                    return out

                colours = {}
                for writer, (P, T, C, cols) in ((visual["arena-static"], fine), (collision["arena-static"], coarse)):
                    world = rebase(place(P, M))
                    tris = T[:, [0, 2, 1]] if flip else T
                    n = np.cross(world[tris[:, 1]] - world[tris[:, 0]], world[tris[:, 2]] - world[tris[:, 0]])
                    up = n[:, 2] > 0.5 * np.linalg.norm(n, axis=1)
                    keys = [top_key if u else side_key for u in up]
                    writer.add_node(node, world, tris, keys)
                    if writer is visual["arena-static"]:
                        colours = {top_key: int(up.sum()), side_key: int((~up).sum())}
                world = rebase(placed)
                entry = {
                    "node": node,
                    "product_id": p["product_id"],
                    "part_file": p["file"],
                    "instance": k,
                    "triangles": int(len(fine[1])),
                    "collision_triangles": int(len(coarse[1])),
                    "colours_srgb": colours,
                    "bbox_min_m": world.min(0).round(6).tolist(),
                    "bbox_max_m": world.max(0).round(6).tolist(),
                    "graft": {
                        "source_file": donor.source,
                        "source_sha256": donor_hash,
                        "donor_slab_plane_z_m": [round(float(c), 6) for c in plane],
                        "floor_top_source_z_m": round(floor_top, 6),
                    },
                }
                # Checked before the re-base: the shear would move a wavy top's
                # crest against a vertex box that only holds the edge vertices.
                for b in p["bodies"]:
                    missing_m, excess_m = bbox_check(placed, bbox_corners(b, M))
                    entry["bbox_missing_m"] = round(missing_m, 6)
                    entry["bbox_excess_m"] = round(excess_m, 6)
                    if missing_m > 0.002 or excess_m > 0.1:
                        bbox_errors.append({"node": node, "missing_m": missing_m, "excess_m": excess_m})
                report["arena-static"].append(entry)
                grafted.append(
                    {
                        "node": node,
                        "product": gname,
                        "product_id": p["product_id"],
                        "source_file": donor.source,
                        "source_sha256": donor_hash,
                        "source_sha256_origin": donor_hash_origin,
                    }
                )
                print(
                    f"graft {node}: donor slab tilt {plane[0] * 100:+.2f}% x {plane[1] * 100:+.2f}% y; "
                    f"top {world[:, 2].max() - floor_top:.3f} m above the floor, "
                    f"{len(fine[1])} / {len(coarse[1])} triangles",
                    flush=True,
                )

    os.makedirs(a.out)
    files = {}
    for asset in ("floor", "arena-static"):
        for kind, writer in (("visual", visual[asset]), ("collision", collision[asset])):
            name = f"{asset}.glb" if kind == "visual" else f"{asset}-collision.glb"
            writer.write(os.path.join(a.out, name))
            files[(asset, kind)] = name
    floor_box = (
        np.min([e["bbox_min_m"] for e in report["floor"]], axis=0).tolist(),
        np.max([e["bbox_max_m"] for e in report["floor"]], axis=0).tolist(),
    )

    # Carry the articulated equipment over from the earlier extraction.
    old = json.load(open(os.path.join(a.equipment, "manifest.json")))
    assets = {}
    for asset in ("floor", "arena-static"):
        assets[asset] = {
            "visual": files[(asset, "visual")],
            "visual_sha256": sha256(os.path.join(a.out, files[(asset, "visual")])),
            "collision": files[(asset, "collision")],
            "collision_sha256": sha256(os.path.join(a.out, files[(asset, "collision")])),
            "source_products": sorted({e["product_id"] for e in report[asset] if "graft" not in e}),
            "placements_in_source_arena_frame": [],
            "nodes": len(report[asset]),
            "triangles": sum(e["triangles"] for e in report[asset]),
            "collision_triangles": sum(e["collision_triangles"] for e in report[asset]),
            "colours_srgb": sorted({c for e in report[asset] for c in e["colours_srgb"]}),
        }
        if asset == "arena-static" and grafted:
            assets[asset]["grafted"] = grafted
    carried = {}
    for name in ("rune", "outpost"):
        entry = dict(old["assets"][name])
        for key in ("visual", "collision"):
            src = os.path.join(a.equipment, entry[key])
            shutil.copyfile(src, os.path.join(a.out, entry[key]))
            entry[f"{key}_sha256"] = sha256(os.path.join(a.out, entry[key]))
        entry["carried_from"] = {"directory": a.equipment, "source_sha256": old.get("source_sha256")}
        assets[name] = entry
        carried[name] = entry[f"visual_sha256"]
    equipment_dir = os.path.join(a.equipment, "equipment")
    if os.path.isdir(equipment_dir):
        shutil.copytree(equipment_dir, os.path.join(a.out, "equipment"))
        for name, entry in json.load(open(os.path.join(equipment_dir, "manifest.json")))["assets"].items():
            carried[f"equipment/{name}"] = entry["visual_sha256"]

    source_path = manifest_in["source"]
    source_hash, hash_origin = source_checksum(source_path)
    manifest = {
        "schema_version": 1,
        "generator": generator,
        "units": "metres",
        "source_file": source_path,
        "source_sha256": source_hash,
        "source_sha256_origin": hash_origin,
        "split_package": {"parts_json_source": manifest_in["source"], "parts": len(manifest_in["parts"])},
        "arena_frame": ARENA_FRAME,
        "source_to_y_up_rotation_xyzw": SOURCE_TO_Y_UP_XYZW,
        "floor_top_source_z_m": round(floor_top, 6),
        "floor_slab": floor_name,
        "tessellation": {
            "visual": {"linear_deflection_mm": a.lin, "angular_deflection_rad": a.ang},
            "collision": {"linear_deflection_mm": a.collision_lin, "angular_deflection_rad": a.collision_ang},
        },
        "collision_contract": COLLISION_CONTRACT,
        "collision_solids": True,
        "materials": MATERIALS,
        "assets": assets,
    }
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"), indent=2, ensure_ascii=False)
    validation = {
        "ok": not failures and not bbox_errors,
        "arena_parts": len(arena),
        "read_failures": failures,
        "bbox_mismatches": bbox_errors,
        "floor_top_source_z_m": round(floor_top, 6),
        "floor_bbox_m": floor_box,
        "arena_bbox_m": [
            np.min([e["bbox_min_m"] for k in report for e in report[k]], axis=0).tolist(),
            np.max([e["bbox_max_m"] for k in report for e in report[k]], axis=0).tolist(),
        ],
        "carried_equipment_sha256": carried,
        "skipped_assemblies": skipped,
        "grafted": grafted,
        "seconds": round(time.time() - t0, 1),
        "nodes": report,
    }
    json.dump(validation, open(os.path.join(a.out, "validation.json"), "w"), indent=1)
    for asset in ("floor", "arena-static"):
        print(
            f"{asset}: {assets[asset]['nodes']} nodes, {assets[asset]['triangles']} visual / "
            f"{assets[asset]['collision_triangles']} collision triangles, colours {assets[asset]['colours_srgb']}"
        )
    print(f"floor top z = {floor_top:.4f} m; failures {len(failures)}; bbox mismatches {len(bbox_errors)}; {time.time() - t0:.0f}s")
    if failures or bbox_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
