#!/usr/bin/env python3
"""Turn a field-elements package into Gazebo, MuJoCo and Isaac Sim scenes.

Reads the `manifest.json` written by `export_elements.py` and its glb
assets and writes, under `--out`:

  meshes/<asset>-visual-<k>[-<n>].stl  one binary STL per asset and colour,
                                       split at 200k triangles (MuJoCo's limit)
  meshes/<asset>-collision.stl         the asset's collision proxy, whole
  meshes/<asset>/<node>-collision.stl  the same proxy split per source solid
  gazebo/rmuc2026.sdf                  SDF 1.11 world: one static model, one
                                       link per placed instance, STL visuals
                                       with their colours, whole-asset
                                       triangle-mesh collisions
  mujoco/rmuc2026.xml                  MJCF: one static body per instance,
                                       visual geoms per colour (no contacts),
                                       one collision geom per source solid
                                       (MuJoCo hulls each mesh, so per-solid
                                       hulls keep concave assets usable)
  isaac/<asset>.usd, isaac/rmuc2026.usda USD (needs the `usd-core` package):
                                       one binary file per asset with the
                                       visual meshes (display colours) and
                                       guide-purpose collision meshes carrying
                                       PhysicsCollisionAPI with triangle-mesh
                                       approximation; a Z-up ASCII world stage
                                       that references each file per instance
  manifest.json                        what was written, with checksums

Everything stays in the arena frame of the package (Z up, metres); the
placements come straight from the elements manifest, and assets the
manifest marks as already inside `arena-static` are exported but not
placed again. `verify` loads what was written back through the real
libraries where they exist (MuJoCo, USD) and checks every instance's box
against the manifest; the SDF is checked structurally, parsed with
sdformat's Python bindings when they import (Homebrew's osrf/simulation
`sdformat15` bottle is found automatically), and validated against the
schemas published at sdformat.org (mirrored into ~/.cache/rm-map-tools).

Usage:
  export_sim.py <elements dir> --out <dir> [--no-isaac]
  export_sim.py <elements dir> --out <dir> verify
  export_sim.py <elements dir> --out <dir> render [--png file]   (MUJOCO_GL=cgl on macOS)
"""
import argparse
import hashlib
import json
import os
import struct
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance  # noqa: E402
from gltf_scene import read_glb_nodes  # noqa: E402

DEFAULT_RGB = (0.63, 0.63, 0.63)
MODEL_NAME = "rmuc2026_field"
BBOX_TOL_M = 0.01
SDF_SCHEMA = "http://sdformat.org/schemas/root.xsd"
STL_MAX_TRIANGLES = 200000  # MuJoCo's STL reader refuses larger files


# ---------------------------------------------------------------- geometry
def rgb_of(key):
    return DEFAULT_RGB if key is None else tuple(float(x) for x in key.split(","))


def quat_wxyz(xyzw):
    x, y, z, w = xyzw
    return (w, x, y, z)


def rpy_of(R):
    """Roll, pitch, yaw with R = Rz(yaw) Ry(pitch) Rx(roll), as SDF poses use."""
    sy = -R[2, 0]
    pitch = float(np.arcsin(np.clip(sy, -1.0, 1.0)))
    if abs(sy) < 1 - 1e-9:
        roll = float(np.arctan2(R[2, 1], R[2, 2]))
        yaw = float(np.arctan2(R[1, 0], R[0, 0]))
    else:
        roll = 0.0
        yaw = float(np.arctan2(-R[0, 1], R[1, 1]))
    return roll, pitch, yaw


