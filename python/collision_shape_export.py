# SPDX-License-Identifier: MIT OR Apache-2.0
"""Experimental cylinder + retained-mesh sidecars; never install runtime assets.

JSON is an rm-map-tools prototype contract, not an existing rm-simulator schema.
The SDF adapter exports one unplaced static model for interoperability inspection.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
from gltf_scene import accessor, read_glb, scene_nodes, write_glb
from simplify_package import compact, scene_triangles
from export_sim import write_stl

SCHEMA = 'rm-map-tools.collision-shapes.prototype-1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def z_rotation(axis):
    """Quaternion xyzw rotating canonical cylinder +Z onto its unit axis."""
    axis = np.asarray(axis, dtype=float)
    if axis.shape != (3,) or not np.isfinite(axis).all() or not np.isclose(np.linalg.norm(axis), 1, atol=1e-8, rtol=0):
        raise ValueError('cylinder axis must be a finite unit vector')
    sine = np.linalg.norm(axis[:2])
    if sine < 1e-14:
        return np.array([1.,0,0,0]) if axis[2] < 0 else np.array([0.,0,0,1.])
    perpendicular = np.array([-axis[1], axis[0], 0.]) / sine
    return Rotation.from_rotvec(perpendicular * np.arctan2(sine, axis[2])).as_quat()


def cylinder_in_scene(parameters, world):
    """Transform a solid mesh-local cylinder through a rigid/uniform mount."""
    if parameters.get('solid') is not True:
        raise ValueError('native cylinders are solid; hollow profiles must retain mesh geometry')
    c = np.asarray(parameters['center_m'], dtype=float)
    axis = np.asarray(parameters['axis_unit_vector'], dtype=float)
    z_rotation(axis)
    radius, length = float(parameters['radius_m']), float(parameters['length_m'])
    if c.shape != (3,) or not np.isfinite(c).all() or not np.isfinite([radius, length]).all() or min(radius, length) <= 0:
        raise ValueError('invalid cylinder dimensions/center')
    linear = np.asarray(world, dtype=float)[:3, :3]
    scale = float(np.linalg.norm(linear, axis=0).mean())
    if scale <= 0 or np.linalg.det(linear) <= 0 or not np.allclose(linear.T @ linear / scale**2, np.eye(3), rtol=1e-7, atol=1e-8):
        raise ValueError('cylinder requires proper rigid or uniform scale; nonuniform/sheared/reflected mounts are unsupported')
    direction = linear @ axis / scale
    center = linear @ c + world[:3, 3]
    return {'kind': 'cylinder', 'radius_m': radius * scale, 'length_m': length * scale,
            'pose': {'translation_m': center.tolist(), 'rotation_xyzw': z_rotation(direction).tolist()},
            'axis_unit_vector': direction.tolist(), 'solid': True}


def geometry(doc, binary):
    parts = []
    for ni, world, _ in scene_nodes(doc):
        node = doc['nodes'][ni]
        if 'mesh' not in node:
            continue
        for pr in doc['meshes'][node['mesh']]['primitives']:
            p = accessor(doc, binary, pr['attributes']['POSITION']).astype(float)
            t = accessor(doc, binary, pr['indices']).reshape(-1, 3)
            if np.linalg.det(world[:3, :3]) < 0:
                t = t[:, ::-1]
            parts.append((p @ world[:3, :3].T + world[:3, 3])[t])
    return np.concatenate(parts) if parts else np.empty((0, 3, 3))


def export(source, selection, out):
    """Replace exact selected mesh nodes; keep every other source node unchanged."""
    source, out = Path(source).resolve(), Path(out).resolve()
    if source in [out / name for name in ['remainder.glb', 'remainder.stl', 'collision-shapes.json', 'model.sdf']]:
        raise ValueError('output would overwrite source')
    if digest(source) != selection['source_sha256']:
        raise ValueError('source GLB hash does not match reviewed selection')
    doc, binary = read_glb(source)
    live = {ni: (world, parent) for ni, world, parent in scene_nodes(doc)}
    selected, native = set(), []
    for row in selection['replacements']:
        ni = row['node_index']
        if isinstance(ni, bool) or not isinstance(ni, int) or ni not in live or ni in selected:
            raise ValueError('selection must identify distinct active mesh nodes')
        node = doc['nodes'][ni]
        if 'mesh' not in node or node.get('name') != row['node_name']:
            raise ValueError('selected node identity differs from reviewed input')
        ancestors, cur = [], ni
        while cur is not None:
            ancestors.append(cur)
            cur = live[cur][1]
        component = next((doc['nodes'][i].get('extras', {}).get('component_id') for i in ancestors if doc['nodes'][i].get('extras', {}).get('component_id')), None)
        if ('cylinder' in row) == ('cylinders' in row):
            raise ValueError('provide one cylinder or an explicit list of cylinders')
        parameters = [row['cylinder']] if 'cylinder' in row else row['cylinders']
        if not parameters or len(parameters) > 255:
            raise ValueError('replacement requires 1 to 255 cylinders')
        for index, parameter in enumerate(parameters):
            shape = cylinder_in_scene(parameter, live[ni][0])
            native.append({'id': f'node-{ni}-{index}', 'source_node_index': ni, 'source_node_name': row['node_name'],
                           'ancestor_nodes_root_first': ancestors[::-1], 'component_id': component,
                           'review_status': row.get('review_status', 'unreviewed'), 'shape': shape})
        selected.add(ni)
    if not selected:
        raise ValueError('at least one explicit replacement is required')
    remainder = copy.deepcopy(doc)
    removed = sum(sum(doc['accessors'][pr['indices']]['count'] // 3 for pr in doc['meshes'][doc['nodes'][ni]['mesh']]['primitives']) for ni in selected)
    for ni in selected:
        del remainder['nodes'][ni]['mesh']
    out.mkdir(parents=True, exist_ok=True)
    write_glb(out / 'remainder.glb', remainder, compact(remainder, binary))
    actual, ab = read_glb(out / 'remainder.glb')
    if scene_triangles(actual) != scene_triangles(doc) - removed:
        raise ValueError('remainder triangle accounting differs')
    # The selected mesh is absent, rather than colliding twice alongside a native shape.
    for ni in selected:
        assert 'mesh' not in actual['nodes'][ni]
    for ni, _, _ in scene_nodes(doc):
        n, a = doc['nodes'][ni], actual['nodes'][ni]
        assert {k:v for k,v in n.items() if k != 'mesh'} == {k:v for k,v in a.items() if k != 'mesh'}
        if ni in selected or 'mesh' not in n:
            continue
        pp = doc['meshes'][n['mesh']]['primitives']; qq = actual['meshes'][a['mesh']]['primitives']
        assert len(pp) == len(qq)
        for p, q in zip(pp, qq):
            assert {k:v for k,v in p.items() if k not in ['attributes','indices']} == {k:v for k,v in q.items() if k not in ['attributes','indices']}
            assert set(p['attributes']) == set(q['attributes'])
            for name in p['attributes']:
                aa, bb = accessor(doc,binary,p['attributes'][name]), accessor(actual,ab,q['attributes'][name])
                assert aa.dtype == bb.dtype and aa.shape == bb.shape and aa.tobytes() == bb.tobytes()
            assert accessor(doc,binary,p['indices']).tobytes() == accessor(actual,ab,q['indices']).tobytes()
    g = geometry(actual, ab)
    if not len(g):
        raise ValueError('prototype hybrid export requires retained mesh geometry')
    write_stl(out/'remainder.stl', g.reshape(-1,3), np.arange(g.size//3).reshape(-1,3))
    result = {'schema':SCHEMA, 'units':'m', 'coordinate_frame':'source_glb_active_scene',
              'cylinder_local_axis':'+Z', 'quaternion_order':'xyzw', 'status':'prototype_not_runtime_supported',
              'source':{'file':source.name,'sha256':selection['source_sha256']}, 'asset_id':selection['asset_id'],
              'scope':'one unplaced asset; retain manifest placements and floor/FLU conversion at runtime',
              'retained_mesh':{'file':'remainder.glb','sha256':digest(out/'remainder.glb'),'triangles':scene_triangles(actual),
                               'ownership':'Original node names, ancestry and source part partitions retained.'},
              'replaced_node_indices':sorted(selected),'removed_mesh_triangles':removed,'native_parts':native,
              'policy':'Explicit prototype selections only; remaining original mesh must be loaded together with native parts. Preserve motion ownership and contact/filter policy in a future adapter.'}
    (out/'collision-shapes.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    sdf = ET.Element('sdf',version='1.11'); model = ET.SubElement(sdf,'model',name='collision_shape_prototype')
    ET.SubElement(model,'static').text='true'; link=ET.SubElement(model,'link',name='asset_rest_pose')
    col=ET.SubElement(link,'collision',name='retained_mesh'); geo=ET.SubElement(col,'geometry');mesh=ET.SubElement(geo,'mesh');ET.SubElement(mesh,'uri').text='remainder.stl'
    for part in native:
        shape=part['shape']; pose=shape['pose']; col=ET.SubElement(link,'collision',name=part['id'])
        xyz=pose['translation_m'];rpy=Rotation.from_quat(pose['rotation_xyzw']).as_euler('xyz')
        ET.SubElement(col,'pose').text=' '.join(format(float(v),'.17g') for v in [*xyz,*rpy])
        cyl=ET.SubElement(ET.SubElement(col,'geometry'),'cylinder'); ET.SubElement(cyl,'radius').text=format(shape['radius_m'],'.17g'); ET.SubElement(cyl,'length').text=format(shape['length_m'],'.17g')
    ET.indent(sdf);ET.ElementTree(sdf).write(out/'model.sdf',encoding='utf-8',xml_declaration=True)
    if digest(source) != selection['source_sha256']:
        raise ValueError('source changed during export')
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source',type=Path);ap.add_argument('--selection',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);args=ap.parse_args()
    result=export(args.source,json.loads(args.selection.read_text()),args.out)
    print(json.dumps({'retained_mesh_triangles':result['retained_mesh']['triangles'],'native_cylinders':len(result['native_parts']),'runtime_supported':False}))

if __name__=='__main__':main()
