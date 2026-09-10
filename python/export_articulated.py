#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Export semantic equipment to SDF, URDF and USD as kinematic models.

Example: python/export_articulated.py ../assets/rm2026-reference --out out/joints
The output contains individual equipment models, not a second full field.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
from articulated_scene import load_asset, semantic_assets
from export_sim import rpy_of, write_stl


def numbers(values):
    return ' '.join(format(float(x), '.12g') for x in values)


def name_map(graph):
    # Prefixes and indices prevent collisions after sanitizing semantic names.
    return {name: f'link_{i}_' + re.sub(r'[^A-Za-z0-9_]', '_', name) for i, name in enumerate(graph)}


def joint_type(link):
    joint = link['joint']
    if joint.get('geometry_binding') == 'frames_only':
        return 'fixed'
    if joint['type'] != 'continuous' and 'limits' not in joint:
        raise ValueError(f"{joint['id']}: bounded joint has no limits")
    return joint['type']


def xml_write(root, path):
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def meshes(asset, directory):
    (directory / 'meshes').mkdir()
    records = []
    for kind, geometry in asset['geometry'].items():
        for i, g in enumerate(geometry):
            relative = f'meshes/{kind}_{i}.stl'
            write_stl(directory / relative, g['points'], g['triangles'])
            records.append({'kind': kind, 'file': relative, **{k: v for k, v in g.items()
                            if k not in ('points', 'triangles')}, 'triangles': len(g['triangles'])})
    return records


def write_urdf(asset, records, directory):
    graph, names = asset['graph'], name_map(asset['graph'])
    robot = ET.Element('robot', name=asset['name'])
    for key, link in graph.items():
        node = ET.SubElement(robot, 'link', name=names[key])
        for i, rec in enumerate(records):
            if rec['link'] != key:
                continue
            elem = ET.SubElement(node, rec['kind'], name=f"{rec['kind']}_{i}")
            ET.SubElement(ET.SubElement(elem, 'geometry'), 'mesh', filename=f"package://rm_map_equipment/{asset['name']}/{rec['file']}")
            if rec['kind'] == 'visual':
                mat = ET.SubElement(elem, 'material', name=f'material_{i}')
                ET.SubElement(mat, 'color', rgba=numbers(rec['color']))
        if key == 'root':
            continue
        kind = joint_type(link)
        joint = ET.SubElement(robot, 'joint', name=names[key] + '_joint', type=kind)
        ET.SubElement(joint, 'parent', link=names[link['parent']])
        ET.SubElement(joint, 'child', link=names[key])
        m = np.asarray(link['parent_to_joint'])
        ET.SubElement(joint, 'origin', xyz=numbers(m[:3, 3]), rpy=numbers(rpy_of(m[:3, :3])))
        if kind != 'fixed':
            ET.SubElement(joint, 'axis', xyz=numbers(link['joint']['axis']))
            # URDF requires effort and velocity. Zero disables actuation; these
            # are compatibility sentinels, not measured equipment properties.
            limit = {'effort': '0', 'velocity': '0'}
            if 'limits' in link['joint']:
                limit.update(lower=str(link['joint']['limits'][0]), upper=str(link['joint']['limits'][1]))
            ET.SubElement(joint, 'limit', **limit)
    xml_write(robot, directory / 'model.urdf')


