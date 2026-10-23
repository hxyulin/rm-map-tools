# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read sibling simulator GLBs; write an optical-binding inventory beside this file."""
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SIM = ROOT.parent / "rm-simulator"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def glb(path):
    data = path.read_bytes()
    assert data[:4] == b"glTF"
    length, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A
    return json.loads(data[20:20 + length])


def descendants(g, i):
    for child in g["nodes"][i].get("children", []):
        yield child
        yield from descendants(g, child)


def srgb(v):
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def inspect(path, bindings):
    g = glb(path)
    mats = g.get("materials", [])
    records = []
    head = next((i for i, n in enumerate(g["nodes"])
                 if n.get("name") == "technology-core/tool-head"), None)
    head_nodes = {head, *descendants(g, head)} if head is not None else set()
    for i, node in enumerate(g["nodes"]):
        if "mesh" not in node:
            continue
        for pi, prim in enumerate(g["meshes"][node["mesh"]]["primitives"]):
            assert prim.get("mode", 4) == 4
            mi = prim.get("material")
            mat = mats[mi] if mi is not None else {}
            factor = mat.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1] * 4)
            acc = g["accessors"][prim["attributes"]["POSITION"]]
            count = g["accessors"][prim["indices"]]["count"] if "indices" in prim else acc["count"]
            records.append({"node": i, "name": node.get("name"), "primitive": pi,
                            "material": mi, "triangles": count // 3,
                            "srgb_from_linear_factor": [srgb(x) for x in factor[:3]],
                            "attributes": sorted(prim["attributes"]),
                            "position_accessor_min": acc.get("min"),
                            "position_accessor_max": acc.get("max"),
                            "node_extras": node.get("extras"), "in_tool_head": i in head_nodes})
    matches = []
    for name, expected in bindings:
        nodes = [i for i, n in enumerate(g["nodes"]) if n.get("name") == name]
        # Bevy loads a glTF node's own mesh primitives as child entities too.
        eligible = {c for i in nodes for c in [i, *descendants(g, i)]}
        found = [r for r in records if r["node"] in eligible
                 and all(abs(a - b) <= .01 for a, b in zip(r["srgb_from_linear_factor"], expected))]
        matches.append({"exact_node_name": name, "source_srgb": expected,
                        "node_occurrences": nodes, "matched_primitives": len(found),
                        "triangles": sum(r["triangles"] for r in found),
                        "materials": sorted({r["material"] for r in found}),
                        "mesh_nodes": sorted({r["node"] for r in found})})
    return {"path": str(path.relative_to(ROOT.parent)), "sha256": sha(path),
            "materials": mats, "mesh_nodes": len({r["node"] for r in records}),
            "primitives": len(records), "triangles": sum(r["triangles"] for r in records),
            "authored_nonzero_emission_materials": [i for i, m in enumerate(mats)
                if any(m.get("emissiveFactor", [0, 0, 0]))],
            "textures": len(g.get("textures", [])), "binding_matches": matches,
            "tool_head_white_primitives": [r for r in records if r["in_tool_head"]
                and all(abs(v - 1) < .01 for v in r["srgb_from_linear_factor"])],
            "tool_head_triangles": sum(r["triangles"] for r in records if r["in_tool_head"])}


def main():
    package = SIM / "field-2027"
    binding = json.loads((package / "rmuc2027-bindings.json").read_text())
    definitions = [
        (package / "equipment/tech-core.glb", []),
        (package / "equipment/base.glb", [(f"source_body_{b}", [1, 0, 0])
            for b in binding["report"]["base"]["detector_bodies"]]),
        (package / "outpost.glb", [(f"source_body_{b}", [0, 1, 1])
            for b in binding["report"]["outpost"]["detector_bodies"]]),
        (package / "rune.glb", [(name, [1, 0, 0] if bank == 0 else [0, 0, 1])
            for bank, arms in enumerate(binding["rune_arms"]) for name in arms]),
        (ROOT / "out/rmuc2027-protected-source-reference/technology-core/tool-head/reference.glb", []),
    ]
    paths = [package / "manifest.json", package / "equipment/manifest.json",
             package / "rmuc2027-bindings.json"]
    paths += [SIM / f"crates/rm-simulator-render/src/{name}.rs"
              for name in ["cad", "targets", "armor", "rune", "quality", "lighting", "lib", "graphics_settings"]]
    paths += [SIM / "crates/rm-simulator-app/src/scene.rs",
              SIM / "crates/rm-simulator-server/src/layout.rs",
              SIM / "crates/rm-simulator-bench/src/assets.rs",
              SIM / "crates/rm-simulator-world/src/config.rs",
              SIM / "crates/rm-simulator-world/src/snapshot.rs",
              SIM / "crates/rm-simulator-assets/src/rmuc_2027.rs",
              SIM / "crates/rm-simulator-assets/src/cad_assets.rs"]
    result = {"notes": "Counts per asset, before placements; node bounds are mesh-local accessor bounds. No runtime capture.",
              "source_sha256": {str(p.relative_to(ROOT.parent)): sha(p) for p in paths},
              "assets": [inspect(p, b) for p, b in definitions]}
    assert all(b["matched_primitives"] > 0 for a in result["assets"]
               for b in a["binding_matches"]), "A requested source optical binding has no match"
    (HERE / "inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    for a in result["assets"]:
        print(a["path"], "triangles", a["triangles"], "materials", len(a["materials"]),
              "textures", a["textures"], "emissive", a["authored_nonzero_emission_materials"],
              "bindings", [b["matched_primitives"] for b in a["binding_matches"]],
              "head-white", len(a["tool_head_white_primitives"]))


if __name__ == "__main__":
    main()