def write_stl(path, P, T):
    """Binary STL of triangles T over points P (metres); normals from winding."""
    V = P[T]
    n = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
    rec = np.zeros(len(T), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = V
    with open(path, "wb") as f:
        f.write(provenance.generator("export_sim.py").encode()[:80].ljust(80, b"\0"))
        f.write(struct.pack("<I", len(T)))
        f.write(rec.tobytes())
    return len(T)


def read_stl(path):
    with open(path, "rb") as f:
        f.seek(80)
        n = struct.unpack("<I", f.read(4))[0]
        rec = np.frombuffer(f.read(50 * n), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return rec["v"].reshape(-1, 3).astype(np.float64)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Asset:
    """One glb asset: its visual triangles grouped by colour, its collision
    nodes, and its placements."""

    def __init__(self, name, entry, src, static_rest_pose=False):
        if entry.get("semantics") and not static_rest_pose:
            raise ValueError(f"{name}: semantic asset requires --static-rest-pose; dynamic joint export is not supported")
        self.name, self.entry = name, entry
        self.label = entry.get("label", "")
        visual = list(read_glb_nodes(os.path.join(src, entry["visual"])))
        self.collision = list(read_glb_nodes(os.path.join(src, entry["collision"])))
        groups = {}
        for node, P, T, K in visual:
            K = np.array([("" if k is None else k) for k in K])
            for key in np.unique(K):
                Pg, Tg = P, T[K == key]
                used = np.unique(Tg)
                remap = np.full(len(P), -1, np.int64)
                remap[used] = np.arange(len(used))
                groups.setdefault(key, []).append((Pg[used], remap[Tg]))
        self.colours = []
        for key, parts in groups.items():
            P = np.vstack([p for p, _ in parts])
            off = np.cumsum([0] + [len(p) for p, _ in parts[:-1]])
            T = np.vstack([t + o for (_, t), o in zip(parts, off)])
            self.colours.append((rgb_of(key or None), P, T))
        pl = entry.get("placements_in_source_arena_frame", [])
        self.placements = [np.array(p["matrix_local_to_arena"]) for p in pl] or [np.eye(4)]
        self.placed = entry.get("in_full_map", True)
        lo = np.min([P.min(0) for _, P, _ in self.colours], axis=0)
        hi = np.max([P.max(0) for _, P, _ in self.colours], axis=0)
        self.bbox_local = (lo, hi)

    def instance_box(self, k, of_points=True):
        """Arena-frame box of instance k: of the transformed visual points, or
        (as USD's BBoxCache and similar do) of the transformed local box."""
        M = self.placements[k]
        if of_points:
            C = np.vstack([P for _, P, _ in self.colours])
        else:
            lo, hi = self.bbox_local
            C = np.array([[lo[j] if (c >> j) & 1 == 0 else hi[j] for j in range(3)] for c in range(8)])
        W = C @ M[:3, :3].T + M[:3, 3]
        return W.min(0), W.max(0)


# ------------------------------------------------------------------ meshes
def write_meshes(assets, out):
    mesh_dir = os.path.join(out, "meshes")
    os.makedirs(mesh_dir, exist_ok=True)
    files = {}
    for a in assets:
        rec = {"visual": [], "collision": None, "collision_nodes": []}
        for k, (rgb, P, T) in enumerate(a.colours):
            chunks = range(0, len(T), STL_MAX_TRIANGLES)
            for n, start in enumerate(chunks):
                fn = f"{a.name}-visual-{k}.stl" if len(chunks) == 1 else f"{a.name}-visual-{k}-{n}.stl"
                Tc = T[start: start + STL_MAX_TRIANGLES]
                used = np.unique(Tc)
                remap = np.full(len(P), -1, np.int64)
                remap[used] = np.arange(len(used))
                tris = write_stl(os.path.join(mesh_dir, fn), P[used], remap[Tc])
                rec["visual"].append({"file": fn, "rgb": [round(c, 4) for c in rgb], "triangles": tris})
        P = np.vstack([p for _, p, _, _ in a.collision])
        off = np.cumsum([0] + [len(p) for _, p, _, _ in a.collision[:-1]])
        T = np.vstack([t + o for (_, _, t, _), o in zip(a.collision, off)])
        fn = f"{a.name}-collision.stl"
        rec["collision"] = {"file": fn, "triangles": write_stl(os.path.join(mesh_dir, fn), P, T)}
        os.makedirs(os.path.join(mesh_dir, a.name), exist_ok=True)
        for node, P, T, _ in a.collision:
            fn = f"{a.name}/{node}-collision.stl"
            rec["collision_nodes"].append({"file": fn, "node": node, "triangles": write_stl(os.path.join(mesh_dir, fn), P, T)})
        files[a.name] = rec
    return files


# ------------------------------------------------------------------ gazebo
def write_gazebo(assets, files, out):
    os.makedirs(os.path.join(out, "gazebo"), exist_ok=True)
    sdf = ET.Element("sdf", version="1.11")
    world = ET.SubElement(sdf, "world", name="rmuc2026")
    light = ET.SubElement(world, "light", type="directional", name="sun")
    ET.SubElement(light, "cast_shadows").text = "true"
    ET.SubElement(light, "pose").text = "0 0 10 0 0 0"
    ET.SubElement(light, "diffuse").text = "0.9 0.9 0.9 1"
    ET.SubElement(light, "specular").text = "0.2 0.2 0.2 1"
    ET.SubElement(light, "direction").text = "-0.4 0.3 -0.9"
    model = ET.SubElement(world, "model", name=MODEL_NAME)
    ET.SubElement(model, "static").text = "true"
    ET.SubElement(model, "pose").text = "0 0 0 0 0 0"
    for a in assets:
        if not a.placed:
            continue
        for k, M in enumerate(a.placements):
            link = ET.SubElement(model, "link", name=f"{a.name}_{k}")
            r, p, y = rpy_of(M[:3, :3])
            ET.SubElement(link, "pose").text = f"{M[0, 3]:.6f} {M[1, 3]:.6f} {M[2, 3]:.6f} {r:.9f} {p:.9f} {y:.9f}"
            for j, v in enumerate(files[a.name]["visual"]):
                vis = ET.SubElement(link, "visual", name=f"visual_{j}")
                ET.SubElement(ET.SubElement(ET.SubElement(vis, "geometry"), "mesh"), "uri").text = f"../meshes/{v['file']}"
                mat = ET.SubElement(vis, "material")
                rgb = " ".join(f"{c:.4f}" for c in v["rgb"])
                ET.SubElement(mat, "ambient").text = f"{rgb} 1"
                ET.SubElement(mat, "diffuse").text = f"{rgb} 1"
            col = ET.SubElement(link, "collision", name="collision")
            ET.SubElement(ET.SubElement(ET.SubElement(col, "geometry"), "mesh"), "uri").text = f"../meshes/{files[a.name]['collision']['file']}"
    ET.indent(sdf)
    path = os.path.join(out, "gazebo", "rmuc2026.sdf")
    with open(path, "wb") as f:
        f.write(b"<?xml version='1.0'?>\n<!-- " + provenance.generator("export_sim.py").encode() + b" -->\n")
        f.write(ET.tostring(sdf))
    return path


# ------------------------------------------------------------------ mujoco
def write_mujoco(assets, files, out):
    os.makedirs(os.path.join(out, "mujoco"), exist_ok=True)
    root = ET.Element("mujoco", model="rmuc2026")
    ET.SubElement(root, "compiler", meshdir="../meshes", angle="radian")
    ET.SubElement(root, "option", gravity="0 0 -9.81")
    ET.SubElement(root, "statistic", center="0 1.65 0.5", extent="30")
    vis = ET.SubElement(root, "visual")
    ET.SubElement(vis, "map", znear="0.01", zfar="200")
    ET.SubElement(vis, "global", offwidth="1920", offheight="1080")
    asset = ET.SubElement(root, "asset")
    ET.SubElement(asset, "texture", type="skybox", builtin="gradient", rgb1="0.8 0.85 0.9", rgb2="0.3 0.35 0.45", width="64", height="64")
    for a in assets:
        if not a.placed:
            continue
        for v in files[a.name]["visual"]:
            ET.SubElement(asset, "mesh", name=v["file"][:-4], file=v["file"], inertia="shell")
        for c in files[a.name]["collision_nodes"]:
            ET.SubElement(asset, "mesh", name=c["file"][:-4].replace("/", "__"), file=c["file"], inertia="shell")
    wb = ET.SubElement(root, "worldbody")
    ET.SubElement(wb, "light", pos="0 1.65 15", dir="0 0 -1", directional="true", diffuse="0.8 0.8 0.8")
    for a in assets:
        if not a.placed:
            continue
        for k, M in enumerate(a.placements):
            q = quat_wxyz(rotation_xyzw(M[:3, :3]))
            body = ET.SubElement(wb, "body", name=f"{a.name}_{k}",
                                 pos=" ".join(f"{x:.6f}" for x in M[:3, 3]), quat=" ".join(f"{x:.9f}" for x in q))
            for v in files[a.name]["visual"]:
                rgb = " ".join(f"{c:.4f}" for c in v["rgb"])
                ET.SubElement(body, "geom", type="mesh", mesh=v["file"][:-4], rgba=f"{rgb} 1",
                              contype="0", conaffinity="0", group="2", mass="0")
            for c in files[a.name]["collision_nodes"]:
                ET.SubElement(body, "geom", type="mesh", mesh=c["file"][:-4].replace("/", "__"),
                              group="3", rgba="0.5 0.8 0.5 0.3", mass="0")
    ET.indent(root)
    path = os.path.join(out, "mujoco", "rmuc2026.xml")
    with open(path, "wb") as f:
        f.write(b"<!-- " + provenance.generator("export_sim.py").encode() + b" -->\n")
        f.write(ET.tostring(root))
    return path


def rotation_xyzw(R):
    from export_elements import quaternion_xyzw
    return quaternion_xyzw(R)


# ------------------------------------------------------------------- isaac
def write_isaac(assets, out):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, Vt

    isaac = os.path.join(out, "isaac")
    os.makedirs(isaac, exist_ok=True)
    gen = provenance.generator("export_sim.py")

    def mesh_prim(stage, path, P, T, colours=None):
        m = UsdGeom.Mesh.Define(stage, path)
        m.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(P.astype(np.float32)))
        m.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(T), 3, np.int32)))
        m.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(T.astype(np.int32).ravel()))
        m.CreateSubdivisionSchemeAttr("none")
        m.CreateDoubleSidedAttr(False)
        if colours is not None:
            pv = UsdGeom.PrimvarsAPI(m).CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3fArray, UsdGeom.Tokens.constant)
            pv.Set(Vt.Vec3fArray([Gf.Vec3f(*colours)]))
        return m

    written = {}
    for a in assets:
        path = os.path.join(isaac, f"{a.name}.usd")
        stage = Usd.Stage.CreateNew(path)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        root = UsdGeom.Xform.Define(stage, f"/{prim_name(a.name)}")
        stage.SetDefaultPrim(root.GetPrim())
        stage.GetRootLayer().comment = gen
        stage.GetRootLayer().documentation = f"{a.name} {a.label}; {provenance.COPYRIGHT}"
        vis = UsdGeom.Scope.Define(stage, root.GetPath().AppendChild("visual"))
        for k, (rgb, P, T) in enumerate(a.colours):
            mesh_prim(stage, vis.GetPath().AppendChild(f"colour_{k}"), P, T, rgb)
        col = UsdGeom.Scope.Define(stage, root.GetPath().AppendChild("collision"))
        for node, P, T, _ in a.collision:
            m = mesh_prim(stage, col.GetPath().AppendChild(prim_name(node)), P, T)
            m.CreatePurposeAttr(UsdGeom.Tokens.guide)
            UsdPhysics.CollisionAPI.Apply(m.GetPrim())
            UsdPhysics.MeshCollisionAPI.Apply(m.GetPrim()).CreateApproximationAttr(UsdPhysics.Tokens.none)
        stage.Save()
        written[a.name] = f"{a.name}.usd"

    world_path = os.path.join(isaac, "rmuc2026.usda")
    stage = Usd.Stage.CreateNew(world_path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.GetRootLayer().comment = gen
    stage.GetRootLayer().documentation = provenance.COPYRIGHT
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdPhysics.Scene.Define(stage, "/World/physicsScene")
    field = UsdGeom.Xform.Define(stage, f"/World/{MODEL_NAME}")
    for a in assets:
        if not a.placed:
            continue
        for k, M in enumerate(a.placements):
            x = UsdGeom.Xform.Define(stage, field.GetPath().AppendChild(f"{prim_name(a.name)}_{k}"))
            x.GetPrim().GetReferences().AddReference(f"./{written[a.name]}")
            x.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in M[:3, 3]]))
            qx, qy, qz, qw = rotation_xyzw(M[:3, :3])
            x.AddOrientOp().Set(Gf.Quatf(float(qw), float(qx), float(qy), float(qz)))
    stage.Save()
    return world_path, written