def write_sdf(asset, records, directory):
    graph, names = asset['graph'], name_map(asset['graph'])
    root = ET.Element('sdf', version='1.11')
    model = ET.SubElement(root, 'model', name=asset['name'])
    ET.SubElement(model, 'static').text = 'false'
    for key, link in graph.items():
        node = ET.SubElement(model, 'link', name=names[key])
        m = np.asarray(link['rest'])
        ET.SubElement(node, 'pose', relative_to='__model__').text = numbers([*m[:3, 3], *rpy_of(m[:3, :3])])
        ET.SubElement(node, 'kinematic').text = 'true'
        ET.SubElement(node, 'gravity').text = 'false'
        for i, rec in enumerate(records):
            if rec['link'] != key:
                continue
            elem = ET.SubElement(node, rec['kind'], name=f"{rec['kind']}_{i}")
            mesh = ET.SubElement(ET.SubElement(elem, 'geometry'), 'mesh')
            ET.SubElement(mesh, 'uri').text = rec['file']
            if rec['kind'] == 'visual':
                mat = ET.SubElement(elem, 'material')
                for tag in ('ambient', 'diffuse'):
                    ET.SubElement(mat, tag).text = numbers(rec['color'])
        if key == 'root':
            continue
        kind = joint_type(link)
        joint = ET.SubElement(model, 'joint', name=names[key] + '_joint',
                              type='revolute' if kind == 'continuous' else kind)
        ET.SubElement(joint, 'parent').text = names[link['parent']]
        ET.SubElement(joint, 'child').text = names[key]
        ET.SubElement(joint, 'pose', relative_to=names[key]).text = '0 0 0 0 0 0'
        if kind != 'fixed':
            axis = ET.SubElement(joint, 'axis')
            ET.SubElement(axis, 'xyz').text = numbers(link['joint']['axis'])
            if 'limits' in link['joint']:
                limit = ET.SubElement(axis, 'limit')
                for tag, value in zip(('lower', 'upper'), link['joint']['limits']):
                    ET.SubElement(limit, tag).text = str(value)
    xml_write(root, directory / 'model.sdf')
    config = ET.Element('model')
    ET.SubElement(config, 'name').text = asset['name']
    ET.SubElement(config, 'version').text = '1.0'
    ET.SubElement(config, 'sdf', version='1.11').text = 'model.sdf'
    ET.SubElement(config, 'description').text = 'Prescribed kinematics; see semantics.json for provenance and limitations.'
    xml_write(config, directory / 'model.config')


def write_usd(asset, directory):
    from pxr import Gf, Usd, UsdGeom, UsdPhysics, Vt
    graph, names = asset['graph'], name_map(asset['graph'])
    stage = Usd.Stage.CreateNew(str(directory / 'model.usdc'))
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    # Assets retain their GLB frame. The sidecar provides arena placements.
    # All assets use the same stage convention; no implicit axis conversion.
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdGeom.Xform.Define(stage, '/Model')
    stage.SetDefaultPrim(root.GetPrim())
    root.GetPrim().SetCustomDataByKey('rm:semanticsFile', 'semantics.json')
    for key, link in graph.items():
        path = '/Model/' + names[key]
        body = UsdGeom.Xform.Define(stage, path)
        body.AddTransformOp().Set(Gf.Matrix4d(np.asarray(link['rest']).T.tolist()))
        api = UsdPhysics.RigidBodyAPI.Apply(body.GetPrim())
        api.CreateKinematicEnabledAttr(True)
        body.GetPrim().SetCustomDataByKey('rm:linkId', key)
        for kind, geometry in asset['geometry'].items():
            for i, geom in enumerate(geometry):
                if geom['link'] != key:
                    continue
                mesh = UsdGeom.Mesh.Define(stage, f'{path}/{kind}_{i}')
                mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(geom['points'].astype(np.float32)))
                mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(geom['triangles']), 3, np.int32)))
                mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(geom['triangles'].astype(np.int32).ravel()))
                mesh.CreateSubdivisionSchemeAttr('none')
                mesh.CreateDoubleSidedAttr(True)
                mesh.GetPrim().SetCustomDataByKey('rm:metadataJson', json.dumps(geom['metadata'], ensure_ascii=False))
                if kind == 'visual':
                    mesh.CreateDisplayColorAttr([Gf.Vec3f(*geom['color'][:3])])
                    mesh.CreateDisplayOpacityAttr([geom['color'][3]])
                else:
                    mesh.CreatePurposeAttr('guide')
                    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
                    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr('none')
        if key == 'root':
            continue
        kind = joint_type(link)
        schema = {'fixed': UsdPhysics.FixedJoint, 'continuous': UsdPhysics.RevoluteJoint,
                  'revolute': UsdPhysics.RevoluteJoint, 'prismatic': UsdPhysics.PrismaticJoint}[kind]
        joint = schema.Define(stage, '/Model/joint_' + names[key])
        joint.CreateBody0Rel().SetTargets(['/Model/' + names[link['parent']]])
        joint.CreateBody1Rel().SetTargets([path])
        # USD primary axes are cardinal. Rotate both local joint frames so X
        # is the semantic axis, including arbitrary tilted slider directions.
        axis = np.asarray(link['joint']['axis'], float)
        helper = np.eye(3)[np.argmin(np.abs(axis))]
        y = np.cross(helper, axis); y /= np.linalg.norm(y)
        align = np.column_stack((axis, y, np.cross(axis, y)))
        parent_frame = np.asarray(link['parent_to_joint'])
        def quat(matrix):
            x, y, z, w = Rotation.from_matrix(matrix).as_quat()
            return Gf.Quatf(float(w), Gf.Vec3f(float(x), float(y), float(z)))
        joint.CreateLocalPos0Attr(Gf.Vec3f(*parent_frame[:3, 3]))
        joint.CreateLocalRot0Attr(quat(parent_frame[:3, :3] @ align))
        joint.CreateLocalPos1Attr(Gf.Vec3f(0))
        joint.CreateLocalRot1Attr(quat(align))
        joint.GetPrim().SetCustomDataByKey('rm:jointJson', json.dumps(link['joint'], ensure_ascii=False))
        if kind != 'fixed':
            joint.CreateAxisAttr('X')
            if 'limits' in link['joint']:
                factor = 1 if kind == 'prismatic' else 180 / np.pi
                joint.CreateLowerLimitAttr(float(link['joint']['limits'][0] * factor))
                joint.CreateUpperLimitAttr(float(link['joint']['limits'][1] * factor))
    stage.GetRootLayer().Save()


