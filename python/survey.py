#!/usr/bin/env python3
"""Survey a STEP file from its index: what it contains and how it is coloured.

Prints the entity type histogram (geometry left out), the styled items by
target type and colour, the product count and assembly tree, and the
largest bodies with their product, body colour, face count, face colour
histogram and vertex box. This is the pure-Python counterpart of
`rm-map-tools inspect`, kept for the colour and extent views the CLI does
not print.

Usage:
  survey.py <index.npz> [--depth 2] [--largest 40] [--bodies bodies.json]

Build the index first with `python3 p21index.py <file.stp> <index.npz>`.
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p21index import Index  # noqa: E402
from p21model import Model  # noqa: E402

GEOMETRY = {
    "CARTESIAN_POINT", "DIRECTION", "VECTOR", "LINE", "CIRCLE", "ELLIPSE", "PLANE", "AXIS2_PLACEMENT_3D",
    "CYLINDRICAL_SURFACE", "CONICAL_SURFACE", "SPHERICAL_SURFACE", "TOROIDAL_SURFACE",
    "B_SPLINE_CURVE_WITH_KNOTS", "B_SPLINE_SURFACE_WITH_KNOTS", "SURFACE_CURVE", "PCURVE", "SEAM_CURVE",
    "DEFINITIONAL_REPRESENTATION", "TRIMMED_CURVE", "BOUNDED_CURVE", "VERTEX_POINT", "EDGE_CURVE",
    "ORIENTED_EDGE", "EDGE_LOOP", "VERTEX_LOOP", "FACE_BOUND", "FACE_OUTER_BOUND", "ADVANCED_FACE",
}


def type_histogram(ix):
    counts = np.bincount(ix.types, minlength=len(ix.typenames))
    return sorted(((ix.typenames[t], int(n)) for t, n in enumerate(counts) if n and ix.typenames[t] not in GEOMETRY),
                  key=lambda kv: -kv[1])


def styled_histogram(ix, m):
    hist = collections.Counter()
    for row, (tgt, surf, curve, over) in m.styled.items():
        hist[("OVER_RIDING_STYLED_ITEM" if over else "STYLED_ITEM", ix.tname(tgt) if tgt >= 0 else "?", surf)] += 1
    return hist.most_common()


def print_tree(m, p, depth, level=0):
    counts = collections.Counter(c for _, c in m.children.get(p, []))
    for c, n in counts.items():
        kids = len(m.children.get(c, []))
        print("  " * (level + 1) + f"{m.pname(c)} x{n}" + (f" ({kids} children)" if kids else ""))
        if level + 1 < depth:
            print_tree(m, c, depth, level + 1)


def body_rows(ix, m):
    rows = []
    for b, rep in m.bodies:
        faces = m.body_faces(b)
        mn, mx, nv = m.body_bbox(b)
        rows.append({
            "id": int(ix.ids[b]),
            "type": ix.tname(b),
            "product": m.pname(m.body_product(b)),
            "body_colour": m.surface_colour(b),
            "faces": len(faces),
            "face_colours": {str(k): v for k, v in m.face_colour_hist(b, faces).items()},
            "bbox_min": None if mn is None else [round(float(x), 1) for x in mn],
            "bbox_max": None if mx is None else [round(float(x), 1) for x in mx],
            "vertices": nv,
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("index")
    ap.add_argument("--depth", type=int, default=2, help="assembly tree depth to print")
    ap.add_argument("--largest", type=int, default=40, help="how many bodies to list, by largest extent")
    ap.add_argument("--bodies", default=None, help="write every body's row as JSON to this file")
    a = ap.parse_args()
    ix = Index(a.index)
    m = Model(ix)
    print(f"{ix.source}: {ix.n} entities, {ix.size / 1e6:.0f} MB")
    print("\nentity types (geometry left out):")
    for name, n in type_histogram(ix):
        print(f"  {n:>9}  {name}")
    print("\nstyled items by kind, target type and surface colour:")
    for (kind, tt, colour), n in styled_histogram(ix, m):
        print(f"  {n:>7}  {kind:<24} {tt:<32} {colour}")
    print(f"\nproducts: {len(m.product_name)}, with shapes: {len(m.product_reps)}, roots: {[m.pname(r) for r in m.roots]}")
    for r in m.roots:
        print(m.pname(r))
        print_tree(m, r, a.depth)
    rows = body_rows(ix, m)
    print(f"\nbodies: {len(rows)} " + ", ".join(f"{t} {n}" for t, n in collections.Counter(r['type'] for r in rows).most_common()))
    if a.bodies:
        json.dump(rows, open(a.bodies, "w"), indent=0, ensure_ascii=False)
        print(f"wrote {a.bodies}")

    def extent(r):
        return 0.0 if r["bbox_min"] is None else max(hi - lo for lo, hi in zip(r["bbox_min"], r["bbox_max"]))

    print(f"\nlargest {a.largest} bodies (extent in mm):")
    for r in sorted(rows, key=lambda r: -extent(r))[: a.largest]:
        ext = [round(hi - lo) for lo, hi in zip(r["bbox_min"], r["bbox_max"])] if r["bbox_min"] else None
        print(f"  {r['type'][:18]:<18} {r['product']:<28} body {r['body_colour']} faces {r['faces']:>6} ext {ext} "
              f"z {r['bbox_min'][2] if r['bbox_min'] else None}..{r['bbox_max'][2] if r['bbox_max'] else None} {r['face_colours']}")


if __name__ == "__main__":
    main()