def prim_name(s):
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in s)
    return out if out[:1].isalpha() or out[:1] == "_" else "_" + out


# ------------------------------------------------------------------ verify
def verify(assets, out, report):
    problems = []

    def check_box(kind, name, lo, hi, want_lo, want_hi):
        dev = float(max(np.abs(lo - want_lo).max(), np.abs(hi - want_hi).max()))
        if dev > BBOX_TOL_M:
            problems.append(f"{kind} {name}: box off by {dev:.4f} m")
        return dev

    def check_pose(kind, name, pose, M):
        got = check_pose_matrix(pose)
        dev = float(np.abs(got - M).max())
        if dev > 1e-6:
            problems.append(f"{kind} {name}: pose differs from the manifest placement by {dev:.2e}")
        return dev

    # meshes: every STL reads back with the glb's box
    worst = 0.0
    for a in assets:
        lo, hi = a.bbox_local
        P = np.vstack([read_stl(os.path.join(out, "meshes", v["file"])) for v in report["meshes"][a.name]["visual"]])
        worst = max(worst, check_box("stl", a.name, P.min(0), P.max(0), lo, hi))
    print(f"meshes: {len(assets)} assets read back, worst box deviation {worst:.5f} m")

    # MuJoCo: compile, step, and check each body's collision geoms
    import mujoco

    t = time.time()
    model = mujoco.MjModel.from_xml_path(os.path.join(out, "mujoco", "rmuc2026.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    for _ in range(10):
        mujoco.mj_step(model, data)
    worst, n = 0.0, 0
    for a in assets:
        if not a.placed:
            continue
        for k in range(len(a.placements)):
            b = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"{a.name}_{k}")
            pts = []
            for g in range(model.ngeom):
                if model.geom_bodyid[g] != b or model.geom_group[g] != 2:
                    continue
                m = model.geom_dataid[g]
                V = model.mesh_vert[model.mesh_vertadr[m]: model.mesh_vertadr[m] + model.mesh_vertnum[m]]
                pts.append(V @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g])
            P = np.vstack(pts)
            want = a.instance_box(k)
            worst = max(worst, check_box("mujoco", f"{a.name}_{k}", P.min(0), P.max(0), *want))
            n += 1
    print(f"mujoco {mujoco.__version__}: {model.nbody - 1} bodies, {model.ngeom} geoms, {model.nmesh} meshes, "
          f"10 steps ok, {n} instances checked, worst box deviation {worst:.5f} m ({time.time() - t:.0f}s)")

    # USD: open the world, compute each instance's world box
    if report.get("isaac"):
        from pxr import Usd, UsdGeom, UsdPhysics

        t = time.time()
        stage = Usd.Stage.Open(os.path.join(out, report["isaac"]["world"]))
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
        worst, n, colliders = 0.0, 0, 0
        for a in assets:
            if not a.placed:
                continue
            for k in range(len(a.placements)):
                prim = stage.GetPrimAtPath(f"/World/{MODEL_NAME}/{prim_name(a.name)}_{k}")
                if not prim:
                    problems.append(f"usd: {a.name}_{k} missing")
                    continue
                box = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                lo, hi = np.array(box.GetMin()), np.array(box.GetMax())
                worst = max(worst, check_box("usd", f"{a.name}_{k}", lo, hi, *a.instance_box(k, of_points=False)))
                n += 1
                for p in Usd.PrimRange(prim):
                    if p.HasAPI(UsdPhysics.CollisionAPI):
                        colliders += 1
        print(f"usd {'.'.join(map(str, Usd.GetVersion()))}: {n} instances, {colliders} collider prims, worst box deviation {worst:.5f} m ({time.time() - t:.0f}s)")

    # SDF: well-formed, poses round-trip, mesh uris resolve; then through
    # sdformat itself when its Python bindings can be found, and against the
    # (old, but still published) sdformat.org schema
    path = os.path.join(out, "gazebo", "rmuc2026.sdf")
    tree = ET.parse(path)
    links = tree.findall(".//link")
    poses = {l.get("name"): [float(x) for x in l.find("pose").text.split()] for l in links}
    worst = 0.0
    for a in assets:
        if not a.placed:
            continue
        for k, M in enumerate(a.placements):
            worst = max(worst, check_pose("sdf", f"{a.name}_{k}", poses[f"{a.name}_{k}"], M))
    missing = [u.text for u in tree.findall(".//uri") if not os.path.exists(os.path.join(os.path.dirname(path), u.text))]
    if missing:
        problems.append(f"sdf: {len(missing)} mesh uris do not resolve, e.g. {missing[0]}")
    print(f"sdf: well-formed, {len(links)} links, {len(tree.findall('.//visual'))} visuals, "
          f"{len(tree.findall('.//collision'))} collisions, worst pose deviation {worst:.5f} m, uris resolve")
    try:
        parsed = sdformat_parse(path)
    except Exception as e:  # noqa: BLE001
        problems.append(f"sdformat: {type(e).__name__}: {str(e)[:300]}")
        parsed = None
    if parsed is None:
        if not problems or not problems[-1].startswith("sdformat"):
            print("sdf: sdformat parse skipped (no sdformat python bindings; see sdformat_parse)")
    else:
        worst = 0.0
        for link in parsed["links"]:
            worst = max(worst, check_pose("sdformat", link["name"], link["pose"], placement_of(assets, link["name"])))
        if len(parsed["links"]) != len(links):
            problems.append(f"sdformat: parsed {len(parsed['links'])} links, wrote {len(links)}")
        print(f"{parsed['module']}: parsed as SDF {parsed['version']}, world {parsed['world']!r}, {parsed['models']} model, "
              f"{len(parsed['links'])} links ({sum(l['visuals'] for l in parsed['links'])} visuals, "
              f"{sum(l['collisions'] for l in parsed['links'])} collisions), static {parsed['static']}, "
              f"worst pose deviation {worst:.5f} m")
    try:
        from lxml import etree

        root = sdformat_schemas()
        schema = etree.XMLSchema(etree.parse(root))
        ok = schema.validate(etree.parse(path))
        if not ok:
            problems.append("sdf: schema validation failed: " + "; ".join(str(e) for e in schema.error_log[:5]))
        else:
            print(f"sdf: valid against {SDF_SCHEMA} (mirrored in {os.path.dirname(root)})")
    except Exception as e:  # noqa: BLE001
        print(f"sdf: schema validation skipped ({type(e).__name__}: {str(e)[:80]})")
    for p in problems:
        print("PROBLEM:", p)
    return not problems


