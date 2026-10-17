#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Restore cleaned native terrain meshes, requiring their prior exact GLB hashes."""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('composition', Path(__file__).with_name('run.py'))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
from export_field_package import GlbWriter


def main():
    root = c.ROOT; folder = root / 'out/rmuc2027-terrain-cost-full'
    for record in c.read(folder / 'audit.json')['components']:
        cid = record['id']; target = folder / cid / 'visual.glb'
        if target.exists():
            if c.digest(target) != record['visual_sha256']: raise ValueError('existing terrain changed')
            continue
        source = root / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step'
        if c.digest(source) != record['component_step_sha256']: raise ValueError('terrain source changed')
        doc, reader, error = c.read_part(str(source))
        if error: raise ValueError(error)
        stats = {}; p, t, m, palette = c.tessellate(doc, .4, .25, stats)
        if len(t) != record['triangles'] or stats.get('unmeshed_faces'): raise ValueError('terrain tessellation changed')
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = GlbWriter(cid, {'version': '2.0', 'generator': 'terrain-cost/audit.py; upstream DJI/RoboMaster source geometry'})
        writer.add_node(cid, p / 1000, t, [palette[int(i)] for i in m]); writer.write(target)
        if c.digest(target) != record['visual_sha256']:
            target.unlink(); raise ValueError('rebuilt terrain differs from pinned mesh: ' + cid)
        print('restored', cid, len(t), flush=True)

if __name__ == '__main__': main()
