# SPDX-License-Identifier: MIT OR Apache-2.0
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
from articulated_scene import topology, extract_geometry, link_poses, load_asset
from export_articulated import export, meshes, name_map, write_sdf, write_urdf, write_usd
from gltf_scene import write_glb
from unittest.mock import patch
from test_articulated_scene import rig


def asset_fixture():
    doc, binary, binding = rig()
    graph, _ = topology(doc, binding)
    geometry = extract_geometry(doc, binary, binding, graph)
    return {'name': 'test', 'graph': graph, 'geometry': {'visual': geometry, 'collision': geometry}}


def origin(xyz, rpy):
    m = np.eye(4)
    m[:3, :3] = Rotation.from_euler('xyz', np.fromstring(rpy, sep=' ')).as_matrix()
    m[:3, 3] = np.fromstring(xyz, sep=' ')
    return m


class ExportArticulatedTests(unittest.TestCase):
    def test_xml_native_joint_forward_kinematics_and_meshes(self):
        asset = asset_fixture()
        names = name_map(asset['graph'])
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            records = meshes(asset, directory)
            write_urdf(asset, records, directory)
            write_sdf(asset, records, directory)
            urdf = ET.parse(directory / 'model.urdf').getroot()
            sdf = ET.parse(directory / 'model.sdf').getroot().find('model')
            q = {'spin': .63, 'slide': .31}
            expected = link_poses(asset['graph'], q)
            actual = {'root': np.eye(4)}
            for key, link in list(asset['graph'].items())[1:]:
                joint = urdf.find(f"joint[@name='{names[key]}_joint']")
                o = joint.find('origin')
                m = origin(o.get('xyz'), o.get('rpy'))
                delta = np.eye(4)
                axis = np.fromstring(joint.find('axis').get('xyz'), sep=' ')
                if joint.get('type') == 'prismatic':
                    delta[:3, 3] = axis * q[key]
                else:
                    delta[:3, :3] = Rotation.from_rotvec(axis * q[key]).as_matrix()
                actual[key] = actual[link['parent']] @ m @ delta
                np.testing.assert_allclose(actual[key], expected[key], atol=1e-10)
                native = sdf.find(f"joint[@name='{names[key]}_joint']")
                self.assertEqual(native.findtext('parent'), names[link['parent']])
                self.assertEqual(native.find('pose').get('relative_to'), names[key])
                np.testing.assert_allclose(np.fromstring(native.findtext('axis/xyz'), sep=' '), axis)
                rest = sdf.find(f"link[@name='{names[key]}']/pose").text.split()
                np.testing.assert_allclose(origin(' '.join(rest[:3]), ' '.join(rest[3:])), link['rest'], atol=1e-10)
            for mesh in urdf.findall('.//mesh'):
                self.assertTrue((directory / mesh.get('filename').removeprefix('package://rm_map_equipment/test/')).is_file())
            self.assertFalse(urdf.findall('.//inertial'))
            self.assertTrue(all(e.text == 'true' for e in sdf.findall('link/kinematic')))
            if shutil.which('check_urdf'):
                result = subprocess.run(['check_urdf', str(directory / 'model.urdf')], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_usd_arbitrary_axis_joint_frames_and_collision(self):
        try:
            from pxr import Usd, UsdGeom, UsdPhysics
        except ImportError:
            self.skipTest('usd-core is not installed')
        asset = asset_fixture()
        # The source's tilted slider direction must survive USD's cardinal axis schema.
        asset['graph']['slide']['joint']['axis'] = [2**-.5, 0, 2**-.5]
        names = name_map(asset['graph'])
        with tempfile.TemporaryDirectory() as tmp:
            write_usd(asset, Path(tmp))
            stage = Usd.Stage.Open(str(Path(tmp) / 'model.usdc'))
            for key, link in list(asset['graph'].items())[1:]:
                j = UsdPhysics.Joint.Get(stage, '/Model/joint_' + names[key])
                def rotation(q):
                    return Rotation.from_quat([*q.GetImaginary(), q.GetReal()]).as_matrix()
                r0, r1 = rotation(j.GetLocalRot0Attr().Get()), rotation(j.GetLocalRot1Attr().Get())
                parent = np.asarray(asset['graph'][link['parent']]['rest'])
                child = np.asarray(link['rest'])
                np.testing.assert_allclose(parent[:3, :3] @ r0, child[:3, :3] @ r1, atol=1e-6)
                np.testing.assert_allclose(r1[:, 0], link['joint']['axis'], atol=1e-6)
                np.testing.assert_allclose(parent[:3, :3] @ j.GetLocalPos0Attr().Get() + parent[:3, 3], child[:3, 3], atol=1e-6)
                body = stage.GetPrimAtPath('/Model/' + names[key])
                self.assertTrue(UsdPhysics.RigidBodyAPI(body).GetKinematicEnabledAttr().Get())
                np.testing.assert_allclose(np.array(UsdGeom.Xformable(body).GetLocalTransformation()).T, child)
            slide = UsdPhysics.PrismaticJoint.Get(stage, '/Model/joint_' + names['slide'])
            self.assertAlmostEqual(slide.GetUpperLimitAttr().Get(), .4, places=6)
            collisions = [p for p in stage.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI)]
            self.assertEqual(len(collisions), len(asset['geometry']['collision']))
            self.assertTrue(all(UsdGeom.Imageable(p).GetPurposeAttr().Get() == 'guide' for p in collisions))

    def test_package_integrity_metadata_and_atomic_failure(self):
        doc, binary, binding = rig()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'
            root.mkdir()
            write_glb(root / 'visual.glb', doc, binary)
            write_glb(root / 'collision.glb', doc, binary)
            files = {k: {'file': k + '.glb',
                         'sha256': hashlib.sha256((root / (k + '.glb')).read_bytes()).hexdigest(),
                         **binding} for k in ('visual', 'collision')}
            sidecar = {'schema_version': 1, 'layers': {'markings': {'visible': True}},
                       'assets': {'test': {'files': files}}}
            (root / 'articulation.json').write_text(json.dumps(sidecar))
            entry = {'visual': 'visual.glb', 'collision': 'collision.glb',
                     'semantics': {'file': 'articulation.json', 'asset': 'test'}}
            (root / 'manifest.json').write_text(json.dumps({'assets': {'test': entry}}))
            out = Path(tmp) / 'result'
            with patch('export_articulated.write_sdf', side_effect=RuntimeError('writer failed')):
                with self.assertRaises(RuntimeError):
                    export(root, out, formats=['sdf'])
            self.assertFalse(out.exists())
            self.assertFalse(list(Path(tmp).glob('.articulated-*')))
            export(root, out, formats=['urdf'])
            metadata = json.loads((out / 'test/semantics.json').read_text())
            self.assertEqual(metadata['semantic_context']['layers'], sidecar['layers'])
            self.assertTrue((out / 'package.xml').is_file())
            self.assertTrue((out / 'CMakeLists.txt').is_file())
            with self.assertRaises(ValueError):
                export(root, out, formats=['urdf'])
            (root / 'visual.glb').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                load_asset(root, 'test', entry)

    def test_frames_only_stays_fixed_without_preview_limits(self):
        asset = asset_fixture()
        joint = asset['graph']['spin']['joint']
        joint.update(type='revolute', geometry_binding='frames_only', preview_range=[-.1, .1])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            write_urdf(asset, [], path)
            write_sdf(asset, [], path)
            for filename, query in [('model.urdf', 'joint'), ('model.sdf', 'model/joint')]:
                joint = ET.parse(path / filename).getroot().find(query)
                self.assertEqual(joint.get('type'), 'fixed')
                self.assertIsNone(joint.find('limit'))


if __name__ == '__main__':
    unittest.main()