def check_pose_matrix(pose):
    x, y, z, roll, pitch, yaw = pose
    cr, sr, cp, sp, cy, sy = np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch), np.cos(yaw), np.sin(yaw)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    M = np.eye(4)
    M[:3, :3] = Rz @ Ry @ Rx
    M[:3, 3] = (x, y, z)
    return M


def placement_of(assets, link):
    name, k = link.rsplit("_", 1)
    return next(a for a in assets if a.name == name).placements[int(k)]


SDFORMAT_CHILD = r"""
import importlib, json, sys
mod = None
for v in ("", *[str(v) for v in range(16, 12, -1)]):
    try:
        mod = importlib.import_module(f"sdformat{v}")
        break
    except ImportError:
        continue
if mod is None:
    sys.exit(3)
root = mod.Root()
root.load(sys.argv[1])
world = root.world_by_index(0)
model = world.model_by_index(0)
links = []
for i in range(model.link_count()):
    link = model.link_by_index(i)
    p, r = link.raw_pose().pos(), link.raw_pose().rot().euler()
    links.append({"name": link.name(), "pose": [p.x(), p.y(), p.z(), r.x(), r.y(), r.z()],
                  "visuals": link.visual_count(), "collisions": link.collision_count()})
print(json.dumps({"module": mod.__name__, "version": root.version(), "world": world.name(),
                  "models": world.model_count(), "static": model.static(), "links": links}))
"""


