"""Measure all presets on the same three source products; no field placements."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from validate_parts import read_part
from mesh_parts import tessellate_pair
from export_policy import ExportPolicy
from export_field_package import GlbWriter
from gltf_scene import read_glb


def measure(parts, output):
    output.mkdir(parents=True, exist_ok=False)
    products = {p['name']: p for p in json.loads((parts / 'parts.json').read_text())['parts']}
    rows = []
    for asset, name in [('resource-zone', '7000001_1_ASM'), ('dart-station', '0013_1_ASM'), ('base', '001_1_ASM')]:
        source = parts / products[name]['file']
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        doc, reader, error = read_part(str(source))
        if error:
            raise RuntimeError(error)
        for preset in ['legacy', 'simulation', 'preview', 'vision']:
            settings = ExportPolicy(preset).settings(asset, name)
            stats = {}
            start = time.perf_counter()
            pair = tessellate_pair(doc, settings, stats)
            row = dict(asset=asset, part=name, source_sha256=sha, preset=preset, settings=settings, recovery=stats)
            for kind, (positions, triangles, indices, colors) in zip(('visual', 'collision'), pair):
                writer = GlbWriter(name, {"version": "2.0", "generator": "preset-inventory"})
                writer.add_node(name, positions / 1000, triangles, [colors[int(i)] for i in indices])
                path = output / f'{asset}-{preset}-{kind}.glb'
                writer.write(path)
                gltf, _ = read_glb(path)
                primitives = [p for m in gltf['meshes'] for p in m['primitives']]
                row[kind] = dict(meshes=len(gltf['meshes']), primitives=len(primitives),
                                 vertices=sum(gltf['accessors'][p['attributes']['POSITION']]['count'] for p in primitives),
                                 triangles=sum(gltf['accessors'][p['indices']]['count'] // 3 for p in primitives),
                                 glb_bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            row['seconds'] = time.perf_counter() - start
            rows.append(row)
            (output / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
            print(f'{asset} {preset}: {row["visual"]["triangles"]:,} / {row["collision"]["triangles"]:,}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parts', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    measure(args.parts, args.output)
