#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Inspect source-owned collision domains without modifying native geometry."""
import argparse
import collections
import importlib.util
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_detail_passes import area
from cad_wall_fill import shape_map, volume
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from plan_cad_lods import digest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


native = module('composition', ROOT / 'benchmarks/2026-10-17-composed-pipeline/run.py').native
TARGETS = {'energy-unit/unit': [1], 'dart-station/frame': [1, 101], 'dart-station/deck-and-shared-hardware': [302, 39, 178, 122, 149], 'dart-station/door-candidate': [4, 26, 27]}


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); args.out.mkdir(parents=True, exist_ok=True); rows = []
    for cid, units in TARGETS.items():
        step = ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step'; doc, reader, faces, shells, owners = native(step); records = []
        for i in range(1, faces.Extent() + 1):
            if owners[i] not in units: continue
            face = TopoDS.Face(faces.FindKey(i)); s = BRepAdaptor_Surface(face); kind = str(s.GetType()).split('_')[-1]; box = Bnd_Box(); BRepBndLib.AddOptimal_s(face, box, False, False); bounds = [box.CornerMin().Coord(), box.CornerMax().Coord()]
            record = {'native_face_index': i, 'member': owners[i], 'kind': kind, 'area_mm2': area(face), 'bbox_mm': bounds}
            if kind == 'Plane':
                plane = s.Plane(); n = np.array(plane.Axis().Direction().Coord()) * (-1 if face.Orientation() == TopAbs_REVERSED else 1)
                record.update(normal=n.tolist(), offset_mm=float(np.array(plane.Location().Coord()) @ n))
            elif kind == 'Cylinder':
                c = s.Cylinder(); record.update(axis=c.Axis().Direction().Coord(), center_mm=c.Location().Coord(), radius_mm=c.Radius())
            records.append(record)
        rows.append({'id': cid, 'source_step_sha256': digest(step), 'members': units, 'faces': records})
        print(cid, 'planes', [(r['native_face_index'], r['member'], round(r['area_mm2']), np.round(r['normal'], 3).tolist()) for r in sorted([r for r in records if r['kind'] == 'Plane'], key=lambda r: -r['area_mm2'])[:8]], flush=True)
    (args.out / 'audit.json').write_text(json.dumps({'components': rows, 'producer_sha256': digest(__file__)}, indent=2) + '\n')


if __name__ == '__main__': main()