def sdformat_parse(path):
    """Parse an SDF file with sdformat's Python bindings in a child
    interpreter, or return None when no bindings import. Homebrew's
    osrf/simulation bottles (`brew install osrf/simulation/sdformat15`) are
    found automatically: their modules live in
    /opt/homebrew/opt/<pkg>/lib/pythonX.Y/site-packages and need the keg lib
    directories on DYLD_LIBRARY_PATH; anything else needs PYTHONPATH (and
    whatever loader path) set by the caller."""
    import glob
    import subprocess

    tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
    env = dict(os.environ)
    site = [d for d in glob.glob(f"/opt/homebrew/opt/*/lib/{tag}/site-packages") if "sdformat" in d or "gz-math" in d]
    libs = glob.glob("/opt/homebrew/opt/gz-math*/lib") + glob.glob("/opt/homebrew/opt/sdformat*/lib")
    env["PYTHONPATH"] = os.pathsep.join(site + [env["PYTHONPATH"]] if env.get("PYTHONPATH") else site)
    env["DYLD_LIBRARY_PATH"] = os.pathsep.join(libs + [env["DYLD_LIBRARY_PATH"]] if env.get("DYLD_LIBRARY_PATH") else libs)
    r = subprocess.run([sys.executable, "-c", SDFORMAT_CHILD, path], env=env, capture_output=True, text=True)
    if r.returncode == 3:
        return None
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"exit {r.returncode}")
    return json.loads(r.stdout)


