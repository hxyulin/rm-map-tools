# SPDX-License-Identifier: LicenseRef-Proprietary
"""Remove reviewed V1 wordmarks superseded by the grafted V2 bumpy roads.

Figure 4-36 of RMUC 2026 V2.1.0 shows wordmarks on the opposite road segments.
This composition choice removes both complete duplicate words, including letters
outside the bumps. It does not move terrain or infer removable parts by colour.
The source package is retained; output must be a new directory.
"""

import argparse
import copy
import json
import shutil
from pathlib import Path

import numpy as np
from deploy_field import asset_path, digest, read_manifest
from gltf_scene import mesh_instances, read_glb, write_glb

# Exact V1.2.0 source occurrences reviewed in the markings contact sheets.
WORDMARKS = (
    tuple(f"source_{13267048 + i}_BREP_{161 + i}_1" for i in range(15)),
    tuple(f"source_{13267137 + i}_BREP_{188 + i}_1" for i in range(15)),
)
ROADS = ("graft_141103_BREP_220", "graft_128896_BREP_192")


def remove_obsolete_wordmarks(document, binary):
    doc = copy.deepcopy(document)
    groups = {}
    for i, _, points, triangles, _ in mesh_instances(doc, binary):
        name = doc["nodes"][i].get("name")
        groups.setdefault(name, []).append((i, points, len(triangles)))
    removed = []
    for names, road in zip(WORDMARKS, ROADS):
        if road not in groups:
            raise ValueError(f"missing grafted road: {road}")
        road_points = np.vstack([p for _, p, _ in groups[road]])
        word_points = []
        for name in names:
            parts = groups.get(name, [])
            if not parts or len({i for i, _, _ in parts}) != 1:
                raise ValueError(f"missing or ambiguous marking: {name}")
            points = np.vstack([p for _, p, _ in parts])
            if np.ptp(points[:, 2]) > 0.003:
                raise ValueError(f"marking is no longer a flat sheet: {name}")
            word_points.append(points)
            removed.append({"node": name, "triangles": sum(n for _, _, n in parts)})
            # Keep stable node indices and source geometry for provenance, but
            # detach the mesh from both visible and collision scene traversal.
            doc["nodes"][parts[0][0]].pop("mesh")
        word_points = np.vstack(word_points)
        if not np.all(
            np.minimum(word_points.max(0)[:2], road_points.max(0)[:2])
            > np.maximum(word_points.min(0)[:2], road_points.min(0)[:2])
        ):
            raise ValueError("reviewed wordmark no longer overlaps the road")
    return doc, removed


def compose(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError("output must be a new directory outside the source package")
    manifest = read_manifest(source)
    if "road_marking_composition" in manifest:
        raise ValueError("package already composed")
    entry = manifest["assets"]["arena-static"]
    prepared = []
    for kind in ("visual", "collision"):
        path = asset_path(source, entry[kind])
        if digest(path) != entry[kind + "_sha256"]:
            raise ValueError(f"checksum mismatch: {path}")
        doc, binary = read_glb(path)
        doc, removed = remove_obsolete_wordmarks(doc, binary)
        prepared.append((kind, doc, binary, removed))
    shutil.copytree(source, output)
    report = {
        "reference": "RMUC 2026 V2.1.0 Figure 4-36",
        "decision": "Omit two obsolete duplicate wordmarks; retain graft placement and other lettering.",
        "source_manifest_sha256": digest(source / "manifest.json"),
        "assets": {},
    }
    for kind, doc, binary, removed in prepared:
        old_hash = entry[kind + "_sha256"]
        path = asset_path(output, entry[kind])
        write_glb(path, doc, binary)
        entry[kind + "_sha256"] = digest(path)
        entry[kind + "_bytes"] = path.stat().st_size
        count = sum(len(t) for _, _, _, t, _ in mesh_instances(doc, binary))
        entry["triangles" if kind == "visual" else "collision_triangles"] = count
        report["assets"][kind] = {
            "before_sha256": old_hash,
            "after_sha256": digest(path),
            "removed": removed,
            "triangles": count,
        }
    manifest["road_marking_composition"] = report
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "road-marking-composition.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compose(args.source, args.output)