def export(root, out, selected=None, formats=('sdf', 'urdf', 'usd')):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError(f'output already exists: {out}')
    entries = list(semantic_assets(root))
    names = [name for _, name, _ in entries]
    if len(set(names)) != len(names):
        raise ValueError('duplicate asset names across packages')
    if selected and set(selected) - set(names):
        raise ValueError('unknown selected asset')
    entries = [(p, n, e) for p, n, e in entries if not selected or n in selected]
    if not entries:
        raise ValueError('no semantic assets found')
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.articulated-', dir=out.parent))
    try:
        report = {'schema_version': 1, 'generator': 'export_articulated.py', 'formats': list(formats),
                  'scope': 'individual semantic equipment; static field geometry is not duplicated', 'assets': {}}
        for source, name, entry in entries:
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                raise ValueError('unsafe asset name')
            print(f'exporting {name}', flush=True)
            asset = load_asset(source, name, entry)
            directory = staging / name
            directory.mkdir()
            records = meshes(asset, directory) if set(formats) & {'urdf', 'sdf'} else []
            for fmt in formats:
                if fmt == 'usd':
                    write_usd(asset, directory)
                else:
                    {'sdf': write_sdf, 'urdf': write_urdf}[fmt](asset, records, directory)
            metadata = {k: asset[k] for k in ('graph', 'semantics', 'placements', 'source_directory')}
            metadata.update(schema_version=1, units={'length': 'metres', 'angle': 'radians'},
                            frame='source GLB asset frame, before arena placement',
                            names=name_map(asset['graph']), meshes=records,
                            policy={'motion': 'prescribed, no controller exported',
                                    'inertials': 'unknown; not authored',
                                    'urdf_effort_velocity': 'zero compatibility sentinels; not physical limits',
                                    'frames_only': 'fixed frames; source joint definitions retained',
                                    'materials': 'base color only; textures and PBR parameters are not converted'})
            (directory / 'semantics.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
            report['assets'][name] = {'directory': name, 'joints': len(asset['graph']) - 1,
                'movable_joints': sum(joint_type(v) != 'fixed' for k, v in asset['graph'].items() if k != 'root')}
        if 'urdf' in formats:
            package = ET.Element('package', format='3')
            for tag, value in [('name', 'rm_map_equipment'), ('version', '0.1.0'),
                               ('description', 'Generated RoboMaster equipment kinematics'),
                               ('license', 'LicenseRef-Source-Assets')]:
                ET.SubElement(package, tag).text = value
            ET.SubElement(package, 'maintainer', email='noreply@example.com').text = 'Generated asset package'
            ET.SubElement(package, 'buildtool_depend').text = 'ament_cmake'
            ET.SubElement(ET.SubElement(package, 'export'), 'build_type').text = 'ament_cmake'
            xml_write(package, staging / 'package.xml')
            (staging / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.8)\nproject(rm_map_equipment)\n'
                'find_package(ament_cmake REQUIRED)\ninstall(DIRECTORY '
                + ' '.join(report['assets']) + ' DESTINATION share/${PROJECT_NAME})\nament_package()\n')
        report['files_sha256'] = {str(p.relative_to(staging)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(staging.rglob('*')) if p.is_file()}
        (staging / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        staging.rename(out)
        return report
    except BaseException:
        shutil.rmtree(staging)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elements')
    parser.add_argument('--out', required=True)
    parser.add_argument('--asset', action='append', help='select an asset; repeat for several')
    parser.add_argument('--formats', nargs='+', choices=['sdf', 'urdf', 'usd'], default=['sdf', 'urdf', 'usd'])
    args = parser.parse_args()
    export(args.elements, args.out, args.asset, args.formats)


if __name__ == '__main__':
    main()
