#!/usr/bin/env python3
"""Export the arena of a split field package as the simulator asset package.

Writes the manifest schema the simulators (`rm-simulator`, `rm-vision-sim`)
already load: `floor.glb`, `arena-static.glb`, their `*-collision.glb`
proxies, `manifest.json` with SHA-256 checksums, and `validation.json`.
The articulated equipment (rune, outpost) and the rigid equipment directory
(base, tech core) are carried over from an existing extraction, since
their placements are in the same arena frame.

Every arena body (`BREP_*` product) is read from its split part file with
OCCT, tessellated, placed by the STEP assembly transforms and written as one
glTF node named `source_<product id>_<product name>[_<instance>]`, with one
primitive per effective face colour (face > shell > body). Coordinates stay
in the CAD arena frame (Z up) converted to metres, exactly like the earlier
extraction, so consumers keep their arena transform.

Usage:
  export_field_package.py <pkg_dir> <index.npz> --equipment <extracted_dir>
      --out <dir> [--lin 2] [--ang 0.35] [--collision-lin 10]
      [--collision-ang 0.7] [--floor NAME]

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
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"{a.out} exists; the output directory must be new")
    t0 = time.time()
    ix = Index(a.index)
    m = Model(ix)
    transforms = occurrence_transforms(ix, m)
    prow = {int(ix.ids[r]): r for r in m.product_name}
    manifest_in = json.load(open(os.path.join(a.pkg, "parts.json")))
    arena = [p for p in manifest_in["parts"] if p["name"].startswith("BREP_")]
    print(f"model ready in {time.time() - t0:.1f}s; {len(arena)} arena parts", flush=True)

    # Floor: the arena part with the largest XY footprint after placement.
    def footprint(p):
        best = 0.0
        for M in transforms.get(prow.get(p["product_id"]), [np.eye(4)]):
            for b in p["bodies"]:
                ext = np.abs(M[:3, :3]) @ (np.array(b["bbox_max"]) - np.array(b["bbox_min"]))
                best = max(best, ext[0] * ext[1])
        return best

    floor_name = a.floor or max(arena, key=footprint)["name"]
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
                world = (P @ M[:3, :3].T + M[:3, 3]) / 1000.0
                tris = T[:, [0, 2, 1]] if flip else T
                writer.add_node(name, world, tris, [cols[c] for c in C])
            P, T, C, cols = fine
            world = (P @ M[:3, :3].T + M[:3, 3]) / 1000.0
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
                corners = np.array(
                    [
                        [b["bbox_min"][j] if (c >> j) & 1 == 0 else b["bbox_max"][j] for j in range(3)]
                        for c in range(8)
                    ]
                )
                corners = (corners @ M[:3, :3].T + M[:3, 3]) / 1000.0
                # The mesh must cover the vertex box; on curved faces it may
                # legitimately reach a little beyond the vertices.
                missing_m = max(
                    float((world.min(0) - corners.min(0)).max()),
                    float((corners.max(0) - world.max(0)).max()),
                )
                excess_m = max(
                    float((corners.min(0) - world.min(0)).max()),
                    float((world.max(0) - corners.max(0)).max()),
                )
                entry["bbox_missing_m"] = round(missing_m, 6)
                entry["bbox_excess_m"] = round(excess_m, 6)
                if missing_m > 0.002 or excess_m > 0.1:
                    bbox_errors.append({"node": name, "missing_m": missing_m, "excess_m": excess_m})
            report[asset].append(entry)
        if (i + 1) % 50 == 0:
            print(f"[{i + 1}/{len(arena)}] {visual['arena-static'].triangles} arena triangles", flush=True)

    os.makedirs(a.out)
    files = {}
    for asset in ("floor", "arena-static"):
        for kind, writer in (("visual", visual[asset]), ("collision", collision[asset])):
            name = f"{asset}.glb" if kind == "visual" else f"{asset}-collision.glb"
            writer.write(os.path.join(a.out, name))
            files[(asset, kind)] = name
    floor_top = max(e["bbox_max_m"][2] for e in report["floor"])
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
            "source_products": sorted({e["product_id"] for e in report[asset]}),
            "placements_in_source_arena_frame": [],
            "nodes": len(report[asset]),
            "triangles": sum(e["triangles"] for e in report[asset]),
            "collision_triangles": sum(e["collision_triangles"] for e in report[asset]),
            "colours_srgb": sorted({c for e in report[asset] for c in e["colours_srgb"]}),
        }
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