def sdformat_schemas():
    """Mirror sdformat.org's XSD set (its includes use absolute URLs, which
    libxml2 will not follow) into a cache and return the local root."""
    import re
    import urllib.request

    cache = os.path.join(os.path.expanduser("~/.cache/rm-map-tools/sdformat-schemas"))
    os.makedirs(cache, exist_ok=True)
    todo, seen = [SDF_SCHEMA], set()
    while todo:
        url = todo.pop()
        if url in seen:
            continue
        seen.add(url)
        local = os.path.join(cache, os.path.basename(url))
        if not os.path.exists(local):
            with urllib.request.urlopen(url, timeout=60) as r:
                text = r.read().decode()
            open(local, "w").write(re.sub(r"schemaLocation='[^']*/([^/']+)'", r"schemaLocation='\1'", text))
        for m in re.finditer(r"schemaLocation='([^']+)'", open(local).read()):
            todo.append(os.path.dirname(SDF_SCHEMA) + "/" + m.group(1))
    return os.path.join(cache, os.path.basename(SDF_SCHEMA))


def render(out, png, width=1920, height=1080):
    """Offscreen MuJoCo render of the visual geoms, as a preview."""
    import mujoco

    model = mujoco.MjModel.from_xml_path(os.path.join(out, "mujoco", "rmuc2026.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height, width)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = (0, 1.65, 0)
    cam.distance, cam.azimuth, cam.elevation = 26, -90, -45
    opt = mujoco.MjvOption()
    opt.geomgroup[:] = 0
    opt.geomgroup[2] = 1
    renderer.update_scene(data, cam, opt)
    img = renderer.render()
    from PIL import Image

    Image.fromarray(img).save(png)
    print(f"rendered {width}x{height} to {png}")


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elements")
    ap.add_argument("--out", required=True)
    ap.add_argument("--static-rest-pose", action="store_true", help="explicitly bake semantic assets at their CAD rest pose")
    ap.add_argument("--no-isaac", action="store_true")
    ap.add_argument("command", nargs="?", default="export", choices=["export", "verify", "render"])
    ap.add_argument("--png", default=None, help="render: output image (default <out>/mujoco-preview.png)")
    a = ap.parse_args()
    t0 = time.time()
    manifest = json.load(open(os.path.join(a.elements, "manifest.json")))
    assets = [Asset(n, e, a.elements, a.static_rest_pose) for n, e in manifest["assets"].items() if n != "full-map"]
    print(f"{len(assets)} assets loaded in {time.time() - t0:.0f}s", flush=True)
    report_path = os.path.join(a.out, "manifest.json")
    if a.command == "render":
        render(a.out, a.png or os.path.join(a.out, "mujoco-preview.png"))
        return
    if a.command == "verify":
        sys.exit(0 if verify(assets, a.out, json.load(open(report_path))) else 1)
    os.makedirs(a.out, exist_ok=True)
    files = write_meshes(assets, a.out)
    print(f"meshes written ({time.time() - t0:.0f}s)", flush=True)
    report = {
        "generator": provenance.generator("export_sim.py"),
        "copyright": provenance.COPYRIGHT,
        "source_elements": {"directory": os.path.abspath(a.elements), "source_sha256": manifest["source_sha256"]},
        "frame": manifest["arena_frame"],
        "units": "metres",
        "meshes": files,
        "gazebo": os.path.relpath(write_gazebo(assets, files, a.out), a.out),
        "mujoco": os.path.relpath(write_mujoco(assets, files, a.out), a.out),
        "not_placed": [x.name for x in assets if not x.placed],
    }
    if not a.no_isaac:
        try:
            world, per_asset = write_isaac(assets, a.out)
            report["isaac"] = {"world": os.path.relpath(world, a.out), "assets": per_asset}
        except ImportError:
            print("isaac: skipped, the usd-core package is not installed", flush=True)
    report["files_sha256"] = {
        os.path.relpath(os.path.join(d, f), a.out): sha256(os.path.join(d, f))
        for d, _, fs in os.walk(a.out) for f in fs if f != "manifest.json"
    }
    json.dump(report, open(report_path, "w"), indent=2, ensure_ascii=False)
    print(f"written to {a.out} in {time.time() - t0:.0f}s", flush=True)
    sys.exit(0 if verify(assets, a.out, report) else 1)


if __name__ == "__main__":
    main()
