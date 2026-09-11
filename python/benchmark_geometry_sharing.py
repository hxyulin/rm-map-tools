#!/usr/bin/env python3
"""Compare export writers on existing element triangles, without CAD tessellation.

The output is a static geometry benchmark, not an animation/texture package.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import types
import zipfile
from collections import Counter
import re
import numpy as np
from export_field_package import GlbWriter
from gltf_scene import read_glb_nodes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('package', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--baseline', required=True, help='Git revision before sharing changes')
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = subprocess.check_output(['git','show',f'{args.baseline}:python/export_field_package.py'])
    old = types.ModuleType('baseline_writer'); old.__file__ = str(Path(__file__).with_name('export_field_package.py'))
    exec(compile(source, old.__file__, 'exec'), old.__dict__)
    manifest = json.loads((args.package/'manifest.json').read_text())
    report = {'baseline_revision':args.baseline, 'package':str(args.package), 'assets':[], 'step':[]}
    for name, asset in manifest['assets'].items():
        if name == 'full-map': continue
        placements = asset.get('placements_in_source_arena_frame') or [{'matrix_local_to_arena':np.eye(4).tolist()}]
        for kind in ('visual','collision'):
            path = args.package/asset[kind]
            before = old.GlbWriter(name, {'version':'2.0'})
            after = GlbWriter(name, {'version':'2.0'})
            for node,p,t,k in read_glb_nodes(path):
                for i, placement in enumerate(placements):
                    m = np.array(placement['matrix_local_to_arena'])
                    before.add_node(f'{node}_{i}', p@m[:3,:3].T+m[:3,3],t,k)
                    after.add_node(f'{node}_{i}',p,t,k,matrix=m)
            bp=args.output/f'{name}-{kind}-baseline.glb'; cp=args.output/f'{name}-{kind}.glb'
            before.write(bp); after.write(cp)
            error=0.; nodes=0
            a=iter(read_glb_nodes(bp)); b=iter(read_glb_nodes(cp))
            from itertools import zip_longest
            for x,y in zip_longest(a,b):
                assert x is not None and y is not None and x[0]==y[0] and x[3]==y[3]
                assert x[2].shape == y[2].shape
                error=max(error,float(np.max(np.abs(x[1][x[2]]-y[1][y[2]]))))
                nodes+=1
            assert error < 1e-5, error
            row=dict(asset=name,kind=kind,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     placements=len(placements),before_bytes=bp.stat().st_size,after_bytes=cp.stat().st_size,
                     before_meshes=len(before.meshes),after_meshes=len(after.meshes),
                     scene_triangles=after.triangles,max_coordinate_delta_m=error,nodes_checked=nodes)
            report['assets'].append(row); print(json.dumps(row),flush=True)
            bp.unlink()
        step=args.package/f'{name}.step'
        if step.exists():
            counts=Counter()
            with step.open() as f:
                for line in f:
                    if 'NEXT_ASSEMBLY_USAGE_OCCURRENCE(' in line:
                        refs=re.findall(r'#(\d+)',line.split('=',1)[1]); counts[refs[-1]]+=1
            archive=args.output/f'{name}.step.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
                z.write(step,step.name)
            with zipfile.ZipFile(archive) as z:
                assert hashlib.sha256(z.read(step.name)).digest()==hashlib.sha256(step.read_bytes()).digest()
            report['step'].append(dict(asset=name,bytes=step.stat().st_size,zip_bytes=archive.stat().st_size,
                                       occurrences=sum(counts.values()),unique_referenced_products=len(counts)))
        (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__ == '__main__': main()
