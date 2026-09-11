#!/usr/bin/env python3
"""Build the documentation's movable-entity catalog from pinned reference CAD."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, write_glb
from articulated_scene import checked_file, topology
from preview.tech_core_demo import prepare_demo, PREVIEW_JOINT_RANGE

NAMES = {
    'base': ('Base', ['Shield 1', 'Shield 2', 'Shield 3', 'Dart target']),
    'rune': ('Power Rune', ['Front rotor', 'Rear rotor']),
    'outpost': ('Outpost', ['Rotor']),
    'dart-station': ('Dart station', ['Sliding window']),
    'tech-core': ('Technology Core', ['Base yaw', 'Shoulder', 'Elbow', 'Wrist 1', 'Wrist 2', 'Tool roll']),
}

def build(source, destination):
    if destination.exists():
        raise ValueError(f'Output already exists: {destination}. Choose a new output or remove the generated catalog first.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.models-') as temp:
        staging = Path(temp)
        catalog = {'schema_version': 1, 'copyright': 'CAD geometry: DJI / RoboMaster. See repository NOTICE.md.', 'models': []}
        for name, (label, labels) in NAMES.items():
            package = source / 'equipment' if name in ('base', 'tech-core') else source
            manifest = json.loads((package / 'manifest.json').read_text())
            asset = manifest['assets'][name]
            sidecar = json.loads(checked_file(package, asset['semantics']['file']).read_text())
            binding = sidecar['assets'][name]['files']['visual']
            source_file = checked_file(package, binding['file'], binding['sha256'])
            doc, binary = read_glb(source_file)
            topology(doc, binding)
            note = ''
            if name == 'tech-core':
                doc, binary, *_ = prepare_demo(doc, binary, binding)
                note = 'CAD display rig with six movable axes and schematic bearings. Display ranges are ±1.2 rad, about ±68.8°, and are not physical limits. The reference export keeps these axes as fixed frames.'
            target = staging / (name + '.glb')
            write_glb(target, doc, binary)
            data = target.read_bytes()
            compressed = gzip.compress(data, compresslevel=9, mtime=0)
            (staging / (name + '.glb.gz')).write_bytes(compressed)
            target.unlink()
            joints = []
            for joint, joint_label in zip(binding['joints'], labels, strict=True):
                limits = joint.get('limits', joint.get('preview_range', [-3.141592653589793, 3.141592653589793]))
                if name == 'tech-core':
                    limits = list(PREVIEW_JOINT_RANGE)
                control = {'id': joint['id'], 'label': joint_label, 'type': joint['type'], 'motion_node': joint['motion_node'], 'axis': joint['axis'], 'limits': limits}
                if name == 'tech-core':
                    control['limits_kind'] = 'preview'
                joints.append(control)
            catalog['models'].append({'id': name, 'label': label, 'file': name + '.glb.gz', 'sha256': hashlib.sha256(data).hexdigest(), 'source_sha256': binding['sha256'], 'bytes': len(compressed), 'up': [0, 0, 1] if name in ('base', 'tech-core', 'dart-station') else [0, 1, 0], 'joints': joints, 'note': note})
            print(f'{label}: {len(joints)} joints, {len(compressed)/1e6:.1f} MB', flush=True)
        (staging / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
        staging.rename(destination)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT.parent / 'assets/rm2026-reference')
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/public/models')
    args = parser.parse_args()
    build(args.source.resolve(), args.out.resolve())
